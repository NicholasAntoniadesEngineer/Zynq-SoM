"""High-level placement helpers built on Pin + BoundingBox + routing.

The single biggest practical win from the kicad-sch-api primitives we
borrowed: ``place_decoupling`` collapses what is otherwise ~20 lines of
per-IC boilerplate (place a cap, position it above the VDD pin, wire VDD
to cap pin 1, wire GND from cap pin 2 to the ground rail, junction at
each corner) into one call.

The carrier generator's ``_place_refcircuit`` consumes this for every
``ExternalPart`` whose role looks like decoupling (X7R MLCC tied between
a power_in pin and GND).
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.carrier.core.geometry import (
    BoundingBox,
    CornerDirection,
    create_orthogonal_routing,
    validate_routing_result,
)
from scripts.carrier.core.parts import DECOUPLING_REQUIRED_PIN_TYPES
from scripts.carrier.core.sexpr import (
    Point,
    SExp,
    junction,
    local_label,
    screen_above,
    snap_to_grid,
    wire,
)
from scripts.carrier.core.symbols import Pin, PlacedSymbol, SymbolDef


DECOUPLING_OFFSET_MM: float = 5.08
"""Default vertical distance from the VDD pin tip to the cap's pin 1."""


@dataclass(frozen=True)
class DecouplingResult:
    """Outcome of a single ``place_decoupling`` call."""

    cap_symbol: PlacedSymbol
    schematic_objects: tuple[SExp, ...]


def can_place_decoupling(
    ic: PlacedSymbol,
    vdd_pin_name: str,
    cap_symbol_def: SymbolDef,
    obstacles: tuple[BoundingBox, ...] = (),
    distance_mm: float = DECOUPLING_OFFSET_MM,
) -> bool:
    """Predicate: would a place_decoupling call with these parameters succeed?

    Checks the same conditions that ``place_decoupling`` would fail-hard on
    so the caller can pre-route the decision rather than relying on
    catch-and-fall-back. Specifically: the IC pin exists, its electrical
    type permits decoupling, and the resulting cap bounding box does not
    overlap any obstacle.
    """
    target_pin: Pin | None = next(
        (
            pin for pin in ic.symbol.pins
            if pin.number == vdd_pin_name or pin.name == vdd_pin_name
        ),
        None,
    )
    if target_pin is None:
        return False
    if target_pin.electrical_type not in DECOUPLING_REQUIRED_PIN_TYPES:
        return False
    cap_origin = _resolve_decoupling_origin(
        ic.pin_position(vdd_pin_name), cap_symbol_def, distance_mm,
    )
    candidate_box = _placed_bounding_box(cap_origin, cap_symbol_def)
    return not any(
        _boxes_overlap(candidate_box, obstacle) for obstacle in obstacles
    )


def place_decoupling(
    ic: PlacedSymbol,
    vdd_pin_name: str,
    gnd_net: str,
    cap_symbol_def: SymbolDef,
    cap_reference: str,
    cap_value: str,
    cap_footprint: str,
    obstacles: tuple[BoundingBox, ...] = (),
    distance_mm: float = DECOUPLING_OFFSET_MM,
) -> DecouplingResult:
    """Place a decoupling capacitor above an IC VDD pin and wire it.

    The cap's pin 1 lands ``distance_mm`` visually above the IC's VDD pin
    on the KiCad grid, oriented vertically so cap pin 2 sits one pin pitch
    further up. A wire is routed from the IC pin tip to cap pin 1 (with a
    junction at any corner), and a local ground label is placed at cap
    pin 2's tip to tie it to ``gnd_net``.

    Fails hard if:
        - ``vdd_pin_name`` is not on the IC symbol
        - The IC pin's ``electrical_type`` is not in
          ``DECOUPLING_REQUIRED_PIN_TYPES`` (Rule C1)
        - The placed cap intersects ``obstacles``
        - Routing cannot avoid all obstacles
    """

    ic_pin = _resolve_pin(ic, vdd_pin_name)
    if ic_pin.electrical_type not in DECOUPLING_REQUIRED_PIN_TYPES:
        raise ValueError(
            f"place_decoupling: IC {ic.reference} pin {vdd_pin_name!r} has "
            f"electrical_type {ic_pin.electrical_type!r}, which is not in "
            f"DECOUPLING_REQUIRED_PIN_TYPES. Call can_place_decoupling first."
        )

    ic_pin_tip = ic.pin_position(vdd_pin_name)
    cap_origin = _resolve_decoupling_origin(ic_pin_tip, cap_symbol_def, distance_mm)

    cap_symbol = PlacedSymbol(
        reference=cap_reference,
        symbol=cap_symbol_def,
        value=cap_value,
        footprint=cap_footprint,
        origin=cap_origin,
    )

    if any(
        _boxes_overlap(cap_symbol.bounding_box, obstacle)
        for obstacle in obstacles
    ):
        raise ValueError(
            f"place_decoupling: cap {cap_reference} for {ic.reference}.{vdd_pin_name} "
            f"overlaps an existing component bounding box. Call "
            f"can_place_decoupling first to pre-check feasibility."
        )

    cap_pin_1_position = cap_symbol.pin_position("1")
    cap_pin_2_position = cap_symbol.pin_position("2")

    routing_result = create_orthogonal_routing(
        from_pos=ic_pin_tip,
        to_pos=cap_pin_1_position,
        direction=CornerDirection.VERTICAL_FIRST,
        obstacles=obstacles,
    )
    validate_routing_result(routing_result)

    schematic_objects: list[SExp] = []
    for segment_start, segment_end in routing_result.segments:
        schematic_objects.append(wire(segment_start, segment_end))
    for junction_position in routing_result.junctions:
        schematic_objects.append(junction(junction_position))
    schematic_objects.append(local_label(
        net=gnd_net,
        position=cap_pin_2_position,
        angle=0.0,
    ))

    return DecouplingResult(
        cap_symbol=cap_symbol,
        schematic_objects=tuple(schematic_objects),
    )


def _resolve_pin(ic: PlacedSymbol, name_or_number: str) -> Pin:
    for pin in ic.symbol.pins:
        if pin.number == name_or_number or pin.name == name_or_number:
            return pin
    raise KeyError(
        f"_resolve_pin: IC {ic.reference} ({ic.symbol.lib_id}) has no pin "
        f"matching {name_or_number!r}"
    )


def _resolve_decoupling_origin(
    ic_pin_tip: Point,
    cap_symbol_def: SymbolDef,
    distance_mm: float,
) -> Point:
    cap_pin_1_local = cap_symbol_def.pin_position("1")
    cap_pin_1_target = screen_above(ic_pin_tip, distance_mm)
    return Point(
        snap_to_grid(cap_pin_1_target.x - cap_pin_1_local.x),
        snap_to_grid(cap_pin_1_target.y - cap_pin_1_local.y),
    )


def _placed_bounding_box(origin: Point, symbol_def: SymbolDef) -> BoundingBox:
    local_box = symbol_def.bounding_box
    return BoundingBox(
        top_left=Point(
            origin.x + local_box.top_left.x,
            origin.y + local_box.top_left.y,
        ),
        bottom_right=Point(
            origin.x + local_box.bottom_right.x,
            origin.y + local_box.bottom_right.y,
        ),
    )


def _boxes_overlap(box_a: BoundingBox, box_b: BoundingBox) -> bool:
    if box_a.bottom_right.x <= box_b.top_left.x:
        return False
    if box_a.top_left.x >= box_b.bottom_right.x:
        return False
    if box_a.bottom_right.y <= box_b.top_left.y:
        return False
    if box_a.top_left.y >= box_b.bottom_right.y:
        return False
    return True


__all__ = [
    "DECOUPLING_OFFSET_MM",
    "DecouplingResult",
    "can_place_decoupling",
    "place_decoupling",
]
