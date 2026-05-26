"""Hierarchical-label placement at sheet edges.

Each :class:`ExternalNet` declared on a block becomes one or more
hierarchical labels on the configured edge of the sub-sheet. Power-input
nets also get one ``power:PWR_FLAG`` per net so ERC accepts the sub-sheet
standalone (without a populated parent sheet).

Ground nets share one bottom-edge label and a single PWR_FLAG.
"""

from __future__ import annotations

from zynq_eda.core.layout._builder import BlockLayoutBuilder, PinGeometryAbs
from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM, POWER_SYMBOL_OFFSET_MM
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
from zynq_eda.core.route.router import route_orthogonal


def place_external_nets(
    builder: BlockLayoutBuilder,
    *,
    block: Block,
    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]],
    ic_anchors: dict[str, Point],
    geometry_cache: SymbolGeometryCache,
) -> set[tuple[str, str]]:
    """Place per-IC hierarchical labels + PWR_FLAGs.

    Returns the set of ``(ic_reference, pin_name)`` pairs that already
    received an edge-label wiring, so :func:`place._attach_ic_signal_overrides`
    can skip them and avoid creating duplicate connections.
    """
    paper_w, _paper_h = PAPER_DIMENSIONS_MM[block.paper_size]
    left_x = snap_to_grid(INTERIOR_MARGIN_MM)
    right_x = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)

    declared_nets: dict[str, ExternalNet] = {net.name: net for net in block.external_nets}

    seen_label_positions: set[tuple[float, float]] = set()
    edge_labeled: set[tuple[str, str]] = _per_ic_pin_labels(
        builder,
        block=block,
        declared_nets=declared_nets,
        ic_pin_geometries=ic_pin_geometries,
        ic_anchors=ic_anchors,
        geometry_cache=geometry_cache,
        left_x=left_x,
        right_x=right_x,
        seen_label_positions=seen_label_positions,
    )

    # Power-rail drivers (power:PWR_FLAG, root-level power:GND) live on
    # the *root* sheet now — see :mod:`zynq_eda.core.layout.root`. Emitting
    # them per-block produces duplicate drivers once the blocks merge in
    # the project hierarchy ("Power output × Power output" pin_to_pin
    # errors). The sub-sheet still emits the ground HIERARCHICAL LABEL
    # so the GND net can leave the sheet; the root sheet's power symbol
    # then drives it across the whole hierarchy.
    _ground_label_only(
        builder,
        block=block,
        ic_anchors=ic_anchors,
        left_x=left_x,
        right_x=right_x,
        seen_label_positions=seen_label_positions,
    )

    # Surface every declared external_net that didn't already get a hier
    # label via IC pin overrides. Anchor each orphan hier label AT an
    # existing same-name local label's coordinate, so KiCad merges the
    # hier label and the local label into one net (the local label is
    # already on a real wire endpoint inside the sub-sheet — anything
    # else dangles the hier label per ERC).
    _orphan_net_labels(
        builder,
        block=block,
        left_x=left_x,
        right_x=right_x,
        paper_w=paper_w,
        seen_label_positions=seen_label_positions,
    )

    return edge_labeled


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

        # Compute the IC's body bbox y range so the dogleg avoidance
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
        except Exception:
            ic_body_y_range = None

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

        for pin_role, net_name in candidates:
            if net_name not in declared_nets:
                # Pin's override doesn't match an external net — leave it
                # for the signal-override pass to handle as a local label.
                continue
            if pin_role in ic_geoms:
                pin_connection = ic_geoms[pin_role].connection
            else:
                # Pin has no external-part cluster, so it wasn't recorded in
                # ``ic_geoms``. Resolve directly from the symbol library so
                # signal-only override pins (e.g. TPS2051 EN) still get a
                # hierarchical edge label when their target net is external.
                # Without this, the pin's hier label gets created later by
                # ``_orphan_net_labels`` at the local-label coord -- which
                # may sit on a wire already carrying a different net and
                # produce a ``multiple_net_names`` ERC warning.
                try:
                    pin_geom = geometry_cache.pin_geometry_by_name(
                        ic.lib_id,
                        ic_anchors[ic.reference],
                        pin_role,
                    )
                except KeyError:
                    # Pin missing from the symbol (refcircuit name mismatch).
                    continue
                pin_connection = pin_geom.connection
            net = declared_nets[net_name]
            label_x = left_x if net.edge == SheetEdge.LEFT else right_x

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
            )

            label_position = Point(label_x, route_y)
            key = (label_position.x, label_position.y)
            if key in seen_label_positions:
                # Two IC pins want the same edge label slot — leave the
                # second one for signal-override (it'll get a local label).
                continue
            seen_label_positions.add(key)

            rotation = 180.0 if net.edge == SheetEdge.LEFT else 0.0
            builder.add_hierarchical_label(PlacedHierarchicalLabel(
                net_name=net_name,
                position=label_position,
                direction=net.direction,
                rotation=rotation,
            ))
            # Route from pin_connection to label_position, avoiding the
            # IC's own body bbox (the wire is BY DESIGN attached to one
            # of its pins, so the body overlap is expected and exempted).
            # The router considers OTHER symbol bodies as obstacles.
            ic_owner = f"symbol:{ic.reference}"
            if route_y == pin_y:
                # Straight horizontal — pin_connection y equals
                # label_position y. The router picks "direct" if clear,
                # falls back to single-L / double-L if it has to detour
                # around an obstacle.
                segments = route_orthogonal(
                    pin_connection,
                    label_position,
                    builder.occupancy,
                    avoid_owners=frozenset({ic_owner}),
                )
            else:
                # Dogleg pre-computed Y: route through (pin.x, route_y)
                # then horizontally to the label. We do the dogleg by
                # hand so the pin-crossing-avoidance logic stays
                # respected (the router only does collision avoidance,
                # not pin-crossing detection).
                turn = Point(snap_to_grid(pin_connection.x), route_y)
                segments = [
                    PlacedWire(start=pin_connection, end=turn),
                    PlacedWire(start=turn, end=label_position),
                ]
            for seg in segments:
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
) -> float:
    """Pick a Y for the edge-bound segment that avoids crossing other pins.

    Default is the pin's own Y (straight wire). If any OTHER pin of the
    same IC sits at the pin's Y between ``pin_x`` and ``target_x`` (the
    edge segment's X range), pick the nearest grid step above or below
    that is free of pin crossings on that span. Falls back to ``pin_y``
    if no clean slot exists within a small search window.

    When ``ic_body_y_range`` is supplied (``(min_y, max_y)`` of the IC
    body bbox), candidate Ys INSIDE that range are also skipped — the
    dogleg shouldn't route a wire through the body it's escaping from.
    The body-Y exclusion only applies to candidates OTHER than ``pin_y``
    (which by definition is inside the body's Y range and IS where the
    pin sits — that's the legitimate path out).

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
            if abs(other.x - pin_x) < EPS and abs(other.y - pin_y) < EPS:
                # Same pin — skip (the source we're routing from).
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

    pin_y_snapped = snap_to_grid(pin_y)
    if not pin_collides(pin_y_snapped) and not is_blocked(pin_y_snapped):
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
    for net in block.external_nets:
        if net.power_kind not in ("input", "output"):
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
        if net.name in flag_emitted_for_net:
            continue
        flag_emitted_for_net.add(net.name)

        anchor_label = next(
            (label for label in builder.hierarchical_labels if label.net_name == net.name),
            None,
        )
        if anchor_label is None:
            continue

        flag_offset = -3.81 if net.edge == SheetEdge.LEFT else 3.81
        flag_position = Point(
            snap_to_grid(anchor_label.position.x + flag_offset),
            anchor_label.position.y,
        )
        builder.add_wire(PlacedWire(
            start=anchor_label.position,
            end=flag_position,
        ))
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
        anchor_label = matching[0]
        key = (anchor_label.position.x, anchor_label.position.y)
        if key in seen_label_positions:
            continue
        seen_label_positions.add(key)
        # Inherit the local label's rotation — it was already chosen so
        # the text reads OUTWARD from the host pin (so the bbox extends
        # away from the host symbol body). Stamping the hier label with
        # the same rotation keeps its text on the same side as the
        # local label it's replacing.
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
            matching.pop(0)
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
            # Inherit the local label's rotation so the hier label text
            # reads in the same outward direction (away from the host
            # symbol body). See ``_orphan_net_labels`` for the rationale.
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
            existing_ys = {
                lab.position.y for lab in builder.hierarchical_labels
            }

            def _y_distance_score(sym: PlacedSymbol) -> float:
                if not existing_ys:
                    return 0.0
                # Higher score = more distant Y. min-distance ascending.
                return -min(abs(sym.position.y - ey) for ey in existing_ys)

            anchor_sym = min(matching_syms, key=_y_distance_score)
            key = (anchor_sym.position.x, anchor_sym.position.y)
            if key in seen_label_positions:
                continue
            seen_label_positions.add(key)
            rotation = 180.0 if ground_net.edge == SheetEdge.LEFT else 0.0
            builder.add_hierarchical_label(PlacedHierarchicalLabel(
                net_name=ground_net.name,
                position=anchor_sym.position,
                direction=ground_net.direction,
                rotation=rotation,
            ))
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
