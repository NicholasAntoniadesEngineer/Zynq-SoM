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

    gnd_geom = _attach_ic_ground(
        builder,
        ic=ic,
        ic_anchor=ic_anchor,
        geometry_cache=geometry_cache,
    )
    if gnd_geom is not None:
        pin_geom_map.setdefault("GND", gnd_geom)

    # Note: signal-override + no-connect handling moved to ``place_block``
    # so they can be informed by which pins the edge-label pass picked up.
    return pin_geom_map


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

    edge_labeled = place_external_nets(
        builder,
        block=block,
        ic_pin_geometries=ic_pin_geometries,
        ic_anchors=ic_anchors,
        geometry_cache=geometry_cache,
    )

    # Per-IC signal-override stubs + no-connect markers. The "expected
    # edge-labeled" set is computed UPFRONT from declared external nets
    # — every pin whose override net is in ``block.external_nets``
    # belongs to the edge-label handler EXCLUSIVELY. signal_overrides
    # skips those whether or not edge_labels actually succeeded in
    # routing them; the alternative is double-handling and conflicting
    # wires/labels. Single-handler-per-pin invariant.
    declared_net_names = {net.name for net in block.external_nets}
    for ic in block.ics:
        edge_labeled_pin_names = {
            pin_name for (ic_ref, pin_name) in edge_labeled if ic_ref == ic.reference
        }
        # Add pins whose override-net is declared external — those are
        # the edge-label handler's territory even if its routing failed
        # for this run.
        ic_overrides = dict(ic.refcircuit.pin_net_overrides) | dict(getattr(ic, "net_overrides", ()) or ())
        for pin_name, net_name in ic_overrides.items():
            if net_name in declared_net_names:
                edge_labeled_pin_names.add(pin_name)
        _attach_ic_signal_overrides(
            builder,
            ic=ic,
            ic_anchor=ic_anchors[ic.reference],
            geometry_cache=geometry_cache,
            placed_passive_pin_names=set(ic_pin_geometries[ic.reference].keys()),
            edge_labeled_pin_names=edge_labeled_pin_names,
        )
        _add_no_connects_for_unused_pins(
            builder,
            ic=ic,
            ic_anchor=ic_anchors[ic.reference],
            geometry_cache=geometry_cache,
            skip_pin_names=(
                set(ic_pin_geometries[ic.reference].keys())
                | edge_labeled_pin_names
            ),
        )

    return builder.finalize(block, geometry_cache=geometry_cache)
