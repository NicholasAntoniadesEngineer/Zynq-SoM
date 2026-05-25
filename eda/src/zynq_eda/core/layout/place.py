"""Per-block placement: derive symbol positions from a declarative Block.

This is the first version of the placement engine: it lays out a Block onto
a single A4 page using a deterministic "IC column + passive swarm" pattern.
Limitations (will be lifted in Stage 5):

* No auto-pagination across multiple sheets.
* No cross-IC collision detection — caller is responsible for ensuring the
  configured IC anchors are far enough apart that their passive swarms
  don't overlap.
* Wires are L-routed Manhattan without occupancy avoidance.

Output is a fully-populated :class:`Sheet` ready for the emitter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from zynq_eda.core.layout.geometry import (
    DEFAULT_PIN_LENGTH_MM,
    SymbolGeometryCache,
    pin_connection_from_anchor,
)
from zynq_eda.core.model.block import Block, ExternalNet, IcInstance
from zynq_eda.core.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from zynq_eda.core.model.interface import SheetEdge
from zynq_eda.core.model.nets import is_power_rail
from zynq_eda.core.model.refcircuit import ExternalPart
from zynq_eda.core.model.sheet import (
    PAPER_DIMENSIONS_MM,
    PlacedHierarchicalLabel,
    PlacedJunction,
    PlacedLabel,
    PlacedNoConnect,
    PlacedSymbol,
    PlacedWire,
    Sheet,
)


PASSIVE_PITCH_MM = snap_to_grid(5.08)         # vertical distance between stacked passives
PASSIVE_OFFSET_MM = snap_to_grid(10.16)       # distance from IC pin to nearest passive
PIN_TO_PASSIVE_NEAR_MM = snap_to_grid(2.54)   # gap between IC pin and passive's near terminal
POWER_SYMBOL_OFFSET_MM = snap_to_grid(5.08)   # distance from passive far pin to power symbol
INTERIOR_MARGIN_MM = snap_to_grid(15.24)      # min distance from page edge to any placed item


# Map from canonical net names to KiCad power-symbol lib_ids. Anything not in
# this map is rendered as a local label instead of a power symbol.
POWER_SYMBOL_LIB_IDS: dict[str, str] = {
    "GND":         "power:GND",
    "+VIN":        "power:+5V",
    "+VIN_IN":     "power:+5V",
    "+5V":         "power:+5V",
    "+3V3":        "power:+3V3",
    "+3V3_SC":     "power:+3V3",
    "+2V5":        "power:+2V5",
    "+1V8":        "power:+1V8",
    "+1V2":        "power:+1V2",
    "CHASSIS_GND": "power:Earth",
}


_PASSIVE_KIND = Literal["cap", "res", "diode", "other"]


def _passive_kind(part_token: str) -> _PASSIVE_KIND:
    """Classify a part token as cap / res / diode / other."""
    lowered = part_token.lower()
    if "schottky" in lowered or lowered.startswith("ss"):
        return "diode"
    cap_markers = ("n_0402", "n_0603", "u_0402", "u_0603", "u_1206", "p_0402", "_x7r", "_x5r", "_c0g")
    if any(marker in lowered for marker in cap_markers):
        return "cap"
    res_markers = ("k_0402", "k_0603", "r_0402", "r_0603", "_1%")
    if any(marker in lowered for marker in res_markers):
        return "res"
    return "other"


def _passive_lib_id(part_token: str) -> str:
    """Return the KiCad lib_id for a passive given its part token."""
    kind = _passive_kind(part_token)
    if kind == "cap":
        return "Device:C"
    if kind == "res":
        return "Device:R"
    if kind == "diode":
        return "Device:D_Schottky"
    return "Device:R"


def _passive_value(part_token: str) -> str:
    """Strip footprint suffix off a part token for the symbol's Value field."""
    # Tokens look like "100n_0402_X7R", "10k_0402_1%", "schottky_SS14".
    parts = part_token.split("_")
    if not parts:
        return part_token
    if parts[0].lower() == "schottky":
        return parts[-1] if len(parts) > 1 else parts[0]
    return parts[0]


@dataclass
class _BlockLayoutBuilder:
    """Mutable accumulator while laying out a block."""

    symbols: list[PlacedSymbol] = field(default_factory=list)
    wires: list[PlacedWire] = field(default_factory=list)
    labels: list[PlacedLabel] = field(default_factory=list)
    junctions: list[PlacedJunction] = field(default_factory=list)
    no_connects: list[PlacedNoConnect] = field(default_factory=list)
    hierarchical_labels: list[PlacedHierarchicalLabel] = field(default_factory=list)
    _ref_counters: dict[str, int] = field(default_factory=lambda: {"C": 100, "R": 100, "D": 100, "PWR": 100})

    def next_ref(self, prefix: str) -> str:
        index = self._ref_counters.setdefault(prefix, 100)
        self._ref_counters[prefix] = index + 1
        return f"{prefix}{index}"

    def finalize(self, block: Block) -> Sheet:
        return Sheet(
            name=block.name,
            title=block.title,
            paper_size=block.paper_size,
            symbols=tuple(self.symbols),
            wires=tuple(self.wires),
            labels=tuple(self.labels),
            junctions=tuple(self.junctions),
            no_connects=tuple(self.no_connects),
            hierarchical_labels=tuple(self.hierarchical_labels),
            description=block.description,
        )


def _ic_anchors_for_block(
    block: Block,
    *,
    geometry_cache: SymbolGeometryCache,
    column_x: float,
    top_y: float,
    row_pitch: float,
) -> dict[str, Point]:
    """Place ICs in a single vertical column, evenly spaced.

    For Stage 4 this is sufficient (Power block: 3-4 LDOs + 1 Schottky).
    Stage 5 will replace this with a region-aware packer.
    """
    anchors: dict[str, Point] = {}
    for index, ic in enumerate(block.ics):
        anchors[ic.reference] = Point(
            snap_to_grid(column_x),
            snap_to_grid(top_y + index * row_pitch),
        )
    return anchors


def _pin_side(pin_relative: Point) -> Literal["left", "right", "top", "bottom"]:
    """Determine which side of the symbol a pin lives on, from its relative pos."""
    if abs(pin_relative.x) >= abs(pin_relative.y):
        return "right" if pin_relative.x > 0 else "left"
    return "bottom" if pin_relative.y > 0 else "top"


def _place_one_passive_for_pin(
    builder: _BlockLayoutBuilder,
    *,
    external: ExternalPart,
    resolved_destination: str,
    ic_pin_geometry,
    swarm_slot_offset: float,
    ic_reference: str,
) -> None:
    """Place one external passive next to an IC pin and wire it up.

    ``swarm_slot_offset`` is the perpendicular distance from the IC pin to
    this passive (0 = closest to IC, then ``PASSIVE_PITCH_MM`` per slot).
    """
    # Device:C and Device:R have pins at relative (0, ±3.81) when rotation=0
    # (pin 1 at top, pin 2 at bottom). When rotated 90, the pins lie on the
    # X axis instead.
    PASSIVE_PIN_HALF = 3.81  # mm; half the 7.62 mm pin-to-pin separation

    side = _pin_side(ic_pin_geometry.relative)
    pin_connection = ic_pin_geometry.connection

    # ``primary_offset`` is the distance from the IC pin to the passive's
    # *anchor* (centre). Increase per swarm slot to stack additional passives
    # away from the IC.
    primary_offset = PASSIVE_OFFSET_MM + swarm_slot_offset

    # Pick the passive's centre + rotation so its NEAR pin (toward the IC)
    # and FAR pin (away from the IC) land at predictable absolute positions.
    #
    # Under KiCad's "Y-flip then rotate CW" placement transform,
    # Device:C / Device:R pin positions resolve to:
    #
    #   rotation  0 : pin 1 → (0,  -3.81), pin 2 → (0, +3.81)  [pin 1 on top]
    #   rotation 90 : pin 1 → (-3.81, 0),  pin 2 → (+3.81, 0)  [pin 1 on left]
    #   rotation 180: pin 1 → (0, +3.81),  pin 2 → (0, -3.81)
    #   rotation 270: pin 1 → (+3.81, 0),  pin 2 → (-3.81, 0)
    #
    # We choose ``passive_rotation`` so the geometric NEAR pin lines up
    # exactly on the IC-pin axis (regardless of which numbered pin lands
    # there — wires connect by position, not by pin number).
    if side == "left":
        # IC pin on body's left edge → passive sits to the LEFT of IC pin.
        # rotation 270 puts pin 1 on the RIGHT (toward IC); pin 2 on the
        # LEFT (away, toward power symbol).
        passive_anchor = Point(
            snap_to_grid(pin_connection.x - primary_offset),
            pin_connection.y,
        )
        passive_rotation = 270.0
        near_point = Point(snap_to_grid(passive_anchor.x + PASSIVE_PIN_HALF), passive_anchor.y)
        far_point = Point(snap_to_grid(passive_anchor.x - PASSIVE_PIN_HALF), passive_anchor.y)
    elif side == "right":
        # IC pin on body's right edge → passive sits to the RIGHT of IC pin.
        # rotation 90 puts pin 1 on the LEFT (toward IC); pin 2 on the right.
        passive_anchor = Point(
            snap_to_grid(pin_connection.x + primary_offset),
            pin_connection.y,
        )
        passive_rotation = 90.0
        near_point = Point(snap_to_grid(passive_anchor.x - PASSIVE_PIN_HALF), passive_anchor.y)
        far_point = Point(snap_to_grid(passive_anchor.x + PASSIVE_PIN_HALF), passive_anchor.y)
    elif side == "top":
        # IC pin emerges from the top of the body → passive sits ABOVE.
        # rotation 0 puts pin 1 above the anchor (away from IC) and pin 2
        # below (toward IC). Near pin (toward IC) is on the BOTTOM of the
        # passive.
        passive_anchor = Point(
            pin_connection.x,
            snap_to_grid(pin_connection.y - primary_offset),
        )
        passive_rotation = 0.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
    else:  # bottom
        # IC pin emerges from the bottom → passive sits BELOW the IC pin.
        # rotation 180 puts pin 1 below the anchor (away from IC) and pin 2
        # above (toward IC). Near pin (toward IC) is on the TOP of the
        # passive.
        passive_anchor = Point(
            pin_connection.x,
            snap_to_grid(pin_connection.y + primary_offset),
        )
        passive_rotation = 180.0
        near_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y - PASSIVE_PIN_HALF))
        far_point = Point(passive_anchor.x, snap_to_grid(passive_anchor.y + PASSIVE_PIN_HALF))

    lib_id = _passive_lib_id(external.part_token)
    kind = _passive_kind(external.part_token)
    if kind == "cap":
        ref_prefix = "C"
        footprint = "Capacitor_SMD:C_0402_1005Metric"
    elif kind == "diode":
        ref_prefix = "D"
        footprint = "Diode_SMD:D_SMA"
    else:
        ref_prefix = "R"
        footprint = "Resistor_SMD:R_0402_1005Metric"

    passive_ref = builder.next_ref(ref_prefix)
    passive_value = _passive_value(external.part_token)

    builder.symbols.append(PlacedSymbol(
        lib_id=lib_id,
        reference=passive_ref,
        value=passive_value,
        position=passive_anchor,
        footprint=footprint,
        rotation=passive_rotation,
    ))

    # Wire from IC pin → passive's near terminal. They share an axis (X or Y)
    # because the passive is placed in line with the IC pin.
    if pin_connection != near_point:
        builder.wires.append(PlacedWire(start=pin_connection, end=near_point))

    # Wire from passive far terminal -> destination (power symbol or local label).
    _attach_far_endpoint(
        builder,
        far_point=far_point,
        passive_orientation=passive_rotation,
        passive_side=side,
        destination_net=resolved_destination,
    )


def _attach_far_endpoint(
    builder: _BlockLayoutBuilder,
    *,
    far_point: Point,
    passive_orientation: float,
    passive_side: str,
    destination_net: str,
) -> None:
    """Attach a passive's far terminal to a power symbol or a local label."""
    power_lib_id = POWER_SYMBOL_LIB_IDS.get(destination_net)
    if power_lib_id is not None:
        # Place a power symbol at the far terminal. KiCad power symbols have
        # one pin at their origin, so the symbol's anchor == the wire-attachment.
        # We add a small wire stub if the symbol is in the "GND" family
        # (which conventionally faces down).
        symbol_position = far_point
        # GND-family symbols face downward; place the symbol below the far pin.
        # +Vxx symbols face upward; place the symbol above the far pin.
        if "GND" in destination_net.upper() or destination_net.upper() == "CHASSIS_GND":
            symbol_position = Point(
                far_point.x,
                snap_to_grid(far_point.y + POWER_SYMBOL_OFFSET_MM),
            )
            builder.wires.append(PlacedWire(start=far_point, end=symbol_position))
            rotation = 0.0
        else:
            symbol_position = Point(
                far_point.x,
                snap_to_grid(far_point.y - POWER_SYMBOL_OFFSET_MM),
            )
            builder.wires.append(PlacedWire(start=symbol_position, end=far_point))
            rotation = 0.0
        builder.symbols.append(PlacedSymbol(
            lib_id=power_lib_id,
            reference=builder.next_ref("#PWR"),
            value=destination_net,
            position=symbol_position,
            footprint="",
            rotation=rotation,
        ))
    else:
        # Local label at the far terminal.
        builder.labels.append(PlacedLabel(
            net_name=destination_net,
            position=far_point,
            rotation=0.0,
        ))


def _classify_swarm_slot(
    external_parts_for_pin: list[ExternalPart],
) -> list[int]:
    """Assign a swarm-slot index (0, 1, 2, ...) to each external part on a pin."""
    return list(range(len(external_parts_for_pin)))


def _resolve_destination_net(
    *,
    raw_destination: str,
    ic: IcInstance,
    overrides_for_pin: dict[str, str],
) -> str:
    """Resolve a refcircuit's ``to_net`` into the actual schematic net.

    Special cases:

    * ``"IN"``  → the IC's ``power_input_net`` (if set); else fallback name.
    * ``"OUT"`` → the IC's ``power_output_net`` (if set); else fallback name.
    * If the value names another pin on the same IC (e.g. ``"VBUS"``),
      use that pin's override net when known.
    * Otherwise return the raw value (handled as a power symbol or local label).
    """
    if raw_destination == "IN" and ic.power_input_net:
        return ic.power_input_net
    if raw_destination == "OUT" and ic.power_output_net:
        return ic.power_output_net
    if raw_destination in overrides_for_pin:
        return overrides_for_pin[raw_destination]
    return raw_destination


def _place_ic_with_passives(
    builder: _BlockLayoutBuilder,
    *,
    ic: IcInstance,
    ic_anchor: Point,
    geometry_cache: SymbolGeometryCache,
) -> dict[str, "PinGeometryAbs"]:
    """Place the IC + every external part in its refcircuit."""
    # Place the IC body.
    builder.symbols.append(PlacedSymbol(
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
    ))

    # Group external parts by from_pin so the swarm-slot indexing is per-pin.
    by_pin: dict[str, list[ExternalPart]] = {}
    for external in ic.refcircuit.external_parts:
        by_pin.setdefault(external.from_pin, []).append(external)

    overrides_for_pin = dict(ic.refcircuit.pin_net_overrides) | dict(ic.net_overrides)
    if ic.power_input_net:
        # Synthesize entries so to_net="IN" gets resolved correctly.
        overrides_for_pin.setdefault("IN", ic.power_input_net)
    if ic.power_output_net:
        overrides_for_pin.setdefault("OUT", ic.power_output_net)

    pin_geom_by_name: dict[str, "PinGeometryAbs"] = {}
    placed_passive_pin_names: set[str] = set()
    for pin_name, externals in by_pin.items():
        try:
            pin_geom = geometry_cache.pin_geometry_by_name(
                ic.lib_id,
                ic_anchor,
                pin_name,
            )
        except KeyError:
            # The refcircuit references a pin not present on the symbol
            # (e.g. NR_SS where KiCad labels the pin NC). Skip — placement
            # validator in Stage 5 will surface this mismatch.
            continue
        pin_geom_by_name[pin_name] = PinGeometryAbs(
            anchor=pin_geom.anchor,
            connection=pin_geom.connection,
            relative=pin_geom.relative,
        )
        placed_passive_pin_names.add(pin_name)

        for slot_index, external in enumerate(externals):
            resolved_destination = _resolve_destination_net(
                raw_destination=external.to_net,
                ic=ic,
                overrides_for_pin=overrides_for_pin,
            )
            _place_one_passive_for_pin(
                builder,
                external=external,
                resolved_destination=resolved_destination,
                ic_pin_geometry=pin_geom,
                swarm_slot_offset=slot_index * PASSIVE_PITCH_MM,
                ic_reference=ic.reference,
            )

    # Always attach a power:GND symbol to the IC's GND pin (if present) so the
    # IC has a ground reference regardless of whether a refcircuit external
    # part attaches to GND.
    for gnd_pin_name in ("GND", "VSS"):
        try:
            gnd_geom = geometry_cache.pin_geometry_by_name(
                ic.lib_id,
                ic_anchor,
                gnd_pin_name,
            )
        except KeyError:
            continue
        # Place power:GND directly below the pin connection. The pin sits at
        # the bottom of the body for most ICs, so the symbol just continues
        # downward from there.
        gnd_symbol_pos = Point(
            gnd_geom.connection.x,
            snap_to_grid(gnd_geom.connection.y + 5.08),
        )
        builder.wires.append(PlacedWire(
            start=gnd_geom.connection,
            end=gnd_symbol_pos,
        ))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:GND",
            reference=builder.next_ref("#PWR"),
            value="GND",
            position=gnd_symbol_pos,
            footprint="",
            rotation=0.0,
        ))
        pin_geom_by_name[gnd_pin_name] = PinGeometryAbs(
            anchor=gnd_geom.anchor,
            connection=gnd_geom.connection,
            relative=gnd_geom.relative,
        )
        break  # only one GND per IC

    # Add no-connect markers for pins with no external part attached AND
    # whose pin name looks like "NC" (KiCad convention for unused pins).
    for pin_info in geometry_cache.all_pins(ic.lib_id):
        pin_name = str(pin_info["name"])
        pin_number = str(pin_info["number"])
        if pin_name.upper() not in {"NC", "~NC~", "~"}:
            continue
        if pin_name in placed_passive_pin_names:
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

    return pin_geom_by_name


@dataclass(frozen=True)
class PinGeometryAbs:
    """Subset of PinGeometry kept by the builder for later wiring."""
    anchor: Point
    connection: Point
    relative: Point


def _place_external_nets(
    builder: _BlockLayoutBuilder,
    *,
    block: Block,
    paper_size: str,
    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]],
    ic_anchors: dict[str, Point],
) -> None:
    """Place hierarchical labels at the configured edges and wire IC power
    inputs/outputs to them.

    Strategy:
    * For each IC + power-pin pair, emit one hierarchical label at the IC's
      pin Y on the configured edge. Multiple ICs sharing a net produce
      multiple same-named labels — KiCad treats them as the same net.
    * Each label is wired to its IC pin via a single horizontal segment,
      so no vertical wire ever crosses another label.
    """
    paper_w, _paper_h = PAPER_DIMENSIONS_MM[paper_size]
    left_x = snap_to_grid(INTERIOR_MARGIN_MM)
    right_x = snap_to_grid(paper_w - INTERIOR_MARGIN_MM)

    # Build a map from net name → its declared edge so we know which side to
    # place each instance's label on.
    declared_nets: dict[str, ExternalNet] = {net.name: net for net in block.external_nets}

    # Walk ICs in order; each IC's IN/OUT/etc. pin gets its own hierarchical
    # label at the same Y as the pin, on the declared edge.
    seen_label_positions: set[tuple[float, float]] = set()
    for ic in block.ics:
        ic_geoms = ic_pin_geometries.get(ic.reference, {})

        candidates: list[tuple[str, str]] = []
        if ic.power_input_net:
            candidates.extend([
                ("IN",  ic.power_input_net),
                ("VDD", ic.power_input_net),
                ("VCC", ic.power_input_net),
                ("ANODE", ic.power_input_net),
            ])
        if ic.power_output_net:
            candidates.extend([
                ("OUT", ic.power_output_net),
                ("CATHODE", ic.power_output_net),
            ])

        for pin_role, net_name in candidates:
            if net_name not in declared_nets:
                continue
            if pin_role not in ic_geoms:
                continue
            net = declared_nets[net_name]
            pin_connection = ic_geoms[pin_role].connection
            label_x = left_x if net.edge == SheetEdge.LEFT else right_x
            label_y = pin_connection.y  # align with pin Y for clean wiring
            label_position = Point(label_x, snap_to_grid(label_y))
            if (label_position.x, label_position.y) in seen_label_positions:
                continue
            seen_label_positions.add((label_position.x, label_position.y))

            rotation = 180.0 if net.edge == SheetEdge.LEFT else 0.0
            builder.hierarchical_labels.append(PlacedHierarchicalLabel(
                net_name=net_name,
                position=label_position,
                direction=net.direction,
                rotation=rotation,
            ))
            # Single horizontal wire from IC pin to label (same Y).
            builder.wires.append(PlacedWire(
                start=pin_connection,
                end=label_position,
            ))

    # Add exactly one PWR_FLAG per unique INPUT-direction net (power_kind ==
    # "input"). ERC requires every power_input pin to be driven by a
    # power_output somewhere, and the hierarchical label alone doesn't
    # count as a driver. Skip OUTPUT-direction nets (the LDO OUT pin is
    # itself a power_out, so adding a FLAG would create two drivers and
    # trigger pin_to_pin conflicts). Skip GND (handled via power:GND
    # symbols at every cap, which are implicit drivers).
    flag_emitted_for_net: set[str] = set()
    for net in block.external_nets:
        if net.power_kind != "input":
            continue
        if net.name in flag_emitted_for_net:
            continue
        flag_emitted_for_net.add(net.name)
        # Find the first hierarchical label for this net to anchor the flag.
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
        builder.wires.append(PlacedWire(
            start=anchor_label.position,
            end=flag_position,
        ))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=builder.next_ref("#FLG"),
            value=net.name,
            position=flag_position,
            footprint="",
            rotation=0.0,
        ))

    # Ground nets need their own label too: place GND at left edge but at the
    # very bottom (away from power input labels) so it stays clear of any
    # power routing. The actual GND connections happen through power symbols
    # at each cap, not directly through the hierarchical label.
    for ground_net in block.external_nets:
        if ground_net.power_kind != "ground":
            continue
        label_x = left_x if ground_net.edge == SheetEdge.LEFT else right_x
        # Pick a Y near the bottom of the placed ICs.
        ic_y_values = [anchor.y for anchor in ic_anchors.values()]
        if ic_y_values:
            label_y = snap_to_grid(max(ic_y_values) + 38.1)
        else:
            label_y = snap_to_grid(INTERIOR_MARGIN_MM + 20.32)
        label_position = Point(label_x, label_y)
        if (label_position.x, label_position.y) in seen_label_positions:
            continue
        seen_label_positions.add((label_position.x, label_position.y))
        rotation = 180.0 if ground_net.edge == SheetEdge.LEFT else 0.0
        builder.hierarchical_labels.append(PlacedHierarchicalLabel(
            net_name=ground_net.name,
            position=label_position,
            direction=ground_net.direction,
            rotation=rotation,
        ))
        # Connect the GND hierarchical label to a power:GND symbol so the
        # net is electrically driven into the rest of the sheet.
        gnd_symbol_position = Point(
            label_position.x,
            snap_to_grid(label_position.y + POWER_SYMBOL_OFFSET_MM),
        )
        builder.wires.append(PlacedWire(start=label_position, end=gnd_symbol_position))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:GND",
            reference=builder.next_ref("#PWR"),
            value="GND",
            position=gnd_symbol_position,
            footprint="",
            rotation=0.0,
        ))
        # One PWR_FLAG per sheet on GND so ERC sees the global GND net as
        # driven. The power:GND symbols on each cap are power_in pins and
        # don't satisfy the "needs power_out" check on their own.
        gnd_flag_position = Point(
            snap_to_grid(label_position.x + (-3.81 if ground_net.edge == SheetEdge.LEFT else 3.81)),
            label_position.y,
        )
        builder.wires.append(PlacedWire(
            start=label_position,
            end=gnd_flag_position,
        ))
        builder.symbols.append(PlacedSymbol(
            lib_id="power:PWR_FLAG",
            reference=builder.next_ref("#FLG"),
            value="GND",
            position=gnd_flag_position,
            footprint="",
            rotation=0.0,
        ))


def _route_l(builder: _BlockLayoutBuilder, start: Point, end: Point) -> None:
    """Emit a 1- or 2-segment Manhattan L from ``start`` to ``end``."""
    if start == end:
        return
    if start.x == end.x or start.y == end.y:
        builder.wires.append(PlacedWire(start=start, end=end))
        return
    # Two-segment: go horizontal first then vertical.
    corner = Point(end.x, start.y)
    builder.wires.append(PlacedWire(start=start, end=corner))
    builder.wires.append(PlacedWire(start=corner, end=end))


def place_block(
    block: Block,
    *,
    geometry_cache: SymbolGeometryCache,
    ic_column_x: float = 130.0,
    ic_top_y: float = 60.0,
    ic_row_pitch: float = 45.72,
) -> Sheet:
    """Render a :class:`Block` into a placed :class:`Sheet`.

    Args:
        block: The declarative block description.
        geometry_cache: Pre-loaded symbol geometry cache.
        ic_column_x: X coordinate of the IC column on the sheet.
        ic_top_y: Y coordinate of the first IC.
        ic_row_pitch: Vertical distance between consecutive ICs.
    """
    builder = _BlockLayoutBuilder()

    # Step 1: place each IC and its passive swarm.
    ic_anchors = _ic_anchors_for_block(
        block,
        geometry_cache=geometry_cache,
        column_x=ic_column_x,
        top_y=ic_top_y,
        row_pitch=ic_row_pitch,
    )

    ic_pin_geometries: dict[str, dict[str, PinGeometryAbs]] = {}
    for ic in block.ics:
        ic_pin_geometries[ic.reference] = _place_ic_with_passives(
            builder,
            ic=ic,
            ic_anchor=ic_anchors[ic.reference],
            geometry_cache=geometry_cache,
        )

    # Step 2: hierarchical labels at sheet edges + wire ICs to them.
    _place_external_nets(
        builder,
        block=block,
        paper_size=block.paper_size,
        ic_pin_geometries=ic_pin_geometries,
        ic_anchors=ic_anchors,
    )

    return builder.finalize(block)
