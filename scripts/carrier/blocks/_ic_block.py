"""Wired block builder from verified ReferenceCircuit instances."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._wiring import manhattan_wires
from scripts.carrier.blocks.symbol_registry import lib_id_for_token, resolve_symbol_pin
from scripts.carrier.model.block import LocalLabel, PlacedComponent, Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from scripts.carrier.model.refcircuit import ExternalPart, ReferenceCircuit, StrapPin
from scripts.carrier.model.templates import PinGroup
from scripts.carrier.registry import get_part


PASSIVE_LIB: dict[str, str] = {
    "schottky_SS14": "Device:D_Schottky",
}

SUPPLY_NET_LIBS: dict[str, str] = {
    "+3V3": "power:+3V3",
    "+3V3_SC": "power:+3V3",
    "+5V": "power:+5V",
    "+VIN": "power:+5V",
    "+1V8": "power:+3V3",
    "+2V5": "power:+3V3",
    "VDD": "power:+3V3",
    "VCC": "power:+3V3",
}


@dataclass
class IcBlockBuildResult:
    components: list[PlacedComponent] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    local_labels: list[LocalLabel] = field(default_factory=list)
    pin_tap_points: dict[str, Point] = field(default_factory=dict)


def _is_capacitor_token(part_token: str) -> bool:
    lowered = part_token.lower()
    return (
        lowered.endswith("_x7r")
        or lowered.endswith("_x5r")
        or lowered.endswith("_c0g")
        or "nf_" in lowered
        or lowered.startswith("1n_")
        or "u_" in lowered
        or "p_" in lowered
    )


def _lib_id_for_token(part_token: str) -> str:
    if part_token in PASSIVE_LIB:
        return PASSIVE_LIB[part_token]
    if _is_capacitor_token(part_token):
        return "Device:C"
    return "Device:R"


def _classify_pin_group(external_part: ExternalPart) -> PinGroup:
    token = external_part.part_token.lower()
    if external_part.to_net in {"GND", "CHASSIS_GND", "VSS"} and _is_capacitor_token(
        external_part.part_token
    ):
        return PinGroup.DECOUPLING
    if external_part.to_net in {"GND", "CHASSIS_GND"} and not _is_capacitor_token(
        external_part.part_token
    ):
        return PinGroup.TERMINATION
    if "k_" in token or token.endswith("_1%"):
        if external_part.to_net in SUPPLY_NET_LIBS:
            return PinGroup.PULL_UP
        return PinGroup.SERIES
    if _is_capacitor_token(external_part.part_token):
        return PinGroup.SIGNAL_FILTER
    return PinGroup.SERIES


def _placed_passive(reference: str, part_token: str, position: Point) -> PlacedComponent:
    part = get_part(part_token)
    return PlacedComponent(
        lib_id=_lib_id_for_token(part_token),
        reference=reference,
        value=part.value,
        position=position,
        footprint=part.footprint,
    )


def _power_symbol_base(
    ic_reference: str,
    part_mpn: str,
    registry_token: str,
) -> int:
    """Deterministic #PWR index (stable across processes; low collision rate)."""
    seed = f"{ic_reference}:{part_mpn}:{registry_token}"
    total = 0
    for index, character in enumerate(seed):
        total += ord(character) * (index + 17)
    return (total % 89000) + 1000


def _resolve_ic_pin(
    *,
    geometry_cache: SymbolGeometryCache,
    ic_lib_id: str,
    ic_anchor: Point,
    registry_token: str,
    refcircuit_pin: str,
) -> Point:
    symbol_pin = resolve_symbol_pin(refcircuit_pin, registry_token)
    try:
        return geometry_cache.absolute_pin_by_name(
            ic_lib_id,
            ic_anchor,
            symbol_pin,
        )
    except KeyError as missing:
        raise KeyError(
            f"Symbol {ic_lib_id!r} has no pin for refcircuit pin {refcircuit_pin!r} "
            f"(resolved {symbol_pin!r}) on {registry_token}"
        ) from missing


def _supply_point_for_net(
    *,
    net_name: str,
    supply_points: dict[str, Point],
    ground_point: Point,
) -> Point:
    if net_name in {"GND", "CHASSIS_GND", "VSS"}:
        return ground_point
    if net_name in supply_points:
        return supply_points[net_name]
    raise KeyError(f"No supply anchor for net {net_name!r}")


def build_ic_block(
    *,
    ref_circuit: ReferenceCircuit,
    ic_reference: str,
    ic_anchor: Point,
    registry_token: str,
    geometry_cache: SymbolGeometryCache,
    designator_prefix: str,
    ic_lib_id: str | None = None,
) -> IcBlockBuildResult:
    """Place IC + externals; wire every external part to resolved IC pin geometry."""
    if not ref_circuit.minimum_circuit_verified:
        raise RuntimeError(
            f"Refusing to build unverified refcircuit {ref_circuit.part_mpn}"
        )

    resolved_lib_id = ic_lib_id or lib_id_for_token(registry_token)
    result = IcBlockBuildResult()
    ic_part = get_part(registry_token)
    result.components.append(
        PlacedComponent(
            lib_id=resolved_lib_id,
            reference=ic_reference,
            value=ic_part.value,
            position=ic_anchor,
            footprint=ref_circuit.footprint,
        )
    )

    ground_anchor = Point(snap_to_grid(ic_anchor.x - 25.4), snap_to_grid(ic_anchor.y + 50.8))
    power_base = _power_symbol_base(
        ic_reference,
        ref_circuit.part_mpn,
        registry_token,
    )
    ground_reference = f"#PWR{power_base}"
    result.components.append(
        PlacedComponent("power:GND", ground_reference, "GND", ground_anchor, "")
    )

    supply_points: dict[str, Point] = {}
    default_supply = ref_circuit.supply_rail or "+3V3"
    supply_anchor = Point(snap_to_grid(ic_anchor.x + 50.8), snap_to_grid(ic_anchor.y - 25.4))
    supply_lib = SUPPLY_NET_LIBS.get(default_supply, "power:+3V3")
    supply_reference = f"#PWR{power_base + 1}"
    result.components.append(
        PlacedComponent(
            supply_lib,
            supply_reference,
            default_supply,
            supply_anchor,
            "",
        )
    )
    supply_points[default_supply] = supply_anchor
    result.local_labels.append(LocalLabel(default_supply, supply_anchor))

    for extra_net in ("+3V3", "+3V3_SC", "+5V", "+VIN", "VDD", "VCC"):
        if extra_net in supply_points:
            continue
        if any(
            part.to_net == extra_net
            for part in ref_circuit.external_parts
        ) or any(strap.tied_to == extra_net for strap in ref_circuit.strap_pins):
            extra_y = snap_to_grid(supply_anchor.y + len(supply_points) * 7.62)
            extra_point = Point(supply_anchor.x, extra_y)
            extra_lib = SUPPLY_NET_LIBS.get(extra_net, "power:+3V3")
            result.components.append(
                PlacedComponent(
                    extra_lib,
                    f"#PWR{power_base + len(supply_points) + 1}",
                    extra_net,
                    extra_point,
                    "",
                )
            )
            supply_points[extra_net] = extra_point
            result.local_labels.append(LocalLabel(extra_net, extra_point))

    passive_y = snap_to_grid(ic_anchor.y - 12.7)
    passive_index = 0
    group_counts: dict[PinGroup, int] = {}

    for external_part in ref_circuit.external_parts:
        pin_point = _resolve_ic_pin(
            geometry_cache=geometry_cache,
            ic_lib_id=resolved_lib_id,
            ic_anchor=ic_anchor,
            registry_token=registry_token,
            refcircuit_pin=external_part.from_pin,
        )
        result.pin_tap_points.setdefault(external_part.from_pin, pin_point)

        pin_group = _classify_pin_group(external_part)
        group_index = group_counts.get(pin_group, 0)
        group_counts[pin_group] = group_index + 1

        if ref_circuit.layout_template is not None:
            group_offset = ref_circuit.layout_template.offset_for(pin_group)
            part_position = Point(
                snap_to_grid(ic_anchor.x + group_offset.offset.x),
                snap_to_grid(
                    ic_anchor.y
                    + group_offset.offset.y
                    + group_index * group_offset.stride.y
                ),
            )
        else:
            part_position = Point(
                snap_to_grid(ic_anchor.x + 38.1),
                snap_to_grid(passive_y + passive_index * 5.08),
            )
            passive_index += 1

        passive_index += 1
        reference = f"{designator_prefix}{ic_reference}{passive_index}"
        result.components.append(
            _placed_passive(reference, external_part.part_token, part_position)
        )

        if external_part.to_net in {"GND", "CHASSIS_GND", "VSS"}:
            result.wires.extend(manhattan_wires(part_position, ground_anchor))
            result.wires.extend(manhattan_wires(pin_point, part_position))
        elif external_part.to_net in SUPPLY_NET_LIBS:
            rail = _supply_point_for_net(
                net_name=external_part.to_net,
                supply_points=supply_points,
                ground_point=ground_anchor,
            )
            result.wires.extend(manhattan_wires(part_position, rail))
            result.wires.extend(manhattan_wires(pin_point, part_position))
        elif external_part.from_pin != external_part.to_net:
            result.wires.extend(manhattan_wires(pin_point, part_position))
            result.local_labels.append(
                LocalLabel(external_part.to_net, part_position)
            )
        else:
            result.wires.extend(manhattan_wires(pin_point, part_position))

    for strap_pin in ref_circuit.strap_pins:
        pin_point = _resolve_ic_pin(
            geometry_cache=geometry_cache,
            ic_lib_id=resolved_lib_id,
            ic_anchor=ic_anchor,
            registry_token=registry_token,
            refcircuit_pin=strap_pin.pin,
        )
        tie_point = _supply_point_for_net(
            net_name=strap_pin.tied_to,
            supply_points=supply_points,
            ground_point=ground_anchor,
        )
        result.wires.extend(manhattan_wires(pin_point, tie_point))

    for pin_name, override_net in ref_circuit.pin_net_overrides:
        pin_point = _resolve_ic_pin(
            geometry_cache=geometry_cache,
            ic_lib_id=resolved_lib_id,
            ic_anchor=ic_anchor,
            registry_token=registry_token,
            refcircuit_pin=pin_name,
        )
        result.local_labels.append(LocalLabel(override_net, pin_point))
        result.pin_tap_points[pin_name] = pin_point

    return result
