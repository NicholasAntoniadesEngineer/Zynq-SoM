"""Per-block placement orchestrator.

Takes a declarative :class:`Block` and produces a placed :class:`Sheet`.
The actual work is delegated to:

  * :mod:`zynq_eda.core.layout.cluster` — per-IC passive clustering.
  * :mod:`zynq_eda.core.layout.connectors` — per-block connector placement.
  * :mod:`zynq_eda.core.layout.edge_labels` — hierarchical labels at sheet
    edges + PWR_FLAGs for ERC.

Current limitations (lifted progressively in Stage 5+):

  * Single A4 page per block — no auto-pagination yet.
  * IC anchors picked from a simple vertical column heuristic; multi-IC
    blocks may need explicit ``layout_hint`` overrides on
    :class:`IcInstance` until the region packer lands.
  * Wires use direct point-to-point routing; no A* obstacle avoidance.
"""

from __future__ import annotations

from typing import Literal

from zynq_eda.core.layout._builder import BlockLayoutBuilder, PinGeometryAbs
from zynq_eda.core.layout.cluster import cluster_ic_externals
from zynq_eda.core.layout.connectors import place_connectors
from zynq_eda.core.layout.edge_labels import place_external_nets
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.block import Block, IcInstance
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import PlacedSymbol, PlacedWire, Sheet


def _ic_anchors_for_block(
    block: Block,
    *,
    column_x: float,
    top_y: float,
    row_pitch: float,
    geometry_cache: "SymbolGeometryCache | None" = None,
) -> dict[str, Point]:
    """Place ICs in a single vertical column with bbox-aware spacing.

    For each IC after the first, compute the next anchor as:
      prev_anchor.y + prev_ic_half_height + cap_chain_clearance
                    + next_ic_half_height
    so that the IC's body + its TOP-side decoupling cap chain don't
    collide with the prior IC. Falls back to the static ``row_pitch``
    when ``geometry_cache`` is unavailable or the IC's lib_id can't
    be resolved.
    """
    anchors: dict[str, Point] = {}
    # Top-side cap chain clearance: PASSIVE_OFFSET (10.16) + stagger
    # (5.08) + cap-body-half (3.81) + power-symbol stub (5.08) +
    # 2 grid-unit safety margin (5.08). Caps a TOP-attached cap chain
    # reaches roughly this far above the IC's top edge.
    CAP_CHAIN_CLEARANCE_MM = 29.21

    current_y = top_y
    prev_max_y_extent = 0.0  # half-height of previous IC (from anchor downward)
    for index, ic in enumerate(block.ics):
        # Compute this IC's half-heights (above + below anchor).
        ic_half_up = 0.0
        ic_half_down = 0.0
        if geometry_cache is not None:
            try:
                bbox = geometry_cache.bounding_box(ic.lib_id, rotation=0.0)
                ic_half_up = abs(bbox.min_y)   # min_y is negative (above anchor)
                ic_half_down = abs(bbox.max_y) # max_y is positive (below anchor)
            except Exception:
                pass

        if index == 0:
            anchor_y = top_y
        else:
            # Next anchor sits at:
            #   prev_anchor.y + prev_ic_half_down + cap_chain_clearance
            #     + this_ic_half_up
            # (prev_max_y_extent already captures prev_ic_half_down)
            anchor_y = current_y + prev_max_y_extent + CAP_CHAIN_CLEARANCE_MM + ic_half_up
            # Fall back to static pitch if bbox-aware result would be tighter
            # than the safe minimum (shouldn't normally happen).
            anchor_y = max(anchor_y, current_y + row_pitch)

        anchor_y = snap_to_grid(anchor_y)
        anchors[ic.reference] = Point(snap_to_grid(column_x), anchor_y)
        current_y = anchor_y
        prev_max_y_extent = ic_half_down

    return anchors


def _place_ic_body(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache | None = None,
) -> None:
    """Append the IC body's :class:`PlacedSymbol` to the builder."""
    builder.add_symbol(PlacedSymbol(
        lib_id=ic.lib_id,
        reference=ic.reference,
        value=ic.refcircuit.part_mpn,
        position=ic_anchor,
        footprint=ic.refcircuit.footprint,
        rotation=0.0,
        properties=(
            ("LCSC", ic.refcircuit.lcsc),
            ("Datasheet", ic.refcircuit.datasheet_url),
        ),
    ), geometry=geometry_cache)


# ============================================================================
# Unified per-pin handler — ONE pipeline per pin, ZERO skip flags
#
# Every IC pin not handled by the cluster pass flows through ONE classifier
# and ONE emitter. The classifier partitions pins into exclusive categories
# (CLUSTER, GND, EDGE_LABEL, POWER_SYMBOL, LOCAL_LABEL, NC) BEFORE any
# emission happens. Each emitter iterates a PRE-FILTERED list with no
# in-loop ``continue``. All wires route through ``route_orthogonal_detail``;
# routing failures hard-fail with diagnostics. No fallback to another
# handler — the classification IS the dispatch.
# ============================================================================

_GND_PIN_NAME_PATTERNS = ("GND", "VSS", "GNDA", "AGND", "DGND")
_POWER_INPUT_PIN_NAMES = ("IN", "VDD", "VCC", "VBUS", "AVDD", "DVDD", "PVIN", "ANODE")
_POWER_OUTPUT_PIN_NAMES = ("OUT", "VOUT", "CATHODE")


def _is_gnd_pin_name(pin_name: str) -> bool:
    """True iff ``pin_name`` belongs to the GND-family naming convention.

    Matches plain ``GND``/``VSS``/``GNDA``/``AGND``/``DGND`` AND the
    ``<PATTERN>_*`` form (e.g. ``GND_EP``, ``GND_2``).
    """
    name_upper = pin_name.upper()
    return (
        name_upper in _GND_PIN_NAME_PATTERNS
        or any(name_upper.startswith(p + "_") for p in _GND_PIN_NAME_PATTERNS)
    )


def _compute_pin_net(pin_name: str, ic: IcInstance) -> str:
    """Resolve which net an IC pin is on.

    Priority order: ``refcircuit.pin_net_overrides`` | per-instance
    ``net_overrides`` win first; then ``power_input_net`` for the
    canonical input-pin names; then ``power_output_net`` for output
    names. Returns the empty string when no mapping applies — the
    caller's classifier then routes the pin to ``NC``.

    Pure function. No I/O, no occupancy reads.
    """
    overrides = dict(ic.refcircuit.pin_net_overrides) | dict(
        getattr(ic, "net_overrides", ()) or ()
    )
    direct = overrides.get(pin_name, "")
    if direct:
        return direct
    if pin_name in _POWER_INPUT_PIN_NAMES and ic.power_input_net:
        return ic.power_input_net
    if pin_name in _POWER_OUTPUT_PIN_NAMES and ic.power_output_net:
        return ic.power_output_net
    return ""


def _classify_pin(
    pin_name: str,
    ic: IcInstance,
    declared_nets: dict,
    *,
    in_cluster: bool,
) -> tuple[str, str]:
    """Classify a pin into EXACTLY ONE category and return (category, net).

    Mutually exclusive categories, evaluated in priority order:

      1. ``CLUSTER`` — pin appears in ``ic.refcircuit.external_parts``.
         The cluster pass owns it. This dispatcher does nothing for it.
      2. ``GND`` — pin name is GND-family (``_is_gnd_pin_name``).
      3. ``EDGE_LABEL`` — pin's net is in ``block.external_nets``
         (a declared sheet-edge net).
      4. ``POWER_SYMBOL`` — pin's net is in ``POWER_SYMBOL_LIB_IDS``
         but not declared external.
      5. ``LOCAL_LABEL`` — pin has a named net but none of the above.
      6. ``NC`` — no net mapping at all.

    Pure function. No mutation.
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS as _PWR
    if in_cluster:
        return "CLUSTER", _compute_pin_net(pin_name, ic)
    if _is_gnd_pin_name(pin_name):
        return "GND", "GND"
    net = _compute_pin_net(pin_name, ic)
    if not net:
        return "NC", ""
    if net in declared_nets:
        return "EDGE_LABEL", net
    if net in _PWR:
        return "POWER_SYMBOL", net
    return "LOCAL_LABEL", net


def _first_clean_route(
    start: Point,
    end_candidates: list[Point],
    occupancy,
    *,
    avoid_owners: frozenset[str],
    forbidden_traversal_points: frozenset[tuple[float, float]],
):
    """Return the FIRST clean route from ``start`` to any of ``end_candidates``.

    The Y-search candidate ladder is folded into this single helper so the
    EDGE_LABEL emitter can express its routing as "give me the first
    clean candidate or None" — a pure functional form with NO in-loop
    ``continue`` on the caller's side.

    Returns ``(end_point, RouteAttempt)`` for the first non-gave-up
    attempt; ``None`` if every candidate failed.
    """
    from zynq_eda.core.route.router import route_orthogonal_detail
    attempts = (
        (end, route_orthogonal_detail(
            start, end, occupancy,
            avoid_owners=avoid_owners,
            forbidden_traversal_points=forbidden_traversal_points,
        ))
        for end in end_candidates
    )
    clean = ((e, r) for (e, r) in attempts if not r.gave_up)
    return next(clean, None)


# --- Per-category emitters --------------------------------------------------

def _emit_gnd_pin(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    pin_geom: PinGeometryAbs,
    pin_number: str,
    geometry_cache: SymbolGeometryCache,
) -> None:
    """Emit ONE ``power:GND`` symbol + wire for a single GND-family pin.

    Symbol position is laterally outboard when the pin has a non-zero
    relative X (multi-pin sides), else vertically outboard. Routing goes
    through ``route_orthogonal_detail``; raises ``RuntimeError`` on
    unrouteability (no fallback).
    """
    from zynq_eda.core.route.router import route_orthogonal_detail
    from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
    from zynq_eda.core.layout.cluster import _outward_power_symbol_rotation

    OFFSET = 5.08
    rel = pin_geom.relative
    if rel.x != 0.0:
        outward_side: Literal["left", "right", "top", "bottom"] = (
            "left" if rel.x < 0 else "right"
        )
        gnd_pos = Point(
            snap_to_grid(
                pin_geom.connection.x + (-OFFSET if rel.x < 0 else OFFSET)
            ),
            pin_geom.connection.y,
        )
    else:
        outward_side = "top" if rel.y > 0 else "bottom"
        page_dy_dir = -1 if rel.y > 0 else 1
        gnd_pos = Point(
            pin_geom.connection.x,
            snap_to_grid(pin_geom.connection.y + page_dy_dir * OFFSET),
        )

    avoid: set[str] = {f"symbol:{ic.reference}"}
    if pin_number:
        avoid |= set(pin_intrinsic_owner_ids(ic.reference, (pin_number,)))

    route = route_orthogonal_detail(
        pin_geom.connection,
        gnd_pos,
        builder.occupancy,
        avoid_owners=frozenset(avoid),
    )
    if route.gave_up:
        raise RuntimeError(
            f"_emit_gnd_pin: router gave up routing IC {ic.reference!r} "
            f"GND pin @ {pin_geom.connection} → symbol @ {gnd_pos}. "
            f"Upstream: move the IC anchor or widen the channel."
        )
    for seg in route.segments:
        builder.add_wire(seg)

    rotation = _outward_power_symbol_rotation(
        lib_id="power:GND",
        pin_side=outward_side,
        geometry_cache=geometry_cache,
    )
    builder.add_symbol(PlacedSymbol(
        lib_id="power:GND",
        reference=builder.next_ref("#PWR"),
        value="GND",
        position=gnd_pos,
        footprint="",
        rotation=rotation,
    ), geometry=geometry_cache)


def _emit_edge_label_pin(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    pin_geom: PinGeometryAbs,
    pin_number: str,
    net_name: str,
    declared_nets: dict,
    forbidden_traversal_points: frozenset[tuple[float, float]],
    label_x_left: float,
    label_x_right: float,
    geometry_cache: SymbolGeometryCache,
    reserved_label_ys: set[float],
) -> float:
    """Route the pin → hier-label at the appropriate sheet edge.

    Builds a Y-candidate ladder PRE-FILTERED to skip Ys already reserved
    by sibling EDGE_LABEL pins on the same IC (set-membership, NOT an
    in-loop skip). The first non-gave-up route from `_first_clean_route`
    wins. Hard-fails with a diagnostic when no candidate routes cleanly.

    Returns the Y of the picked endpoint so the dispatcher can update
    ``reserved_label_ys`` for the next pin's allocation.
    """
    from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
    from zynq_eda.core.model.sheet import PlacedHierarchicalLabel
    from zynq_eda.core.model.block import SheetEdge

    net = declared_nets[net_name]
    label_x = label_x_left if net.edge == SheetEdge.LEFT else label_x_right

    # Exempt ONLY the source pin's intrinsic text bboxes — NOT the IC
    # body. Exempting the body would let the router route the wire
    # straight through the IC body's interior (USBLC6 I/O2 → LEFT-edge
    # USB_DM label crosses U2 body). The router must dogleg AROUND
    # the body via Z-bend offsets.
    avoid: set[str] = set()
    if pin_number:
        avoid |= set(pin_intrinsic_owner_ids(ic.reference, (pin_number,)))

    pin_y = snap_to_grid(pin_geom.connection.y)
    Y_LADDER_STEPS = 15
    Y_STEP_MM = 2.54
    raw_candidates = [pin_y] + [
        snap_to_grid(pin_y + sign * step * Y_STEP_MM)
        for step in range(1, Y_LADDER_STEPS + 1)
        for sign in (1, -1)
    ]
    # PRE-FILTER (not in-loop skip): drop Ys already reserved by other
    # EDGE_LABEL pins on this IC. Two pins at the same Y would land
    # hier-labels on top of each other; the partition happens upfront.
    candidates = [
        Point(label_x, y) for y in raw_candidates if y not in reserved_label_ys
    ]

    picked = _first_clean_route(
        pin_geom.connection,
        candidates,
        builder.occupancy,
        avoid_owners=frozenset(avoid),
        forbidden_traversal_points=forbidden_traversal_points,
    )
    if picked is None:
        raise RuntimeError(
            f"_emit_edge_label_pin: no clean route for IC {ic.reference!r} "
            f"pin #{pin_number} (net {net_name!r}) from "
            f"{pin_geom.connection} to any unreserved Y at X={label_x}. "
            f"reserved_label_ys={sorted(reserved_label_ys)}. "
            f"forbidden_traversal_points={sorted(forbidden_traversal_points)}. "
            f"Upstream: move the IC anchor, widen the cluster channel, "
            f"or drop the override."
        )
    end_point, route = picked
    for seg in route.segments:
        builder.add_wire(seg)
    rotation = 180.0 if net.edge == SheetEdge.LEFT else 0.0
    builder.add_hierarchical_label(PlacedHierarchicalLabel(
        net_name=net_name,
        position=end_point,
        direction=net.direction,
        rotation=rotation,
    ))
    return end_point.y


def _emit_power_symbol_pin(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    pin_geom: PinGeometryAbs,
    pin_number: str,
    net_name: str,
    geometry_cache: SymbolGeometryCache,
) -> None:
    """Place a power symbol AT the pin tip (no stub wire).

    The symbol's pin coincides with the IC pin tip; KiCad treats this
    as a direct connection. The symbol's body extends OUTWARD via
    ``_outward_power_symbol_rotation``.
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS
    from zynq_eda.core.layout.cluster import _outward_power_symbol_rotation
    from zynq_eda.core.layout.geometry import page_side_from_pin

    power_lib_id = POWER_SYMBOL_LIB_IDS[net_name]
    side = page_side_from_pin(
        pin_rotation=getattr(pin_geom, "pin_rotation", 0.0),
        symbol_rotation=getattr(pin_geom, "symbol_rotation", 0.0),
    )
    rotation = _outward_power_symbol_rotation(
        lib_id=power_lib_id, pin_side=side, geometry_cache=geometry_cache,
    )
    builder.add_symbol(PlacedSymbol(
        lib_id=power_lib_id,
        reference=builder.next_ref("#PWR"),
        value=net_name,
        position=pin_geom.connection,
        footprint="",
        rotation=rotation,
    ), geometry=geometry_cache)


def _emit_local_label_pin(
    builder: BlockLayoutBuilder,
    *,
    pin_geom: PinGeometryAbs,
    net_name: str,
) -> None:
    """Place a local net label AT the pin tip.

    Rotation chosen so text extends OUTWARD per pin's page side. No
    stub wire — Wave F convention (label anchors directly at pin tip).
    """
    from zynq_eda.core.model.sheet import PlacedLabel
    from zynq_eda.core.layout.geometry import page_side_from_pin

    side = page_side_from_pin(
        pin_rotation=getattr(pin_geom, "pin_rotation", 0.0),
        symbol_rotation=getattr(pin_geom, "symbol_rotation", 0.0),
    )
    rotation = {"left": 180.0, "right": 0.0, "top": 90.0, "bottom": 270.0}[side]
    builder.add_label(PlacedLabel(
        net_name=net_name,
        position=pin_geom.connection,
        rotation=rotation,
    ))


def _emit_nc_pin(
    builder: BlockLayoutBuilder,
    *,
    pin_geom: PinGeometryAbs,
) -> None:
    """Place a NoConnect marker at the pin tip."""
    from zynq_eda.core.model.sheet import PlacedNoConnect
    builder.no_connects.append(PlacedNoConnect(position=pin_geom.connection))


def _resolve_pin_geometry(
    ic: IcInstance, ic_anchor: Point, pin_number: str,
    geometry_cache: SymbolGeometryCache,
) -> "PinGeometryAbs | None":
    """One-shot resolver. Returns ``None`` when the geometry cache cannot
    place the pin (caller filters Nones via list comprehension upfront).
    Centralises the only ``try/except KeyError`` for pin geometry.
    """
    try:
        return geometry_cache.pin_geometry_by_name(ic.lib_id, ic_anchor, pin_number)
    except KeyError:
        return None


def _emit_ic_pin_connections(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache,
    block: Block,
) -> None:
    """ONE dispatcher for every IC pin not handled by the cluster.

    Pre-classifies all pins into ONE of {CLUSTER, GND, EDGE_LABEL,
    POWER_SYMBOL, LOCAL_LABEL, NC}, then iterates the pre-partitioned
    buckets to emit. NO in-loop ``continue``. NO cross-handler skip
    flags. Each pin is touched by EXACTLY ONE emitter.
    """
    from zynq_eda.core.model.sheet import PAPER_DIMENSIONS_MM
    from zynq_eda.core.layout._constants import INTERIOR_MARGIN_MM

    declared_nets = {n.name: n for n in block.external_nets}
    cluster_pins = {ext.from_pin for ext in ic.refcircuit.external_parts}
    paper_w, _ = PAPER_DIMENSIONS_MM[block.paper_size]
    label_x_left = snap_to_grid(INTERIOR_MARGIN_MM)
    label_x_right = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)

    # 1. Build pin records: resolve every pin's geometry up front, drop
    #    unresolvable ones via list comprehension. NO in-loop try/skip.
    ic_rotation = float(getattr(ic, "rotation", 0.0))
    pin_infos = list(geometry_cache.all_pins(ic.lib_id, rotation=ic_rotation))
    raw_records = [
        (str(pi["name"]), str(pi["number"]),
         _resolve_pin_geometry(ic, ic_anchor, str(pi["number"]), geometry_cache))
        for pi in pin_infos
    ]
    records = [(n, num, geom) for (n, num, geom) in raw_records if geom is not None]

    # 2. Forbidden traversal set for EDGE_LABEL routing — every pin tip
    #    on this IC. Each per-pin emission subtracts its own source.
    all_pin_positions = frozenset(
        (round(g.connection.x, 3), round(g.connection.y, 3))
        for (_n, _num, g) in records
    )

    # 3. Classify and partition into exclusive category buckets. The
    #    partitioning is the dispatch — no in-loop branches downstream.
    classified = [
        (n, num, geom,
         *_classify_pin(n, ic, declared_nets, in_cluster=(n in cluster_pins)))
        for (n, num, geom) in records
    ]
    buckets = {
        cat: [(n, num, geom, net)
              for (n, num, geom, c, net) in classified if c == cat]
        for cat in ("CLUSTER", "GND", "EDGE_LABEL",
                    "POWER_SYMBOL", "LOCAL_LABEL", "NC")
    }

    # 4. Dedup GND by tip coordinate UPFRONT — multiple physical pads
    #    sharing the same coord (e.g. CP2102N's GND + EP pad) collapse
    #    to ONE symbol. This is a SET operation, not a loop-skip.
    gnd_unique = {
        (round(geom.connection.x, 3), round(geom.connection.y, 3)):
            (n, num, geom, net)
        for (n, num, geom, net) in buckets["GND"]
    }

    # 5. Dispatch each bucket to its emitter. Every loop iterates a
    #    fully pre-filtered list — no ``continue``, no skip flags.
    for (_n, num, geom, _net) in gnd_unique.values():
        _emit_gnd_pin(
            builder, ic=ic, pin_geom=geom, pin_number=num,
            geometry_cache=geometry_cache,
        )
    # EDGE_LABEL pins on the same IC must each land at a DIFFERENT Y at
    # the sheet edge — otherwise their hier-labels stack at the same
    # anchor (USBLC6 I/O1+I/O2 share Y=147.32). ``reserved_label_ys``
    # is a growing set; the emitter pre-filters its Y candidate ladder
    # against it BEFORE picking a route. No in-loop skip.
    reserved_label_ys: set[float] = set()
    for (_n, num, geom, net) in buckets["EDGE_LABEL"]:
        forbidden = all_pin_positions - {
            (round(geom.connection.x, 3), round(geom.connection.y, 3))
        }
        picked_y = _emit_edge_label_pin(
            builder, ic=ic, pin_geom=geom, pin_number=num, net_name=net,
            declared_nets=declared_nets,
            forbidden_traversal_points=forbidden,
            label_x_left=label_x_left, label_x_right=label_x_right,
            geometry_cache=geometry_cache,
            reserved_label_ys=reserved_label_ys,
        )
        reserved_label_ys.add(picked_y)
    for (_n, num, geom, net) in buckets["POWER_SYMBOL"]:
        _emit_power_symbol_pin(
            builder, ic=ic, pin_geom=geom, pin_number=num, net_name=net,
            geometry_cache=geometry_cache,
        )
    for (_n, _num, geom, net) in buckets["LOCAL_LABEL"]:
        _emit_local_label_pin(builder, pin_geom=geom, net_name=net)
    for (_n, _num, geom, _net) in buckets["NC"]:
        _emit_nc_pin(builder, pin_geom=geom)


# ============================================================================
# Legacy handlers (to be deleted in step 7-8 of the unified-handler refactor)
# ============================================================================

def _attach_ic_ground(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache,
) -> PinGeometryAbs | None:
    """Wire every GND/VSS pin on the IC to a ``power:GND`` symbol.

    ICs like FUSB302 have *multiple* GND pins (GND, GND_2, GND_3, GND_EP,
    …). KiCad ERC flags every one that isn't electrically tied to ground.
    We iterate the entire pin list and attach one ``power:GND`` per pin
    that matches a recognized GND name.

    Returns the geometry of the first GND pin (kept for legacy callers
    that wanted "the" GND position).
    """
    from zynq_eda.core.layout.cluster import pin_side as _pin_side

    first_geom: PinGeometryAbs | None = None
    gnd_name_patterns = ("GND", "VSS", "GNDA", "AGND", "DGND")
    OFFSET = 5.08

    # Dedup by pin TIP page coordinate — many ICs have multiple GND
    # pins sharing the same physical location (e.g. CP2102N pin 2 and
    # pin 25 (EP) are both at the same (X, Y)). Without this dedup,
    # we emit two stacked power:GND symbols at the same coord and the
    # strict validator (correctly) flags the symbol_symbol overlap.
    placed_gnd_coords: set[tuple[float, float]] = set()

    for pin_info in geometry_cache.all_pins(ic.lib_id):
        pin_name = str(pin_info["name"])
        pin_number = str(pin_info["number"])
        name_upper = pin_name.upper()
        is_ground = (
            name_upper in gnd_name_patterns
            or any(name_upper.startswith(p + "_") for p in gnd_name_patterns)
            or name_upper.startswith("GND_")
        )
        if not is_ground:
            continue

        try:
            gnd_geom = geometry_cache.pin_geometry_by_name(
                ic.lib_id,
                ic_anchor,
                pin_number,
            )
        except KeyError:
            continue

        coord_key = (round(gnd_geom.connection.x, 3), round(gnd_geom.connection.y, 3))
        if coord_key in placed_gnd_coords:
            continue
        placed_gnd_coords.add(coord_key)

        # Place the power:GND symbol *outboard* of the pin so it doesn't
        # land on an adjacent pin in a densely-packed pinout.
        #
        # For pins on multi-pin sides (FUSB302 has 7 pins along the left
        # column at 2.54 mm pitch), going purely vertical would land the
        # symbol exactly on an adjacent pin. So we always go LATERAL
        # (X direction) when the pin's relative.x is non-zero — that
        # carries us safely outboard of the body. Only pins exactly at
        # the body's top/bottom centre line use a vertical extension.
        rel = gnd_geom.relative
        if rel.x != 0.0:
            outward_side: Literal["left", "right", "top", "bottom"] = (
                "left" if rel.x < 0 else "right"
            )
            gnd_symbol_pos = Point(
                snap_to_grid(gnd_geom.connection.x + (-OFFSET if rel.x < 0 else OFFSET)),
                gnd_geom.connection.y,
            )
        else:
            # Truly top/bottom-centre pin — use vertical (page-coord),
            # which means negating Y when the symbol-relative Y is positive
            # (top of body, since +Y is up in symbol space).
            outward_side = "top" if rel.y > 0 else "bottom"
            page_dy_dir = -1 if rel.y > 0 else 1
            gnd_symbol_pos = Point(
                gnd_geom.connection.x,
                snap_to_grid(gnd_geom.connection.y + page_dy_dir * OFFSET),
            )

        # Route the GND-pin → power:GND-symbol wire via the router so
        # it gets the full collision check (no wire crosses any other
        # wire/body/text). Source pin's intrinsic name text is exempt
        # because the wire's endpoint is at the pin tip by design.
        from zynq_eda.core.route.router import route_orthogonal_detail
        from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
        ic_pin_avoid: set[str] = {f"symbol:{ic.reference}"}
        if pin_number:
            ic_pin_avoid |= set(
                pin_intrinsic_owner_ids(ic.reference, (pin_number,))
            )
        gnd_route = route_orthogonal_detail(
            gnd_geom.connection,
            gnd_symbol_pos,
            builder.occupancy,
            avoid_owners=frozenset(ic_pin_avoid),
        )
        if gnd_route.gave_up:
            raise RuntimeError(
                f"_attach_ic_ground: router gave up routing IC {ic.reference!r} "
                f"GND pin {pin_name!r} @ {gnd_geom.connection} to "
                f"power:GND symbol @ {gnd_symbol_pos}. Upstream fix needed."
            )
        for seg in gnd_route.segments:
            builder.add_wire(seg)
        # Rotate the GND symbol so its body extends OUTWARD (away from
        # the IC) instead of into the wire path. See
        # :func:`zynq_eda.core.layout.cluster._outward_power_symbol_rotation`.
        from zynq_eda.core.layout.cluster import _outward_power_symbol_rotation
        gnd_rotation = _outward_power_symbol_rotation(
            lib_id="power:GND",
            pin_side=outward_side,
            geometry_cache=geometry_cache,
        )
        builder.add_symbol(PlacedSymbol(
            lib_id="power:GND",
            reference=builder.next_ref("#PWR"),
            value="GND",
            position=gnd_symbol_pos,
            footprint="",
            rotation=gnd_rotation,
        ), geometry=geometry_cache)
        if first_geom is None:
            first_geom = PinGeometryAbs(
                anchor=gnd_geom.anchor,
                connection=gnd_geom.connection,
                relative=gnd_geom.relative,
                pin_rotation=getattr(gnd_geom, "pin_rotation", 0.0),
                symbol_rotation=getattr(gnd_geom, "symbol_rotation", 0.0),
            )

    return first_geom


def _attach_ic_signal_overrides(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache,
    placed_passive_pin_names: set[str],
    edge_labeled_pin_names: set[str],
    cluster_pin_geoms: dict | None = None,
) -> None:
    """Attach a label (or power symbol) to every IC pin in ``pin_net_overrides``.

    The refcircuit's ``pin_net_overrides`` says "this IC pin is on net X".
    For signal nets (``STM32_I2C2_SDA``, ``STM32_FUSB302_INT``, etc.) we
    drop a short wire stub from the pin and place a local label at the
    stub's end — KiCad merges that with the same-named hierarchical
    label on the sheet edge.

    For power nets (``+VIN``, ``+3V3``, ``GND``) we drop a power symbol
    instead, which both labels the net AND drives it.

    Pins that already received a passive cluster are skipped (the cluster's
    near-wire already labels them via the cap-to-net connection). Pins
    handled by power_input_net / power_output_net are also skipped (the
    edge-label placer wires them straight to the sheet edge).
    """
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS, POWER_SYMBOL_OFFSET_MM
    from zynq_eda.core.layout.geometry import page_side_from_pin

    # Combine refcircuit + per-IC overrides.
    overrides = dict(ic.refcircuit.pin_net_overrides) | dict(ic.net_overrides)

    # ALSO include power_input_net / power_output_net for "IN"/"OUT" pin
    # roles. Without these the cross-block-name mapping is invisible to
    # the local-label pass — TPS2051's OUT pin gets a cluster cap to
    # GND but no label on the OUT pin itself, leaving its net unnamed
    # and disconnected from the J1 USB-C connector's VBUS_OTG pins
    # (which DO have pin_to_net labels). The edge-label pass already
    # handles the case where power_output_net IS in block.external_nets;
    # this fills the gap for cross-block-internal rails like VBUS_OTG
    # that exist only inside one sub-sheet.
    if getattr(ic, "power_input_net", "") and "IN" not in overrides:
        overrides["IN"] = ic.power_input_net
    if getattr(ic, "power_output_net", "") and "OUT" not in overrides:
        overrides["OUT"] = ic.power_output_net

    # Pins claimed by edge-label handler (hier-label at sheet edge) or
    # by passive clustering — skip those here. The cluster's near-side
    # label-at-trunk-end emission (cluster_ic_externals) now names
    # every clustered IC pin whose source net is a non-power named net,
    # so signal_overrides only needs to handle pins WITHOUT any cluster
    # cap. Single-handler-per-pin invariant: no two passes can both
    # emit a wire / label for the same physical pin.
    skip = {"GND", "VSS"} | set(placed_passive_pin_names) | set(edge_labeled_pin_names)

    # Stub length MUST be ONE pin pitch (2.54 mm), not two. A 5.08 mm stub
    # routed perpendicular to a dense pin row spans two adjacent pin Y
    # positions, so adjacent pins' stubs overlap into one giant vertical
    # wire that shorts them. Same bug + same fix as the connector pass in
    # commit 8eb7e02 (see connectors.py:_place_one_connector). Picking
    # the stub direction from page_side_from_pin (the pin's outward axis)
    # ensures the stub extends past the pin tip and never crosses an
    # adjacent pin's row.
    STUB_MM = 2.54

    for pin_name, net_name in overrides.items():
        if pin_name in skip:
            continue
        try:
            pin_geom = geometry_cache.pin_geometry_by_name(
                ic.lib_id,
                ic_anchor,
                pin_name,
            )
        except KeyError:
            continue

        # Stub direction = the pin's natural outward axis, derived from
        # (pin_rotation, symbol_rotation). This guarantees the stub
        # continues OUTWARD from the IC body along the pin's own axis,
        # so it can never collide with an adjacent pin's stub (adjacent
        # pins are offset perpendicular to that axis).
        side = page_side_from_pin(
            pin_rotation=getattr(pin_geom, "pin_rotation", 0.0),
            symbol_rotation=getattr(pin_geom, "symbol_rotation", 0.0),
        )
        if side == "left":
            stub_dx, stub_dy = -STUB_MM, 0.0
            label_rotation = 180.0
        elif side == "right":
            stub_dx, stub_dy = STUB_MM, 0.0
            label_rotation = 0.0
        elif side == "top":
            stub_dx, stub_dy = 0.0, -STUB_MM
            label_rotation = 90.0
        else:  # bottom
            stub_dx, stub_dy = 0.0, STUB_MM
            label_rotation = 270.0

        stub_end = Point(
            snap_to_grid(pin_geom.connection.x + stub_dx),
            snap_to_grid(pin_geom.connection.y + stub_dy),
        )
        # Route the override stub via the router so it never crosses
        # another wire or pin name. Source pin's own intrinsic text is
        # exempted (the stub's start IS the source pin tip).
        from zynq_eda.core.route.router import route_orthogonal_detail
        from zynq_eda.core.layout._builder import pin_intrinsic_owner_ids
        try:
            pin_number = next(
                str(pi["number"]) for pi in geometry_cache.all_pins(ic.lib_id)
                if str(pi["name"]) == pin_name
            )
        except StopIteration:
            pin_number = ""
        stub_avoid: set[str] = {f"symbol:{ic.reference}"}
        if pin_number:
            stub_avoid |= set(
                pin_intrinsic_owner_ids(ic.reference, (pin_number,))
            )
        stub_route = route_orthogonal_detail(
            pin_geom.connection,
            stub_end,
            builder.occupancy,
            avoid_owners=frozenset(stub_avoid),
        )
        if stub_route.gave_up:
            raise RuntimeError(
                f"_attach_ic_signal_overrides: router gave up routing "
                f"IC {ic.reference!r} pin {pin_name!r} @ {pin_geom.connection} "
                f"to stub end @ {stub_end} (net {net_name!r})."
            )
        for seg in stub_route.segments:
            builder.add_wire(seg)

        power_lib_id = POWER_SYMBOL_LIB_IDS.get(net_name)
        if power_lib_id is not None:
            # Power symbol attached just outboard of the stub end.
            symbol_position = stub_end
            builder.add_symbol(PlacedSymbol(
                lib_id=power_lib_id,
                reference=builder.next_ref("#PWR"),
                value=net_name,
                position=symbol_position,
                footprint="",
                rotation=0.0,
            ), geometry=geometry_cache)
        else:
            from zynq_eda.core.model.sheet import PlacedLabel
            builder.add_label(PlacedLabel(
                net_name=net_name,
                position=stub_end,
                rotation=label_rotation,
            ))


def _add_no_connects_for_unused_pins(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache,
    skip_pin_names: set[str],
) -> None:
    """Mark every IC pin we didn't explicitly handle with a no-connect cross.

    Default policy: an IC pin is "unused" unless the layout engine wired it
    to something. Sources of "wired" status (any one is enough — the pin is
    skipped by no-connect emission):

      * ``pin_net_overrides`` on the refcircuit or the per-instance
        ``net_overrides`` declare an explicit net for the pin.
      * The cluster pass placed a passive against the pin (its name appears
        in ``skip_pin_names``, populated from ``ic_pin_geometries``).
      * The pin is a power input/output recognized as the IC's main supply
        rail (``power_input_net``/``power_output_net`` or a refcircuit
        ``supply_rail`` GND/VDD/VCC-family pin).
      * The pin is a GND-family pin (handled by :func:`_attach_ic_ground`,
        which records the pin name into ``skip_pin_names`` indirectly via
        ``ic_pin_geometries``).

    Anything else gets a no-connect — KiCad's ``pin_not_connected`` ERC
    is then satisfied because the pin is intentionally terminated.

    This auto-NC default trades minor visual noise (an X cross on every
    unhandled pin) for a clean ERC pass. Refcircuits can still curate the
    nicer behaviour by adding pin entries; the auto-NC just stops every
    minor refcircuit gap from blowing up the validation step.
    """
    from zynq_eda.core.model.sheet import PlacedNoConnect

    overrides = dict(ic.refcircuit.pin_net_overrides) | dict(
        getattr(ic, "net_overrides", ()) or ()
    )

    # The IC's primary-supply pin names (the power_input_net / power_output_net
    # standard pin names) are handled by edge_labels — don't NC them.
    primary_supply_pin_names = set()
    if ic.power_input_net:
        primary_supply_pin_names.update(
            ("IN", "VDD", "VCC", "VBUS", "AVDD", "DVDD", "PVIN", "ANODE")
        )
    if ic.power_output_net:
        primary_supply_pin_names.update(("OUT", "VOUT", "CATHODE"))

    # GND-family pin names — _attach_ic_ground wires them.
    gnd_name_patterns = ("GND", "VSS", "GNDA", "AGND", "DGND")

    for pin_info in geometry_cache.all_pins(ic.lib_id):
        pin_name = str(pin_info["name"])
        pin_number = str(pin_info["number"])
        if pin_name in skip_pin_names:
            continue
        if pin_name in overrides:
            continue
        if pin_name in primary_supply_pin_names:
            continue
        name_upper = pin_name.upper()
        is_ground = (
            name_upper in gnd_name_patterns
            or any(name_upper.startswith(p + "_") for p in gnd_name_patterns)
            or name_upper.startswith("GND_")
        )
        if is_ground:
            continue
        try:
            pin_geom = geometry_cache.pin_geometry_by_name(
                ic.lib_id,
                ic_anchor,
                pin_number,
            )
        except KeyError:
            continue
        builder.no_connects.append(PlacedNoConnect(position=pin_geom.connection))


def _place_ic_with_passives(
    builder: BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache,
) -> dict[str, PinGeometryAbs]:
    """Place the IC body, every external part, the GND attachment, and NCs."""
    _place_ic_body(builder, ic=ic, ic_anchor=ic_anchor, geometry_cache=geometry_cache)

    def _resolve_pin(pin_name: str):
        try:
            return geometry_cache.pin_geometry_by_name(
                ic.lib_id,
                ic_anchor,
                pin_name,
            )
        except KeyError:
            return None

    pin_geom_map = cluster_ic_externals(
        builder,
        ic=ic,
        pin_geom_resolver=_resolve_pin,
        geometry_cache=geometry_cache,
    )

    # GND handling moved to the unified per-pin dispatcher
    # (``_emit_ic_pin_connections``) — every non-cluster pin is classified
    # into ONE category (GND, EDGE_LABEL, POWER_SYMBOL, LOCAL_LABEL, NC)
    # and dispatched to exactly ONE emitter. No skip flags coordinate
    # multiple handlers anymore.
    return pin_geom_map


def place_block_via_planner(
    block: Block,
    *,
    geometry_cache: SymbolGeometryCache,
) -> Sheet:
    """Predictive-planner code path: build a complete LayoutPlan first,
    then mechanically emit it.

    Activate by setting the ``ZYNQ_EDA_USE_PLANNER`` env var when
    running the carrier build. Once the planner reaches parity with
    the reactive pipeline (cluster geometry refinements per tasks
    #59-60), this becomes the default and the reactive ``place_block``
    is removed (PR 11).
    """
    from zynq_eda.core.layout.plan import emit_plan, plan_block
    builder = BlockLayoutBuilder()
    plan = plan_block(block, geometry_cache)
    emit_plan(plan, builder)
    return builder.finalize(block, geometry_cache=geometry_cache)


def place_block(
    block: Block,
    *,
    geometry_cache: SymbolGeometryCache,
    ic_column_x: float = 130.0,
    ic_top_y: float = 76.2,
    ic_row_pitch: float = 76.2,
) -> Sheet:
    """Render a :class:`Block` into a placed :class:`Sheet`.

    Args:
        block: The declarative block.
        geometry_cache: Pre-loaded symbol geometry cache.
        ic_column_x: X coordinate of the IC column on the sheet.
        ic_top_y: Y coordinate of the first IC.
        ic_row_pitch: Vertical distance between consecutive ICs. Must
            accommodate the tallest expected IC body plus its TOP-side
            decoupling-cap chain (cap body + power-symbol stub, up to
            ~24 mm). 76.2 mm (30 grid units) clears the TPD12S016 (33 mm
            body) + a stacked decoupling cap above the next IC's VCC
            pin without the cap landing inside the prior IC's body.
            The earlier 45.72 mm produced U1/C102 overlap on hdmi_tx
            because TPD12S016 extends +21.59 mm above its anchor while
            the EEPROM's TOP cap was placed 22.86 mm below the EEPROM
            anchor (cap+stagger = 15.24 mm + half-cap-body = 18.05 mm),
            requiring at least 50.8 mm of row pitch.
    """
    # Predictive planner opt-in via env var. The planner currently
    # achieves 11/27 clean blocks (validator-overlap-free); the
    # reactive pipeline achieves 17/27. Once tasks #59-60 close the
    # gap, the planner becomes default (PR 10) and the reactive
    # code is deleted (PR 11).
    import os
    if os.environ.get("ZYNQ_EDA_USE_PLANNER"):
        return place_block_via_planner(block, geometry_cache=geometry_cache)

    builder = BlockLayoutBuilder()

    ic_anchors = _ic_anchors_for_block(
        block,
        column_x=ic_column_x,
        top_y=ic_top_y,
        row_pitch=ic_row_pitch,
        geometry_cache=geometry_cache,
    )

    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]] = {}
    for ic in block.ics:
        ic_pin_geometries[ic.reference] = _place_ic_with_passives(
            builder,
            ic=ic,
            ic_anchor=ic_anchors[ic.reference],
            geometry_cache=geometry_cache,
        )

    place_connectors(
        builder,
        block=block,
        geometry_cache=geometry_cache,
        ic_anchors=ic_anchors,
    )

    # Unified per-pin dispatch: every non-cluster IC pin flows through
    # ONE classifier → ONE emitter (GND / EDGE_LABEL / POWER_SYMBOL /
    # LOCAL_LABEL / NC). No skip flags, no cross-handler coordination.
    # See ``_emit_ic_pin_connections`` for the partitioning logic.
    for ic in block.ics:
        _emit_ic_pin_connections(
            builder,
            ic=ic,
            ic_anchor=ic_anchors[ic.reference],
            geometry_cache=geometry_cache,
            block=block,
        )

    # Per-NET handlers (run AFTER per-pin dispatch so they can read the
    # local labels each pin emitter laid down). These emit hier-labels
    # at sheet edges + PWR_FLAGs for input rails — block-wide net
    # services, not per-pin work.
    place_external_nets(
        builder,
        block=block,
        ic_pin_geometries=ic_pin_geometries,
        ic_anchors=ic_anchors,
        geometry_cache=geometry_cache,
    )

    return builder.finalize(block, geometry_cache=geometry_cache)
