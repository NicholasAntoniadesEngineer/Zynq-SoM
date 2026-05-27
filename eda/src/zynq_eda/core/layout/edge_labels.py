"""Hierarchical-label placement at sheet edges.

Each :class:`ExternalNet` declared on a block becomes one or more
hierarchical labels on the configured edge of the sub-sheet. Power-input
nets also get one ``power:PWR_FLAG`` per net so ERC accepts the sub-sheet
standalone (without a populated parent sheet).

Ground nets share one bottom-edge label and a single PWR_FLAG.
"""

from __future__ import annotations

from typing import Literal

from zynq_eda.core.layout._builder import (
    BlockLayoutBuilder,
    PinGeometryAbs,
    pin_intrinsic_owner_ids,
    _hierarchical_label_bbox,
)
from zynq_eda.core.layout._constants import (
    INTERIOR_MARGIN_MM,
    POWER_SYMBOL_OFFSET_MM,
    VISUAL_CLEARANCE_MM,
)


_LABEL_PERPENDICULAR_OFFSET_MM: float = 2.54
"""How far perpendicular-to-wire we shift a label's anchor.

Used by :func:`emit_label_perpendicular_to_wire` to push every hier or
local label's anchor OFF the wire's centerline so the label text never
sits along the wire. A 2.54 mm shift puts the text fully above (or
below) the wire's perpendicular bbox padding and out of the wire's own
half-thickness graze region.
"""


from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.block import Block, ExternalNet, IcInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.interface import SheetEdge
from zynq_eda.core.model.sheet import (
    PAPER_DIMENSIONS_MM,
    PlacedHierarchicalLabel,
    PlacedSymbol,
    PlacedWire,
)
from zynq_eda.core.layout.geometry import page_side_from_pin
from zynq_eda.core.route.router import route_orthogonal
from zynq_eda.core.route.shared_trunk import detect_collinear, route_shared_trunk


def place_external_nets(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]],
    ic_anchors: dict[str, Point],
    geometry_cache: SymbolGeometryCache,
) -> set[tuple[str, str]]:
    """Place per-NET edge labels + PWR_FLAGs (NOT per-pin).

    Per-pin edge-label routing now lives in
    :func:`zynq_eda.core.layout.place._emit_edge_label_pin` (called by
    the unified per-pin dispatcher). This function handles only the
    block-wide net services:

      * ``_ground_label_only`` — block-level GND hier-label.
      * ``_orphan_net_labels`` — hier-labels for declared external_nets
        anchored at an existing same-name local label (so KiCad merges
        by name).
      * ``_input_pwr_flags`` — PWR_FLAG drivers for input rails.

    Returns the empty set — the legacy ``edge_labeled`` mechanism
    coordinated signal_overrides skip flags; that machinery is gone.
    """
    paper_w, _paper_h = PAPER_DIMENSIONS_MM[block.paper_size]
    left_x = snap_to_grid(INTERIOR_MARGIN_MM)
    right_x = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)

    seen_label_positions: set[tuple[float, float]] = set()
    _ground_label_only(
        builder,
        block=block,
        ic_anchors=ic_anchors,
        left_x=left_x,
        right_x=right_x,
        seen_label_positions=seen_label_positions,
    )
    _orphan_net_labels(
        builder,
        block=block,
        left_x=left_x,
        right_x=right_x,
        paper_w=paper_w,
        seen_label_positions=seen_label_positions,
    )
    _input_pwr_flags(builder, block=block)
    return set()


def _per_ic_pin_labels(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    declared_nets: dict[str, ExternalNet],
    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]],
    ic_anchors: dict[str, Point],
    geometry_cache: SymbolGeometryCache,
    left_x: float,
    right_x: float,
    seen_label_positions: set[tuple[float, float]],
) -> set[tuple[str, str]]:
    """Emit one hierarchical label per (IC, override-or-supply pin), aligned with pin Y.

    Returns the set of ``(ic_reference, pin_name)`` pairs that got an
    edge-label wire so the signal-override pass can skip them.
    """
    edge_labeled: set[tuple[str, str]] = set()

    for ic in block.ics:
        ic_geoms = ic_pin_geometries.get(ic.reference, {})

        # Pre-compute the full pin map (every pin, not just the clustered
        # ones) for cross-pin-crossing detection below. Keyed by pin number
        # because that's what ``absolute_pin_positions`` returns.
        try:
            all_pin_positions = geometry_cache.absolute_pin_positions(
                ic.lib_id,
                ic_anchors[ic.reference],
            )
        except KeyError:
            all_pin_positions = {}

        # Compute the IC's body bbox X+Y range so the dogleg avoidance
        # avoids routing through the body itself.
        try:
            body_bbox = geometry_cache.bounding_box(
                ic.lib_id,
                rotation=0.0,
            )
            ic_anchor = ic_anchors[ic.reference]
            ic_body_y_range = (
                body_bbox.min_y + ic_anchor.y,
                body_bbox.max_y + ic_anchor.y,
            )
            ic_body_x_range = (
                body_bbox.min_x + ic_anchor.x,
                body_bbox.max_x + ic_anchor.x,
            )
        except Exception:
            ic_body_y_range = None
            ic_body_x_range = None

        # Build the candidate list: (pin_name, target_net). Sources:
        # 1. Refcircuit + per-instance pin_net_overrides — the IC's explicit
        #    "this pin is on net X" declarations. Highest priority.
        # 2. ic.power_input_net / power_output_net mapped to standard pin
        #    names. Lower priority — skipped when the same pin already has
        #    an explicit override.
        explicit_overrides: dict[str, str] = dict(ic.refcircuit.pin_net_overrides)
        explicit_overrides |= dict(getattr(ic, "net_overrides", ()) or ())

        candidates: list[tuple[str, str]] = []
        for pin_name, net_name in explicit_overrides.items():
            candidates.append((pin_name, net_name))

        if ic.power_input_net:
            for pin_name in ("IN", "VDD", "VCC", "VBUS", "AVDD", "DVDD", "PVIN", "ANODE"):
                if pin_name in explicit_overrides:
                    continue
                candidates.append((pin_name, ic.power_input_net))
        if ic.power_output_net:
            for pin_name in ("OUT", "VOUT", "CATHODE"):
                if pin_name in explicit_overrides:
                    continue
                candidates.append((pin_name, ic.power_output_net))

        # Pre-build a pin NAME → pin NUMBER map so each candidate can
        # carry its own pin number through to the per-pin and shared-
        # trunk routers (which add the source pin's intrinsic text owner
        # ids to ``avoid_owners`` so the wire's endpoint clearance
        # doesn't graze the source pin's own pin-name text).
        name_to_number: dict[str, str] = {}
        try:
            for pin_info in geometry_cache.all_pins(
                ic.lib_id,
                rotation=float(getattr(ic, "rotation", 0.0)),
            ):
                name_to_number[str(pin_info["name"])] = str(pin_info["number"])
        except Exception:
            pass

        # ---- Phase 1: resolve every candidate's pin geometry ------------
        # We need the pin connection + rotation info for ALL candidates
        # before we can group them. Singleton groups fall through to the
        # per-pin path; multi-pin collinear groups try the shared-trunk
        # router first.
        resolved: list[tuple[str, str, Point, float, float, str]] = []
        for pin_role, net_name in candidates:
            if net_name not in declared_nets:
                continue
            pin_number = name_to_number.get(pin_role, "")
            if pin_role in ic_geoms:
                pg = ic_geoms[pin_role]
                resolved.append((
                    pin_role, net_name, pg.connection,
                    getattr(pg, "pin_rotation", 0.0),
                    getattr(pg, "symbol_rotation", float(getattr(ic, "rotation", 0.0))),
                    pin_number,
                ))
                continue
            try:
                pg = geometry_cache.pin_geometry_by_name(
                    ic.lib_id,
                    ic_anchors[ic.reference],
                    pin_role,
                )
            except KeyError:
                continue
            resolved.append((
                pin_role, net_name, pg.connection,
                getattr(pg, "pin_rotation", 0.0),
                getattr(pg, "symbol_rotation", float(getattr(ic, "rotation", 0.0))),
                pin_number,
            ))

        # ---- Phase 2: try shared-trunk routing for collinear groups -----
        # Group by net_name; for each group of ≥2 pins where the pins are
        # collinear (share Y or share X), attempt a single shared trunk
        # with one hier label + per-pin stubs. This eliminates the
        # cluster of parallel same-Y wires that otherwise crosses every
        # pin's intrinsic pin-name text bbox.
        #
        # Compute forbidden coordinates: every OTHER override pin on
        # this IC. The shared trunk must NOT land on these — otherwise
        # the trunk wire would touch a foreign pin tip and mix this
        # net into the wrong net.
        all_resolved_pin_positions = {
            (round(conn.x, 3), round(conn.y, 3))
            for _r, _n, conn, _pr, _sr, _pn in resolved
        }
        handled_pins: set[str] = set()
        by_net: dict[str, list[tuple[str, Point, float, float, str]]] = {}
        for pin_role, net_name, conn, pin_rot, sym_rot, pin_number in resolved:
            by_net.setdefault(net_name, []).append(
                (pin_role, conn, pin_rot, sym_rot, pin_number)
            )

        for net_name, group in by_net.items():
            if len(group) < 2:
                continue
            pin_positions = [conn for _r, conn, _pr, _sr, _pn in group]
            axis = detect_collinear(pin_positions)
            if axis is None:
                continue

            net = declared_nets[net_name]
            label_x = left_x if net.edge == SheetEdge.LEFT else right_x

            # Choose label Y from the collinear coordinate so the label
            # sits at the natural pin-row Y (the trunk router will emit
            # a small vertical connector if the trunk itself is offset).
            label_y = snap_to_grid(pin_positions[0].y)
            label_position = Point(label_x, label_y)
            label_key = (label_position.x, label_position.y)
            if label_key in seen_label_positions:
                continue

            # body_inside_direction from the first pin's page-side.
            first_role, _, first_pin_rot, first_sym_rot, _first_pn = group[0]
            side = page_side_from_pin(
                pin_rotation=first_pin_rot,
                symbol_rotation=first_sym_rot,
            )
            body_inside = {
                "left": "right",
                "right": "left",
                "top": "down",
                "bottom": "up",
            }.get(side, "right")

            # avoid_owners exempts ONLY the source pins' own pin-name +
            # pin-number intrinsic bboxes (otherwise the trunk router's
            # stub wires endpoint clearance grazes each pin's own name
            # text and the route falsely blocks). The IC body is NOT
            # exempted — without that, trunks span the whole page
            # straight through the IC interior when LEFT-edge nets
            # come off RIGHT-side pins.
            source_pin_numbers = tuple(
                pn for _r, _c, _pr, _sr, pn in group if pn
            )
            avoid_owners_set: set[str] = set()
            avoid_owners_set |= set(
                pin_intrinsic_owner_ids(ic.reference, source_pin_numbers)
            )
            # Forbid the trunk from landing on ANY other override pin's
            # row/column on this IC. Mixing nets at a foreign pin tip
            # would silently connect this net to the wrong pin.
            group_pin_keys = {
                (round(c.x, 3), round(c.y, 3)) for c in pin_positions
            }
            forbidden_pts = frozenset(
                pt for pt in all_resolved_pin_positions
                if pt not in group_pin_keys
            )
            route = route_shared_trunk(
                pin_positions=pin_positions,
                label_position=label_position,
                occupancy=builder.occupancy,
                body_inside_direction=body_inside,
                avoid_owners=frozenset(avoid_owners_set),
                forbidden_traversal_points=forbidden_pts,
            )
            if route.gave_up:
                continue

            seen_label_positions.add(label_key)
            rotation = 180.0 if net.edge == SheetEdge.LEFT else 0.0
            builder.add_hierarchical_label(PlacedHierarchicalLabel(
                net_name=net_name,
                position=label_position,
                direction=net.direction,
                rotation=rotation,
            ))
            for seg in route.segments:
                builder.add_wire(seg)
            for junc in route.junctions:
                builder.junctions.append(junc)
            for pin_role, _, _, _, _ in group:
                handled_pins.add(pin_role)
                edge_labeled.add((ic.reference, pin_role))

        # ---- Phase 3: per-pin routing for ungrouped / non-collinear -----
        # All OTHER override pins on this IC are forbidden traversal
        # points: if Phase 3's route picks a Z-bend through another
        # override pin's tip, the resulting wire would mix the source's
        # net into that pin (KiCad treats pin tip on wire = connected).
        # Build the set once per IC.
        all_override_pin_positions = {
            (round(conn.x, 3), round(conn.y, 3))
            for _r, _n, conn, _pr, _sr, _pn in resolved
        }

        for pin_role, net_name, pin_connection, _pin_rot, _sym_rot, pin_number in resolved:
            if pin_role in handled_pins:
                continue
            net = declared_nets[net_name]
            label_x = left_x if net.edge == SheetEdge.LEFT else right_x
            source_pin_key = (round(pin_connection.x, 3), round(pin_connection.y, 3))
            forbidden_pts = frozenset(
                pt for pt in all_override_pin_positions if pt != source_pin_key
            )

            # Cross-pin-crossing avoidance: if the straight horizontal wire
            # from pin_connection to (label_x, pin_y) would pass through any
            # OTHER pin on this IC at the same Y, that other pin's stub
            # (placed later by ``_attach_ic_signal_overrides``) would land
            # on the same wire and KiCad ERC reports ``multiple_net_names``.
            # Detect the conflict and offset the wire's edge segment to a
            # neighbouring Y so the two nets stay electrically distinct.
            pin_y = snap_to_grid(pin_connection.y)
            route_y = _routed_y_avoiding_pin_crossings(
                pin_x=pin_connection.x,
                pin_y=pin_y,
                target_x=label_x,
                all_pin_positions=all_pin_positions,
                blocked_label_ys={y for (_x, y) in seen_label_positions},
                ic_body_y_range=ic_body_y_range,
                ic_body_x_range=ic_body_x_range,
            )

            # Incremental Y search: start at the heuristic-picked
            # route_y; if the pin → endpoint route can't be cleanly
            # drawn (router gives up because existing wires/bodies
            # block every shape), bump Y outward by one grid step and
            # retry. Last edge labels placed may end up far from
            # their natural row — by then every closer row has been
            # claimed by earlier wires.
            avoid_owners_set: set[str] = set()
            if pin_number:
                avoid_owners_set |= set(
                    pin_intrinsic_owner_ids(ic.reference, (pin_number,))
                )
            avoid_owners = frozenset(avoid_owners_set)

            from zynq_eda.core.route.router import route_orthogonal_detail
            picked_route_y: float | None = None
            picked_segments: list = []
            for y_step in range(0, 15):
                for sign in (1, -1) if y_step > 0 else (1,):
                    cand_y = snap_to_grid(route_y + sign * y_step * 2.54)
                    cand_endpoint = Point(label_x, cand_y)
                    key = (cand_endpoint.x, cand_endpoint.y)
                    if key in seen_label_positions:
                        continue
                    attempt = route_orthogonal_detail(
                        pin_connection,
                        cand_endpoint,
                        builder.occupancy,
                        avoid_owners=avoid_owners,
                        forbidden_traversal_points=forbidden_pts,
                    )
                    if attempt.gave_up:
                        continue
                    picked_route_y = cand_y
                    picked_segments = list(attempt.segments)
                    break
                if picked_route_y is not None:
                    break
            if picked_route_y is None:
                # No clean route at any Y — give up on this pin's
                # edge-label and let signal-override emit a local
                # label instead. Hard-fail later if validator catches.
                continue
            wire_endpoint = Point(label_x, picked_route_y)
            key = (wire_endpoint.x, wire_endpoint.y)
            seen_label_positions.add(key)

            rotation = 180.0 if net.edge == SheetEdge.LEFT else 0.0
            # Pass 3 of the overlap-free plan: hier-label sits AT the
            # wire endpoint, no stub. Text rotation is chosen so the
            # text extends OUTWARD from the page (off the sheet edge),
            # away from the wire's interior approach. The pin → label
            # route was already picked above with a clean Y row.
            builder.add_hierarchical_label(PlacedHierarchicalLabel(
                net_name=net_name,
                position=wire_endpoint,
                direction=net.direction,
                rotation=rotation,
            ))
            for seg in picked_segments:
                builder.add_wire(seg)
            edge_labeled.add((ic.reference, pin_role))

    return edge_labeled


def _routed_y_avoiding_pin_crossings(
    *,
    pin_x: float,
    pin_y: float,
    target_x: float,
    all_pin_positions: dict[str, Point],
    blocked_label_ys: set[float],
    ic_body_y_range: tuple[float, float] | None = None,
    ic_body_x_range: tuple[float, float] | None = None,
) -> float:
    """Pick a Y for the edge-bound segment that avoids crossing other pins.

    Strategy:

    1. **Straight wire (pin_y)** — preferred when the straight wire
       does NOT cross the IC body horizontally and no other pin sits
       on it within the X span.
    2. **Outside-body Y** — when the straight wire would cross the IC
       body horizontally (e.g. a wire from a RIGHT-side pin to a LEFT-
       edge label whose path traverses the IC interior), pick a Y
       OUTSIDE the body's Y range. The wire then needs a vertical
       segment from pin_y to the dogleg-Y and another back, but it
       doesn't slice through the body interior.
    3. **Outward grid step** — fall back to the existing per-pin
       crossing avoidance.

    Snaps every candidate Y to the schematic grid so blocked-Y comparison
    is exact (avoids float drift from ``pin_y + n * 2.54``).
    """
    GRID_MM = 2.54
    MAX_OFFSET_STEPS = 6  # 15.24 mm of vertical room either way
    EPS = 1e-3

    x_lo, x_hi = min(pin_x, target_x), max(pin_x, target_x)

    def pin_collides(y: float) -> bool:
        for other in all_pin_positions.values():
            if abs(other.y - y) > EPS:
                continue
            # Skip ONLY the source pin itself (same X AND same Y).
            # Other pins on the same X column at DIFFERENT Y are NOT
            # safe to ignore — when the route Z-bends through this Y,
            # its vertical leg at pin_x passes through every pin on
            # that column, and the resulting wire-touches-pin would
            # mix the source's net into the touched pin's net. See the
            # FUSB302 CC1/CC2 duplicate-wire case (CC1's Z-bend at
            # Y=CC2.y emits a wire passing through CC2's pin tip).
            if abs(other.x - pin_x) < EPS and abs(other.y - pin_y) < EPS:
                continue
            if x_lo - EPS < other.x < x_hi + EPS:
                return True
        return False

    def is_blocked(y: float) -> bool:
        # Float-tolerant membership against the blocked set (the set's
        # values come from a previous snap_to_grid pass, so direct == may
        # still differ by a hair of ULP drift).
        return any(abs(b - y) < EPS for b in blocked_label_ys)

    def y_inside_body(y: float) -> bool:
        """True iff y sits STRICTLY inside the IC body's Y range."""
        if ic_body_y_range is None:
            return False
        body_min_y, body_max_y = ic_body_y_range
        return body_min_y + EPS < y < body_max_y - EPS

    def wire_crosses_body_x(y_candidate: float) -> bool:
        """True iff a horizontal wire from (pin_x, y) to (target_x, y)
        TRAVERSES the IC body's X range — i.e. the wire span extends
        past BOTH body edges in opposite directions from the body.

        Wires that legitimately terminate at a pin on one body side
        and exit the OPPOSITE side don't qualify because their span
        stays on one side of body's min OR max edge.
        """
        if ic_body_x_range is None or not y_inside_body(y_candidate):
            return False
        bx_lo, bx_hi = ic_body_x_range
        return x_lo < bx_lo and x_hi > bx_hi

    pin_y_snapped = snap_to_grid(pin_y)
    straight_ok = (
        not pin_collides(pin_y_snapped)
        and not is_blocked(pin_y_snapped)
        and not wire_crosses_body_x(pin_y_snapped)
    )
    if straight_ok:
        return pin_y_snapped

    # Search outward in increasing steps to find a clean Y. Prefer the
    # smaller offset; tie-break with the +Y direction.
    for step in range(1, MAX_OFFSET_STEPS + 1):
        for sign in (1, -1):
            candidate = snap_to_grid(pin_y_snapped + sign * step * GRID_MM)
            if pin_collides(candidate):
                continue
            if is_blocked(candidate):
                continue
            if y_inside_body(candidate):
                # Dogleg into the body is worse than the original
                # collision — skip and search further.
                continue
            # Outside body — also implies wire_crosses_body_x(candidate)
            # is False, so we're done.
            return candidate

    # Nothing clean within range — fall back to the pin's Y. Caller may
    # still produce an ERC warning, but at least the layout is legal.
    return pin_y_snapped


def _input_pwr_flags(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
) -> None:
    """Emit exactly one ``power:PWR_FLAG`` per input-direction net.

    ERC requires every power_in pin to have an upstream power_out driver.
    The hierarchical label alone doesn't qualify, so we add a PWR_FLAG to
    every incoming power net. Output-direction nets (LDO OUT etc.) are
    driven by the IC's power_out pin and need no flag — adding one would
    create a pin_to_pin conflict with two competing power_out drivers.
    Ground nets are handled separately by :func:`_ground_label_and_flag`.
    """
    flag_emitted_for_net: set[str] = set()
    # Pre-compute which external nets are SOURCED on this block by a
    # connector pin. Connectors are the "entry point" — only the
    # sourcing block emits the PWR_FLAG to avoid Power-output ×
    # Power-output conflicts across sheets (e.g. +VIN appears on both
    # usb_pd and power as PowerInputNet, but the USB-C connector on
    # usb_pd is the real source).
    nets_sourced_by_connector: set[str] = set()
    for conn in getattr(block, "connectors", ()) or ():
        for _pin_id, net_name in (getattr(conn, "pin_to_net", ()) or ()):
            nets_sourced_by_connector.add(net_name)

    for net in block.external_nets:
        # Emit PWR_FLAG for power-input, power-output (when no IC driver),
        # AND ground variants that aren't the canonical "GND" (which
        # KiCad's power:GND symbol already drives). Examples: CHASSIS_GND,
        # AGND, DGND — each represented by a power:Earth / power-style
        # symbol that needs a PWR_FLAG driver per ERC.
        if net.power_kind not in ("input", "output", "ground"):
            continue
        if net.power_kind == "ground" and net.name.upper() == "GND":
            # Canonical GND is driven by the cluster's power:GND symbol
            # (KiCad's standard ground driver) — adding a PWR_FLAG would
            # double-drive the net.
            continue
        # Output nets only need a PWR_FLAG when the block itself doesn't
        # contain a power_out pin to drive them. We detect this by checking
        # whether any IC declares this net as ``power_output_net``.
        if net.power_kind == "output":
            has_power_out_driver = any(
                ic.power_output_net == net.name for ic in block.ics
            )
            if has_power_out_driver:
                continue
        # For input nets: emit PWR_FLAG only when this block is the
        # SOURCE of the net (i.e. has a connector pin providing it).
        # Pure consumer blocks see the net via cross-sheet binding;
        # adding a PWR_FLAG there double-drives the net and produces
        # Power-output × Power-output pin_to_pin warnings. Special
        # case: ``CHASSIS_GND``-style ground variants without a
        # connector source still need a flag (no other driver exists).
        if net.power_kind == "input" and net.name not in nets_sourced_by_connector:
            continue
        if net.name in flag_emitted_for_net:
            continue
        flag_emitted_for_net.add(net.name)

        anchor_label = next(
            (label for label in builder.hierarchical_labels if label.net_name == net.name),
            None,
        )
        if anchor_label is None:
            continue

        # Place the PWR_FLAG beyond the FAR edge of EVERY hier label
        # already placed on the same side of the sheet, then CLAMP to
        # page bounds so the FLG body never prints off-page. The FLG
        # body is ~2 × 2.5 mm so even on a 2.54 mm grid it bleeds into
        # the adjacent label row when placed at the same X as the
        # labels — pushing past the longest label's bbox edge is the
        # only way to get the FLG fully clear of every label row.
        from zynq_eda.core.layout._builder import _hierarchical_label_bbox
        from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM as _MARGIN
        from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
        FLG_HALF_WIDTH_MM = 1.02
        SAFETY_MARGIN_MM = 1.0
        paper_w, _ = PAPER_DIMENSIONS_MM[block.paper_size]
        page_min_x = snap_to_grid(_MARGIN + FLG_HALF_WIDTH_MM)
        page_max_x = snap_to_grid(paper_w - _MARGIN - FLG_HALF_WIDTH_MM)
        if anchor_label.rotation == 180.0:
            edge_x_candidates = [
                _hierarchical_label_bbox(lbl).min.x
                for lbl in builder.hierarchical_labels
                if lbl.rotation == 180.0
            ]
            global_min_x = min(edge_x_candidates) if edge_x_candidates else anchor_label.position.x
            flag_x = snap_to_grid(global_min_x - FLG_HALF_WIDTH_MM - SAFETY_MARGIN_MM)
            flag_x = max(flag_x, page_min_x)
        elif anchor_label.rotation == 0.0:
            edge_x_candidates = [
                _hierarchical_label_bbox(lbl).max.x
                for lbl in builder.hierarchical_labels
                if lbl.rotation == 0.0
            ]
            global_max_x = max(edge_x_candidates) if edge_x_candidates else anchor_label.position.x
            flag_x = snap_to_grid(global_max_x + FLG_HALF_WIDTH_MM + SAFETY_MARGIN_MM)
            flag_x = min(flag_x, page_max_x)
        else:
            flag_x = anchor_label.position.x
        flag_position = Point(flag_x, anchor_label.position.y)
        # Route the hier-label → PWR_FLAG wire via the router so it
        # respects the no-cross / no-through rules. Anchor label is the
        # only owner we exempt — its text bbox is at the anchor.
        from zynq_eda.core.route.router import route_orthogonal_detail
        flag_avoid = frozenset({
            f"hlabel:{anchor_label.net_name}@"
            f"{anchor_label.position.x:.1f},{anchor_label.position.y:.1f}",
        })
        flag_route = route_orthogonal_detail(
            anchor_label.position,
            flag_position,
            builder.occupancy,
            avoid_owners=flag_avoid,
        )
        if flag_route.gave_up:
            raise RuntimeError(
                f"_input_pwr_flags: router gave up routing hier label "
                f"{anchor_label.net_name!r} @ {anchor_label.position} → "
                f"PWR_FLAG @ {flag_position}."
            )
        for seg in flag_route.segments:
            builder.add_wire(seg)
        builder.add_symbol(PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=builder.next_ref("#FLG"),
            value=net.name,
            position=flag_position,
            footprint="",
            rotation=0.0,
        ))


def _orphan_net_labels(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    left_x: float,
    right_x: float,
    paper_w: float,
    seen_label_positions: set[tuple[float, float]],
) -> None:
    """Surface declared external_nets that have no hier label yet.

    Strategy: find a same-name local label that the cluster/connector
    code already emitted (those sit at real wire endpoints on real
    component pins), then drop a hierarchical label at the EXACT same
    coordinate. KiCad collapses co-located same-name labels into one
    electrical net, so the hier label inherits the real net.

    The hier label's rotation is derived from the DECLARED net edge
    (180 for LEFT-edge nets, 0 for RIGHT-edge nets) — NOT inherited
    from the local label's default rotation 0. Picking the rotation
    from net.edge makes the hier-label text always read OUTBOARD of
    the connector pin tail it's anchored to, away from the connector
    body's pin-name text. (HDMI RX is the classic example: the HDMI-A
    connector sits on the RIGHT edge but the TMDS signals are declared
    with ``edge=SheetEdge.LEFT``; without the explicit rotation flip,
    the hier-label text would read INTO the HDMI body, overlapping the
    pin-name text printed there.)

    Without an existing local label to anchor onto, we skip the net —
    no point dropping a hier label that floats with no connection.
    Such nets stay invisible to the root sheet; the user must add an
    explicit ``external_parts`` driver or a per-block wire to expose
    them.
    """
    already_labeled = {label.net_name for label in builder.hierarchical_labels}
    local_labels_by_name: dict[str, list] = {}
    for lab in builder.labels:
        local_labels_by_name.setdefault(lab.net_name, []).append(lab)

    # Pre-compute X bounds the connector-pin labels sit near so we can
    # prefer them over cluster-far-terminal labels when both exist for
    # the same net. Connectors are placed at the LEFT or RIGHT sheet
    # edge; their per-pin labels land at ``stub_end`` which is one
    # ``STUB_LEN`` (2.54 mm) outside the connector body — i.e. close to
    # the sheet edge. Cluster far-terminal labels are typically deep
    # inside the page (10-20 mm from the IC body). Picking the most
    # edge-adjacent label as the hier-label anchor ensures the hier
    # label sits where the user expects (at the connector edge) rather
    # than at a passive cluster's far-far terminal.
    def _anchor_priority(lab) -> float:
        # Prefer labels closer to either sheet edge: smaller of
        # (distance-to-left-edge, distance-to-right-edge).
        return min(lab.position.x - left_x, right_x - lab.position.x)

    for net in block.external_nets:
        if net.name in already_labeled:
            continue
        matching = local_labels_by_name.get(net.name)
        if not matching:
            # No local label of this name exists — net only lives inside
            # the sub-sheet via component pins (no connector driver and
            # no override label). Surfacing it as a hier label would
            # produce a dangling label per ERC. Skip.
            continue
        # Pick the most-edge-adjacent local label as the hier anchor.
        anchor_label = min(matching, key=_anchor_priority)
        key = (anchor_label.position.x, anchor_label.position.y)
        if key in seen_label_positions:
            continue
        seen_label_positions.add(key)
        # Pass 3: hier-label sits AT the local label's wire-endpoint
        # position (no perpendicular stub). Inherits the local label's
        # rotation so the text continues to read OUTWARD from the host
        # symbol body. KiCad merges co-located same-name labels into
        # one electrical net, so the hier label inherits the local
        # label's wire endpoint connection.
        hier_rotation = anchor_label.rotation
        builder.add_hierarchical_label(PlacedHierarchicalLabel(
            net_name=net.name,
            position=anchor_label.position,
            direction=net.direction,
            rotation=hier_rotation,
        ))
        # Strip the now-redundant local label that the hier label
        # supersedes. KiCad's label-merging by name keeps electrical
        # connectivity intact across the sheet's other labels.
        try:
            builder.labels.remove(anchor_label)
            matching.remove(anchor_label)
        except ValueError:
            pass


def _ground_label_only(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    ic_anchors: dict[str, Point],
    left_x: float,
    right_x: float,
    seen_label_positions: set[tuple[float, float]],
) -> None:
    """Emit one GND hierarchical label per declared GroundNet, anchored to a real wire.

    Strategy (in order of preference; each tries to anchor onto a real
    wire endpoint so the hier label never floats with no connection):

      1. **Same-name local label** — for ground nets whose name appears
         on a local label (the connector pass emits one per GND-bound
         connector pin), drop the hier label at that coordinate and
         remove the local label. KiCad merges co-located same-name
         labels into one electrical net.
      2. **Same-name power symbol** — the cluster pass attaches GND
         passives via ``power:GND`` symbols at real wire endpoints. Drop
         the hier label AT the power-symbol coord; the symbol is already
         a wire terminus so the hier label inherits a real connection.
         (``CHASSIS_GND`` uses ``power:Earth``; both share the symbol's
         ``value`` field for matching.)
      3. **Skip** — if neither exists, the sub-sheet has no wired GND
         endpoint to surface. Historically we emitted a phantom edge
         hier label + standalone power:GND symbol; that "dangling stub"
         was visible junk on the left edge of every otherwise-clean
         sheet (the cosmetic issue this commit fixes). Skipping the
         emission leaves connectivity intact (the block's GND comes
         through the cluster passives' power symbols, all merged via
         KiCad's global ``power:GND`` net) and removes the floating
         edge label.

    PWR_FLAG drivers live on the root sheet (see :mod:`root`); emitting
    one here would duplicate the driver and trigger ``pin_to_pin``
    Power-out conflicts.
    """
    # Pre-index existing GND local labels so we can anchor at any of them.
    local_labels_by_name: dict[str, list] = {}
    for lab in builder.labels:
        local_labels_by_name.setdefault(lab.net_name, []).append(lab)

    # Pre-index already-placed power symbols by their displayed net name
    # (the ``value`` field) so we can re-use a same-name ``power:GND`` /
    # ``power:Earth`` placed by the cluster pass as the hier-label anchor.
    # Power symbols sit at real wire endpoints by construction, so this
    # is electrically equivalent to anchoring at a local-label coord but
    # works for the common case where the cluster pass chose a symbol
    # instead of a label (GND destinations almost always do).
    power_symbols_by_value: dict[str, list[PlacedSymbol]] = {}
    for sym in builder.symbols:
        if sym.lib_id.startswith("power:"):
            power_symbols_by_value.setdefault(sym.value, []).append(sym)

    for ground_net in block.external_nets:
        if ground_net.power_kind != "ground":
            continue

        # Preferred path 1: piggyback on an existing local label sitting
        # on a real wire. KiCad merges co-located same-name labels into
        # one electrical net, so the hier label inherits the local
        # label's wire endpoint and no longer dangles. Rotation is set
        # from the DECLARED net edge so the GND text reads outboard of
        # the connector body (mirrors ``_orphan_net_labels``).
        matching = local_labels_by_name.get(ground_net.name)
        if matching:
            anchor_label = matching[0]
            key = (anchor_label.position.x, anchor_label.position.y)
            if key in seen_label_positions:
                continue
            seen_label_positions.add(key)
            # Pass 3: hier-label sits AT the local label's wire
            # endpoint (no perpendicular stub). Inherits the local
            # label's rotation so text continues to read outward.
            hier_rotation = anchor_label.rotation
            builder.add_hierarchical_label(PlacedHierarchicalLabel(
                net_name=ground_net.name,
                position=anchor_label.position,
                direction=ground_net.direction,
                rotation=hier_rotation,
            ))
            # Drop the now-redundant local label — KiCad would render
            # both, double-printing the GND text at the same coord.
            try:
                builder.labels.remove(anchor_label)
                matching.pop(0)
            except ValueError:
                pass
            continue

        # Preferred path 2: piggyback on a same-name power symbol. The
        # cluster pass placed it at a real wire endpoint (the far
        # terminal of a GND-bound cap or resistor); putting the hier
        # label at the same coordinate ties it into the live wire
        # without a separate dangling stub.
        #
        # Pick the symbol whose Y is FURTHEST from any existing hier
        # label's Y. Same-Y collisions on the LEFT/RIGHT edge collapse
        # to adjacent sheet-pin rows on the root sheet (5.08 mm apart),
        # and the per-pin power-symbol + PWR_FLAG stacks overlap in
        # weird ways — historically that triggered ``multiple_net_names``
        # warnings when a +VIN label landed on the same column as a
        # GND power-symbol stack. Maximising Y-separation between the
        # GND hier label and the already-placed power-input labels
        # eliminates the per-pin overlap regardless of pitch.
        matching_syms = power_symbols_by_value.get(ground_net.name)
        if matching_syms:
            # KiCad's ``power:GND`` and ``power:Earth`` are GLOBAL net
            # drivers — they propagate the net across every sub-sheet
            # without a hier label. Emitting a hier label at the power
            # symbol's anchor produces a real visible overlap (the
            # label's text bbox lands on the power-symbol body), and
            # the hier label is redundant electrically. Skip the emit
            # for sheets that already have the same-named power symbol.
            continue

        # No local label and no same-name power symbol on this sheet —
        # the block doesn't have a wired GND endpoint to surface. The
        # legacy phantom edge-label + standalone power:GND fallback
        # produced a floating stub on the left edge of every sheet that
        # had only connector-fed GND pins. Skip emission entirely:
        # connectivity stays intact via KiCad's global ``power:GND``
        # net (any cluster passive grounded through a power:GND symbol
        # joins the global), and no floating graphic is drawn.
        continue
