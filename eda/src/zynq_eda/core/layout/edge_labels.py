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
    HLABEL_LADDER_STEPS,
    HLABEL_SHEET_EDGE_LADDER_STEPS,
    HLABEL_TOP_BOTTOM_LADDER_STEPS,
    INTERIOR_MARGIN_MM,
    KICAD_GRID_MM,
    OVERLAP_NOISE_FLOOR_MM,
    POWER_SYMBOL_OFFSET_MM,
    VISUAL_CLEARANCE_MM,
    WIRE_THICKNESS_MM,
)


_LABEL_PERPENDICULAR_OFFSET_MM: float = KICAD_GRID_MM
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
    # Part II Fix 1 (Variant A): PWR_FLAGs are routed BEFORE the orphan-
    # net hier-labels. ``_input_pwr_flags`` now anchors on the LOCAL
    # labels emitted by the cluster/connector passes — those exist at
    # this point, the hier-labels don't yet. Then ``_orphan_net_labels``
    # sees the complete live occupancy (cluster wires + dispatcher wires
    # + PWR_FLAG wires) when picking each net's hier-label position.
    _input_pwr_flags(builder, block=block)
    # ``_orphan_net_labels`` handles ALL declared external_nets through
    # the candidate ladder — including ground nets that have a same-name
    # local label. ``_ground_label_only`` handles only the special case
    # where a power:GND symbol already drives the net (no hier-label
    # needed since power:GND is a global net driver).
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

        # Part II Fix 1: anchor on the LOCAL label, not the hier-label.
        # _input_pwr_flags now runs BEFORE _orphan_net_labels in
        # place_external_nets, so no hier-label exists yet. The local
        # label was placed by the cluster/connector pass at the net's
        # real wire endpoint (cluster trunk_end or connector pin tip),
        # and routing from there ties the PWR_FLAG to the live net.
        anchor_label = next(
            (lab for lab in builder.labels if lab.net_name == net.name),
            None,
        )
        if anchor_label is None:
            continue

        # Place the PWR_FLAG beyond the FAR edge of EVERY local label
        # on the same orientation, then CLAMP to page bounds so the FLG
        # body never prints off-page.
        from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM as _MARGIN
        from zynq_eda.core.layout.bbox import (
            DEFAULT_TEXT_SIZE_MM,
            DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO,
        )
        from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
        FLG_HALF_WIDTH_MM = 1.02
        SAFETY_MARGIN_MM = 1.0
        paper_w, _ = PAPER_DIMENSIONS_MM[block.paper_size]
        page_min_x = snap_to_grid(_MARGIN + FLG_HALF_WIDTH_MM)
        page_max_x = snap_to_grid(paper_w - _MARGIN - FLG_HALF_WIDTH_MM)

        # PREDICTED hier-label width: matches the future hier-label bbox
        # (decorated_text = net_name + " " in _hierarchical_label_bbox).
        # Using local-label width directly would shift flag_x by one char
        # and let the FLG body land in cluster region.
        def _predicted_hlabel_text_width(lbl) -> float:
            return (
                (len(lbl.net_name) + 1) * DEFAULT_TEXT_SIZE_MM
                * DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO
            )

        def _local_label_min_x(lbl) -> float:
            # For rotation 180 the text extends LEFT of the anchor; for
            # rotation 0 it extends RIGHT. The min.x of the bbox is the
            # left edge of the text.
            if lbl.rotation == 180.0:
                return lbl.position.x - _predicted_hlabel_text_width(lbl)
            return lbl.position.x

        def _local_label_max_x(lbl) -> float:
            if lbl.rotation == 0.0:
                return lbl.position.x + _predicted_hlabel_text_width(lbl)
            return lbl.position.x

        if anchor_label.rotation == 180.0:
            edge_x_candidates = [
                _local_label_min_x(lbl)
                for lbl in builder.labels
                if lbl.rotation == 180.0
            ]
            global_min_x = min(edge_x_candidates) if edge_x_candidates else anchor_label.position.x
            flag_x = snap_to_grid(global_min_x - FLG_HALF_WIDTH_MM - SAFETY_MARGIN_MM)
            flag_x = max(flag_x, page_min_x)
        elif anchor_label.rotation == 0.0:
            edge_x_candidates = [
                _local_label_max_x(lbl)
                for lbl in builder.labels
                if lbl.rotation == 0.0
            ]
            global_max_x = max(edge_x_candidates) if edge_x_candidates else anchor_label.position.x
            flag_x = snap_to_grid(global_max_x + FLG_HALF_WIDTH_MM + SAFETY_MARGIN_MM)
            flag_x = min(flag_x, page_max_x)
        else:
            flag_x = anchor_label.position.x
        # PWR_FLAG candidate Y ladder: deterministic — anchor.y first,
        # then grid steps outward. (Part III: the prior "off-pin-row
        # preference" hack was a softening; in the predictive
        # architecture, the planner places the PWR_FLAG based on the
        # full plan including the future hier-label position, so no
        # Y-preference heuristic is needed.)
        from zynq_eda.core.route.router import route_orthogonal_detail
        # Same-net labels exempted (so the route can pass through any
        # local label of the same net).
        same_net_avoid = frozenset({
            f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
            for lab in builder.labels
            if lab.net_name == net.name
        })

        flag_y_candidates = [anchor_label.position.y]
        for step in range(1, HLABEL_LADDER_STEPS + 1):
            for sign in (1, -1):
                flag_y_candidates.append(
                    snap_to_grid(anchor_label.position.y + sign * step * KICAD_GRID_MM)
                )

        flag_route_segments: list | None = None
        flag_position_picked: Point | None = None
        for fy in flag_y_candidates:
            cand_pos = Point(flag_x, fy)
            # Clamp to page bounds (interior margin on both sides).
            paper_h_block = PAPER_DIMENSIONS_MM[block.paper_size][1]
            if cand_pos.y < INTERIOR_MARGIN_MM or cand_pos.y > paper_h_block - INTERIOR_MARGIN_MM:
                continue
            attempt = route_orthogonal_detail(
                anchor_label.position,
                cand_pos,
                builder.occupancy,
                avoid_owners=same_net_avoid,
            )
            if attempt.gave_up:
                continue
            flag_route_segments = list(attempt.segments)
            flag_position_picked = cand_pos
            break

        if flag_position_picked is None:
            raise RuntimeError(
                f"_input_pwr_flags: router gave up routing local label "
                f"{anchor_label.net_name!r} @ {anchor_label.position} → "
                f"PWR_FLAG at any Y candidate near flag_x={flag_x}. "
                f"Tried {len(flag_y_candidates)} Y positions. "
                f"Upstream fix: relocate the local label anchor or "
                f"widen the page margin for the PWR_FLAG."
            )

        flag_position = flag_position_picked
        for seg in flag_route_segments:
            builder.add_wire(seg)
        builder.add_symbol(PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=builder.next_ref("#FLG"),
            value=net.name,
            position=flag_position,
            footprint="",
            rotation=0.0,
        ))


from dataclasses import dataclass


@dataclass(frozen=True)
class _HlabelCandidate:
    """One candidate position for a hier-label placement.

    The candidate ladder (Part II Fix 2) tries positions in priority
    order — in-place at the anchor, then perpendicular Y-offsets, then
    sheet-edge with various Y rows. The first whose hier-label text
    bbox is clear AND whose routing extension (if any) is clean wins.

    Note: ``rotation`` per-candidate (NOT a global per-net rotation).
    In-place and y-offset candidates inherit the LOCAL label's rotation
    (text reads away from the connector body), while sheet-edge
    candidates use the net.edge convention rotation (text reads outward
    off-page).
    """
    position: Point
    rotation: float
    route_from: Point | None  # None = no routing wire needed (in-place)
    kind: str                  # "in_place" | "y_offset" | "sheet_edge"


def _enumerate_hlabel_candidates(
    *,
    net: ExternalNet,
    anchor_label,
    edge_rotation: float,
    target_edge_x: float,
    pin_y_range: tuple[float, float] | None,
    paper_h: float,
) -> list[_HlabelCandidate]:
    """Build the ordered candidate ladder for a hier-label placement.

    Priority order:
      1. ``in_place`` — at the local-label anchor (no extension wire).
         Uses the LOCAL label's rotation so the text continues to read
         AWAY from the host symbol body (connector / cluster).
      2. ``y_offset`` — perpendicular Y-offset at the same X
         (one short vertical extension wire). Also uses local rotation.
      3. ``sheet_edge`` — at the declared sheet edge X, at various Y
         rows including those OUTSIDE the connector pin Y range
         (a longer routed extension wire). Uses ``edge_rotation``
         (per ``net.edge`` convention: 180 for LEFT-edge nets, 0 for
         RIGHT) so the text reads OFF-PAGE.

    Pure function. No occupancy access — the caller (_first_clean_candidate)
    probes each candidate against the live occupancy.
    """
    candidates: list[_HlabelCandidate] = []
    anchor_x = snap_to_grid(anchor_label.position.x)
    anchor_y = snap_to_grid(anchor_label.position.y)
    local_rotation = anchor_label.rotation

    # Build the set of rotations to try for each candidate position.
    # In priority order: local_rotation (text matches local label's
    # direction), edge_rotation (text matches net.edge convention),
    # opposite of local, and vertical (90/270). Each new candidate
    # rotation gives the router another chance to escape a dense
    # cluster region.
    rotation_options: list[float] = []
    for r in (local_rotation, edge_rotation, (local_rotation + 180.0) % 360.0,
              90.0, 270.0):
        if r not in rotation_options:
            rotation_options.append(r)

    # 1. In-place candidates — one per rotation.
    for r in rotation_options:
        candidates.append(_HlabelCandidate(
            position=Point(anchor_x, anchor_y),
            rotation=r,
            route_from=None,
            kind="in_place",
        ))

    # 2. Perpendicular Y-offsets at anchor X — each rotation × each Y step.
    for step in range(1, HLABEL_LADDER_STEPS + 1):
        for sign in (1, -1):
            cand_y = snap_to_grid(anchor_y + sign * step * KICAD_GRID_MM)
            for r in rotation_options:
                candidates.append(_HlabelCandidate(
                    position=Point(anchor_x, cand_y),
                    rotation=r,
                    route_from=Point(anchor_x, anchor_y),
                    kind="y_offset",
                ))

    # 3. Sheet-edge candidates with Y ladder (declared edge — LEFT/RIGHT).
    edge_ys: list[float] = [anchor_y]
    for step in range(1, HLABEL_SHEET_EDGE_LADDER_STEPS + 1):
        for sign in (1, -1):
            edge_ys.append(snap_to_grid(anchor_y + sign * step * KICAD_GRID_MM))
    # Also include rows OUTSIDE the connector pin Y range when known.
    # These are the most reliable: the off-pin band has no clusters
    # crossing it (clusters live AT the pin rows). Routing from anchor
    # to (edge_x, off_pin_y) only needs to escape the cluster region
    # ONCE then traverse the empty band.
    if pin_y_range is not None:
        pin_y_lo, pin_y_hi = pin_y_range
        # Generate Y values BELOW the pin range (page top, smaller Y)
        # down to the top page margin, in grid steps.
        y_above = snap_to_grid(pin_y_lo - 2 * KICAD_GRID_MM)
        y = y_above
        while y > INTERIOR_MARGIN_MM:
            edge_ys.append(y)
            y = snap_to_grid(y - KICAD_GRID_MM)
        # Generate Y values ABOVE the pin range (page bottom, larger Y)
        # down to the bottom page margin.
        y_below = snap_to_grid(pin_y_hi + 2 * KICAD_GRID_MM)
        y = y_below
        while y < paper_h - INTERIOR_MARGIN_MM:
            edge_ys.append(y)
            y = snap_to_grid(y + KICAD_GRID_MM)
    # Dedup while preserving order.
    seen_edge_ys: set[float] = set()
    edge_ys_unique = [y for y in edge_ys if not (y in seen_edge_ys or seen_edge_ys.add(y))]
    for ey in edge_ys_unique:
        candidates.append(_HlabelCandidate(
            position=Point(target_edge_x, ey),
            rotation=edge_rotation,
            route_from=Point(anchor_x, anchor_y),
            kind="sheet_edge",
        ))

    # 4. TOP / BOTTOM sheet-edge candidates — vertical-route fallback
    # for dense blocks where the LEFT/RIGHT routes can't escape the
    # connector region. Hier-labels at top/bottom rotate 270/90 so
    # text reads OFF-PAGE vertically.
    top_y = snap_to_grid(INTERIOR_MARGIN_MM)
    bottom_y = snap_to_grid(paper_h - INTERIOR_MARGIN_MM)
    x_steps = [anchor_x]
    for step in range(1, HLABEL_TOP_BOTTOM_LADDER_STEPS + 1):
        for sign in (1, -1):
            x_steps.append(snap_to_grid(anchor_x + sign * step * KICAD_GRID_MM))
    # Dedup X candidates.
    seen_xs: set[float] = set()
    x_steps_unique = [x for x in x_steps if not (x in seen_xs or seen_xs.add(x))]
    for x in x_steps_unique:
        # TOP candidate (rotation 270 = text reads downward, off-page top)
        candidates.append(_HlabelCandidate(
            position=Point(x, top_y),
            rotation=270.0,
            route_from=Point(anchor_x, anchor_y),
            kind="top_edge",
        ))
        # BOTTOM candidate (rotation 90 = text reads upward, off-page bottom)
        candidates.append(_HlabelCandidate(
            position=Point(x, bottom_y),
            rotation=90.0,
            route_from=Point(anchor_x, anchor_y),
            kind="bottom_edge",
        ))

    return candidates


def _first_clean_candidate(
    candidates: list[_HlabelCandidate],
    *,
    builder: BlockLayoutBuilder,
    net: ExternalNet,
    anchor_label_owner_id: str,
    same_net_label_owner_ids: frozenset[str],
    route_avoid_owners: frozenset[str],
    forbidden_traversal_points: frozenset[tuple[float, float]],
    reserved_endpoints: set[tuple[float, float]],
    failures_log: list | None = None,
):
    """Return ``(candidate, route_segments)`` for the first clean candidate.

    Probes each candidate's hier-label text bbox against live
    occupancy AND probes the routing extension (if any) for cleanliness.
    Returns ``None`` when every candidate fails. When ``failures_log``
    is provided, appends ``(candidate, reason, blocker_owner_id)`` for
    each failed candidate — useful for diagnostics.

    Pure-functional: no in-loop control flow. The generator-expression-
    with-``next`` pattern mirrors :func:`_first_clean_route` in
    ``place.py:213-235``.
    """
    from zynq_eda.core.layout._builder import _hierarchical_label_bbox
    from zynq_eda.core.layout.bbox import wire_bbox
    from zynq_eda.core.route.router import route_orthogonal_detail
    from zynq_eda.core.validate.overlap import _overlap_is_significant

    NOISE = OVERLAP_NOISE_FLOOR_MM

    def _try(cand: _HlabelCandidate):
        # Reject candidates whose endpoint is already reserved.
        endpoint_key = (cand.position.x, cand.position.y)
        if endpoint_key in reserved_endpoints:
            if failures_log is not None:
                failures_log.append((cand, "endpoint_reserved", None))
            return None

        # Probe hier-label text bbox against the live occupancy.
        prospective = PlacedHierarchicalLabel(
            net_name=net.name,
            position=cand.position,
            direction=net.direction,
            rotation=cand.rotation,
        )
        bbox = _hierarchical_label_bbox(prospective)
        # STRICT rule: the hier-label's text bbox must not overlap
        # ANYTHING in live occupancy. The ONLY exemption is the
        # anchor local label that is about to be REMOVED (the
        # hier-label is replacing it; the local label's bbox is
        # phantom from this point onward and stripped from
        # occupancy below). Junctions / no-connects are not text
        # bboxes — they're 0.5 mm dots that don't impede label
        # placement and are intentionally not flagged as overlaps.
        hits = builder.occupancy.collides(
            bbox,
            ignore_owners=frozenset({anchor_label_owner_id}),
            ignore_kinds=frozenset({"junction", "no_connect"}),
        )
        significant = [h for h in hits if _overlap_is_significant(bbox, h)]
        if significant:
            if failures_log is not None:
                failures_log.append((cand, "bbox_blocked", significant[0].owner_id))
            return None

        # No extension needed — endpoint coincides with anchor.
        if cand.route_from is None:
            return (cand, [])

        # Extension route required. STRICT: only the anchor local
        # label (about to be removed) is exempt. Other same-net
        # local labels remain obstacles — a route passing through
        # one would be a visual wire×label overlap the validator
        # (correctly) flags.
        attempt = route_orthogonal_detail(
            cand.route_from,
            cand.position,
            builder.occupancy,
            avoid_owners=frozenset({anchor_label_owner_id}) | route_avoid_owners,
            forbidden_traversal_points=forbidden_traversal_points,
        )
        if attempt.gave_up:
            if failures_log is not None:
                failures_log.append((cand, "route_gave_up", None))
            return None

        # The route's own segments must not enter the new label bbox at
        # a non-endpoint location.
        for seg in attempt.segments:
            seg_bb = wire_bbox(
                start=seg.start, end=seg.end,
                thickness_mm=WIRE_THICKNESS_MM, clearance_mm=0.0,
                owner_id="probe_seg",
            )
            inter = bbox.intersection(seg_bb)
            if inter and inter.width >= NOISE and inter.height >= NOISE:
                # The route's wire goes through the new label's bbox.
                # Endpoint contact (router terminates AT cand.position)
                # produces a bbox-edge graze well below NOISE; only an
                # interior crossing of >= NOISE width AND height fails.
                if failures_log is not None:
                    failures_log.append((cand, "route_through_bbox", None))
                return None
        return (cand, list(attempt.segments))

    attempts = (_try(c) for c in candidates)
    clean = (r for r in attempts if r is not None)
    return next(clean, None)


def _orphan_net_labels(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    left_x: float,
    right_x: float,
    paper_w: float,
    seen_label_positions: set[tuple[float, float]],
) -> None:
    """Surface declared external_nets via a hier-label at a clean spot.

    For each declared external_net with no hier-label yet:
      1. Locate the same-name local label (anchor).
      2. Build a CANDIDATE LADDER via ``_enumerate_hlabel_candidates``:
         in-place → perpendicular Y-offset → sheet-edge with Y ladder.
      3. Pick the FIRST candidate whose hier-label text bbox is clear
         of live occupancy AND whose extension route (if any) is clean.
      4. Hard-fail with a structured diagnostic when every candidate
         fails — surface the upstream layout fix needed.

    No in-loop skips: ``_first_clean_candidate`` is a pure function
    using the ``next(gen)`` pattern.
    """
    paper_h = PAPER_DIMENSIONS_MM[block.paper_size][1]

    already_labeled = {label.net_name for label in builder.hierarchical_labels}
    local_labels_by_name: dict[str, list] = {}
    for lab in builder.labels:
        local_labels_by_name.setdefault(lab.net_name, []).append(lab)

    def _anchor_priority(lab) -> float:
        return min(lab.position.x - left_x, right_x - lab.position.x)

    # Compute the connector-pin Y range (used to prefer sheet-edge
    # candidates OUTSIDE this range so hier-labels land in clear
    # off-pin Y space). Y range is taken from ALL local labels —
    # those sit at real connector pin tails / cluster trunk-ends, so
    # their Y range maps the dense routing band.
    pin_y_range: tuple[float, float] | None = None
    label_ys = [lab.position.y for lab in builder.labels]
    if label_ys:
        pin_y_range = (min(label_ys), max(label_ys))

    # All OTHER local-label positions become forbidden traversal points
    # so an extension route can't accidentally touch another net's
    # anchor (which would short two nets together).
    all_anchor_positions = {
        (round(lab.position.x, 3), round(lab.position.y, 3))
        for lab in builder.labels
    }

    reserved_endpoints: set[tuple[float, float]] = set(seen_label_positions)

    # Build the per-net work list UPFRONT (pre-filter, no in-loop skips).
    # GND nets are already handled by ``_ground_label_only`` (which ran
    # before us and added them to ``already_labeled`` or skipped them
    # entirely if a power:GND symbol drives the sheet's global net).
    work_items = [
        (net, min(local_labels_by_name[net.name], key=_anchor_priority))
        for net in block.external_nets
        if net.name not in already_labeled
        and net.name in local_labels_by_name
    ]

    for net, anchor_label in work_items:
        # Compute rotation for SHEET-EDGE candidates from the declared
        # net edge (text reads outward off-page at the sheet boundary).
        # For IN-PLACE / Y-OFFSET candidates, the candidate ladder uses
        # the LOCAL label's rotation (text reads outward from the host
        # symbol body — the cluster/connector that owns the local
        # label). See ``_enumerate_hlabel_candidates`` for the split.
        edge_rotation = (
            180.0 if getattr(net, "edge", SheetEdge.LEFT) == SheetEdge.LEFT
            else 0.0
        )
        target_edge_x = (
            left_x if getattr(net, "edge", SheetEdge.LEFT) == SheetEdge.LEFT
            else right_x
        )

        anchor_key = (round(anchor_label.position.x, 3),
                      round(anchor_label.position.y, 3))
        anchor_owner_id = (
            f"label:{anchor_label.net_name}@"
            f"{anchor_label.position.x:.1f},{anchor_label.position.y:.1f}"
        )
        # Same-net labels: ALL local labels with this net_name are
        # electrically equivalent — overlap-checks should ignore them
        # as obstacles (a hier-label bbox or extension wire that
        # overlaps a same-net local label IS connecting to the same
        # net; no validator overlap concern).
        same_net_label_owner_ids = frozenset(
            f"label:{lab.net_name}@{lab.position.x:.1f},{lab.position.y:.1f}"
            for lab in local_labels_by_name.get(net.name, [])
        )
        # Forbidden traversal points: other nets' local label positions
        # (so an extension route can't accidentally tie ours into theirs).
        forbidden_pts = frozenset(
            pt for pt in all_anchor_positions
            if pt != anchor_key
            and pt not in {
                (round(l.position.x, 3), round(l.position.y, 3))
                for l in local_labels_by_name.get(net.name, [])
            }
        )

        candidates = _enumerate_hlabel_candidates(
            net=net,
            anchor_label=anchor_label,
            edge_rotation=edge_rotation,
            target_edge_x=target_edge_x,
            pin_y_range=pin_y_range,
            paper_h=paper_h,
        )

        failures_log: list = []
        picked = _first_clean_candidate(
            candidates,
            builder=builder,
            net=net,
            anchor_label_owner_id=anchor_owner_id,
            same_net_label_owner_ids=same_net_label_owner_ids,
            route_avoid_owners=frozenset(),
            forbidden_traversal_points=forbidden_pts,
            reserved_endpoints=reserved_endpoints,
            failures_log=failures_log,
        )

        if picked is None:
            # Build a categorised failure summary.
            from collections import Counter
            reasons = Counter(reason for _c, reason, _b in failures_log)
            blockers = Counter(
                blocker for _c, _r, blocker in failures_log
                if blocker is not None
            )
            top_blockers = blockers.most_common(5)
            # Show 3 representative failed candidates (one per kind).
            by_kind: dict[str, str] = {}
            for cand, reason, blocker in failures_log:
                if cand.kind not in by_kind:
                    by_kind[cand.kind] = (
                        f"{cand.kind} @ ({cand.position.x:.1f},"
                        f"{cand.position.y:.1f}) → {reason}"
                        + (f" [blocked by {blocker}]" if blocker else "")
                    )
            sample = "; ".join(by_kind.values())
            raise RuntimeError(
                f"_orphan_net_labels: no clean candidate for net "
                f"{net.name!r} (anchor local label @ "
                f"{anchor_label.position}, rotation={anchor_label.rotation}, "
                f"net.edge rotation={edge_rotation}). "
                f"Tried {len(candidates)} candidates. "
                f"Failure reasons: {dict(reasons)}. "
                f"Top blocking owners: {top_blockers}. "
                f"Sample failures: {sample}. "
                f"Upstream fix: widen the cluster channel "
                f"(PASSIVE_OFFSET_MM in _constants.py), move the IC "
                f"anchor, relocate the connector, or declare the net "
                f"on the opposite sheet edge."
            )

        cand, segments = picked

        # Emit the extension wires (if any).
        for seg in segments:
            builder.add_wire(seg)

        # Place the hier-label using the CANDIDATE's rotation (which
        # is the local label's rotation for in-place / y_offset, the
        # net-edge convention rotation for sheet_edge).
        builder.add_hierarchical_label(PlacedHierarchicalLabel(
            net_name=net.name,
            position=cand.position,
            direction=net.direction,
            rotation=cand.rotation,
        ))

        # Strip the now-redundant local label (it's been replaced by
        # the hier-label in the net's electrical role). Remove its
        # bbox from occupancy so subsequent passes don't see a stale
        # text-bbox blocking new routes.
        try:
            builder.labels.remove(anchor_label)
            builder.occupancy.remove_by_owner(anchor_owner_id)
        except ValueError:
            pass

        reserved_endpoints.add((cand.position.x, cand.position.y))
        seen_label_positions.add((cand.position.x, cand.position.y))


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

        # If a same-name LOCAL label exists, ``_orphan_net_labels`` will
        # promote it to a hier-label via the candidate ladder (which
        # picks a position that doesn't overlap any wire/symbol). We
        # do NOT directly emit the hier-label here — that would skip
        # the ladder's bbox-clearance probe and risk wire×hlabel
        # overlaps (boot_switches' GND was hit by this).
        matching = local_labels_by_name.get(ground_net.name)
        if matching:
            # Defer to ``_orphan_net_labels`` — its candidate ladder
            # picks a position that doesn't overlap any wire/symbol.
            # Direct emission here would put the hier-label AT the
            # local label coord (a wire endpoint), but the wire body
            # extending past that endpoint can graze the hier-label
            # text bbox (boot_switches GND hit this).
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
