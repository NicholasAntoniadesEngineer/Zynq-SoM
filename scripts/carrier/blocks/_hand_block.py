"""Hand-wired block helpers and refcircuit section builder (usb_pd pattern)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.carrier.blocks._block_common import (
    CARRIER_SYMBOLS,
    HIER_STUB_LENGTH_MM,
    INTERIOR_MARGIN_MM,
    IoAssignmentRow,
    a4_layout,
    build_hier_pins_from_rows,
    connect_pin_to_tap,
    deconflict_label_y,
    hier_channel_x,
    hier_edge_x,
    hier_pin_layout,
    load_io_rows,
    pin_direction_for_interface,
    position_along_edge_for_label_y,
)
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._ic_block import IcBlockBuildResult, build_ic_block
from scripts.carrier.blocks._wiring import manhattan_wires
from scripts.carrier.blocks.signal_maps import unique_carrier_signals
from scripts.carrier.blocks.symbol_registry import lib_id_for_token, resolve_symbol_pin
from scripts.carrier.model.block import Block, BlockLayout, LocalLabel, PlacedComponent, Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from scripts.carrier.model.interface import HierarchicalPin, PinDirection, SheetEdge
from scripts.carrier.model.nets import is_power_rail
from scripts.carrier.model.refcircuit import ReferenceCircuit
from scripts.carrier.symbols.io_library import emit_io_connector_symbol, pin_name_for_carrier_signal


IO_SYMBOLS_DIR = Path(CARRIER_SYMBOLS).parent / "generated"
CONNECTOR_X_MM = snap_to_grid(35.56)


def connect(point_a: Point, point_b: Point) -> list[Wire]:
    return manhattan_wires(point_a, point_b)


def inter_wires_from_pin_maps(
    *,
    source_pin_map: dict[str, Point],
    geometry_cache: SymbolGeometryCache,
    dest_lib_id: str,
    dest_anchor: Point,
    signal_map: dict[str, str],
) -> tuple[Wire, ...]:
    """Wire IO symbol pins to destination symbol pins via explicit name map."""
    wires: list[Wire] = []
    for carrier_signal, dest_pin in signal_map.items():
        source_point = source_pin_map.get(carrier_signal)
        if source_point is None:
            continue
        try:
            dest_point = geometry_cache.absolute_pin_by_name(
                dest_lib_id,
                dest_anchor,
                dest_pin,
            )
        except KeyError:
            continue
        wires.extend(connect(source_point, dest_point))
    return tuple(wires)


def place_power_symbol(
    lib_id: str,
    reference: str,
    value: str,
    position: Point,
) -> PlacedComponent:
    return PlacedComponent(
        lib_id=lib_id,
        reference=reference,
        value=value,
        position=position,
        footprint="",
    )


def add_hier_pin_from_tap(
    *,
    net_name: str,
    tap: Point,
    direction: PinDirection,
    paper_width_mm: float,
    edge: SheetEdge = SheetEdge.RIGHT,
    label_y: float | None = None,
    min_label_y: float | None = None,
) -> tuple[HierarchicalPin, list[Wire]]:
    resolved_label_y = snap_to_grid(label_y if label_y is not None else tap.y)
    resolved_min_y = (
        snap_to_grid(min_label_y)
        if min_label_y is not None
        else snap_to_grid(resolved_label_y - INTERIOR_MARGIN_MM)
    )
    hierarchical_pin, tap_point, hier_point = hier_pin_layout(
        net_name=net_name,
        direction=direction,
        label_y=resolved_label_y,
        min_label_y=resolved_min_y,
        paper_width_mm=paper_width_mm,
        edge=edge,
    )
    wires = connect(tap, hier_point)
    return hierarchical_pin, wires


def _signal_to_pin_map(
    ref_circuit: ReferenceCircuit,
    ic_build: IcBlockBuildResult,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for external_part in ref_circuit.external_parts:
        if external_part.from_pin != external_part.to_net:
            mapping[external_part.to_net] = external_part.from_pin
    for pin_name, override_net in ref_circuit.pin_net_overrides:
        mapping[override_net] = pin_name
    for pin_name in ic_build.pin_tap_points:
        mapping[pin_name] = pin_name
    for local_label in ic_build.local_labels:
        if local_label.net_name not in mapping:
            mapping[local_label.net_name] = local_label.net_name
    return mapping


def _resolve_tap_source(
    carrier_signal: str,
    *,
    signal_to_pin: dict[str, str],
    ic_build: IcBlockBuildResult,
) -> Point | None:
    ref_pin = signal_to_pin.get(carrier_signal)
    if ref_pin is not None and ref_pin in ic_build.pin_tap_points:
        return ic_build.pin_tap_points[ref_pin]
    for local_label in ic_build.local_labels:
        if local_label.net_name == carrier_signal:
            return local_label.position
    if carrier_signal in ic_build.pin_tap_points:
        return ic_build.pin_tap_points[carrier_signal]
    return None


def _require_tap_sources(
    *,
    block_name: str,
    io_rows: tuple[IoAssignmentRow, ...],
    tap_sources: dict[str, Point],
) -> None:
    missing: list[str] = []
    seen: set[str] = set()
    for row in io_rows:
        if row.carrier_signal in seen:
            continue
        seen.add(row.carrier_signal)
        if row.carrier_signal not in tap_sources:
            missing.append(
                f"{row.carrier_signal} (destination={row.destination})"
            )
    if missing:
        raise ValueError(
            f"{block_name}: hierarchical signals without symbol pin wiring: "
            + ", ".join(missing)
        )


def _renumber_power_refs(components: list[PlacedComponent], offset: int) -> None:
    for index, component in enumerate(components):
        if component.reference.startswith("#PWR"):
            components[index] = PlacedComponent(
                lib_id=component.lib_id,
                reference=f"#PWR{offset + index}",
                value=component.value,
                position=component.position,
                footprint=component.footprint,
                rotation=component.rotation,
                properties=component.properties,
            )


@dataclass(frozen=True)
class HandSectionMerge:
    name: str
    title: str
    sections: tuple[Block, ...]
    inter_wires: tuple[Wire, ...] = ()


POWER_RAIL_SYMBOL_OFFSET_MM = snap_to_grid(25.4)


_POWER_SYMBOL_LIBS: dict[str, str] = {
    "GND": "power:GND",
    "+3V3": "power:+3V3",
    "+3V3_SC": "power:+3V3",
    "+1V8": "power:+1V8",
    "+VIN": "power:+5V",
    "+VCCO_13": "power:+3V3",
    "+VCCO_33": "power:+3V3",
    "+VCCO_34": "power:+3V3",
    "+VCCO_35": "power:+3V3",
}


def build_power_distribution_section(
    *,
    name: str,
    title: str,
    io_destinations: tuple[str, ...],
) -> Block:
    """Wire hierarchical power nets to ``#PWR`` symbols."""
    io_rows = load_io_rows(*io_destinations)
    power_signals: list[str] = []
    seen_signals: set[str] = set()
    for row in io_rows:
        if not is_power_rail(row.carrier_signal):
            continue
        if row.carrier_signal in seen_signals:
            continue
        seen_signals.add(row.carrier_signal)
        power_signals.append(row.carrier_signal)
    power_signals.sort()

    if not power_signals:
        raise ValueError(f"{name}: no power signals in destinations {io_destinations}")

    layout = a4_layout()
    components: list[PlacedComponent] = []
    tap_sources: dict[str, Point] = {}
    hier_x = hier_edge_x(layout.width_mm)
    channel_x = hier_channel_x(layout.width_mm)
    cursor_y = snap_to_grid(25.4)
    for index, signal in enumerate(power_signals):
        lib_id = _POWER_SYMBOL_LIBS.get(signal, "power:+3V3")
        position = Point(
            snap_to_grid(hier_x - HIER_STUB_LENGTH_MM - POWER_RAIL_SYMBOL_OFFSET_MM),
            cursor_y,
        )
        components.append(
            place_power_symbol(
                lib_id=lib_id,
                reference=f"#PWR{index + 1}",
                value=signal,
                position=position,
            )
        )
        tap_sources[signal] = position
        cursor_y += snap_to_grid(10.16)

    filtered_rows = tuple(
        row for row in io_rows if row.carrier_signal in tap_sources
    )
    hierarchical_pins, hier_wires, tap_points = build_hier_pins_from_rows(
        filtered_rows,
        paper_width_mm=layout.width_mm,
        align_y_to_pin={signal: point.y for signal, point in tap_sources.items()},
    )
    aligned_components: list[PlacedComponent] = []
    for hierarchical_pin in hierarchical_pins:
        signal = hierarchical_pin.net_name
        if hierarchical_pin.label_position is None:
            continue
        label_y = hierarchical_pin.label_position.y
        existing = next(
            component for component in components if component.value == signal
        )
        aligned_components.append(
            place_power_symbol(
                lib_id=existing.lib_id,
                reference=existing.reference,
                value=signal,
                position=Point(existing.position.x, label_y),
            )
        )
        tap_sources[signal] = Point(existing.position.x, label_y)

    wires: list[Wire] = list(hier_wires)
    for carrier_signal, tap_point in tap_points.items():
        source = tap_sources.get(carrier_signal)
        if source is not None:
            wires.extend(connect_pin_to_tap(source, tap_point, channel_x))

    _require_tap_sources(
        block_name=name,
        io_rows=filtered_rows,
        tap_sources=tap_sources,
    )

    return Block(
        name=name,
        title=title,
        layout=layout,
        components=tuple(aligned_components),
        wires=tuple(wires),
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=(str(CARRIER_SYMBOLS),),
    )


def _is_hier_route_wire(wire: Wire, hier_x: float, stub_x: float) -> bool:
    for point in (wire.start, wire.end):
        if abs(point.x - hier_x) < 0.01 or abs(point.x - stub_x) < 0.01:
            return True
    return False


def _extract_pin_sources_for_hier(
    section_wires: list[Wire],
    hierarchical_pins: tuple[HierarchicalPin, ...],
    stub_x: float,
    hier_x: float,
) -> dict[str, Point]:
    pin_sources: dict[str, Point] = {}
    for hierarchical_pin in hierarchical_pins:
        if hierarchical_pin.label_position is None:
            continue
        label_y = hierarchical_pin.label_position.y
        pin_source: Point | None = None
        for wire in section_wires:
            if abs(wire.end.y - label_y) < 0.01 and wire.end.x <= stub_x + 0.01:
                if wire.start.x < wire.end.x - 0.01:
                    pin_source = wire.start
                    break
            if abs(wire.start.y - label_y) < 0.01 and wire.start.x <= stub_x + 0.01:
                if wire.end.x < wire.start.x - 0.01:
                    pin_source = wire.end
                    break
        if pin_source is None:
            for wire in section_wires:
                if abs(wire.end.x - hier_x) < 0.01 and abs(wire.end.y - label_y) < 0.01:
                    pin_source = wire.start
                    break
        if pin_source is not None:
            pin_sources[hierarchical_pin.net_name] = pin_source
    return pin_sources


def _rebuild_hier_routing_for_section(
    *,
    section: Block,
    section_wires: list[Wire],
    pin_sources: dict[str, Point],
    label_y_by_net: dict[str, float],
    min_label_y: float,
) -> tuple[list[Wire], list[HierarchicalPin]]:
    paper_width_mm = section.layout.width_mm
    hier_x = hier_edge_x(paper_width_mm)
    stub_x = snap_to_grid(hier_x - HIER_STUB_LENGTH_MM)
    channel_x = hier_channel_x(paper_width_mm)

    kept_wires = [
        wire
        for wire in section_wires
        if not _is_hier_route_wire(wire, hier_x, stub_x)
    ]

    rebuilt_pins: list[HierarchicalPin] = []
    routing_wires: list[Wire] = []
    for hierarchical_pin in section.hierarchical_pins:
        if hierarchical_pin.label_position is None:
            rebuilt_pins.append(hierarchical_pin)
            continue
        label_y = label_y_by_net.get(
            hierarchical_pin.net_name,
            hierarchical_pin.label_position.y,
        )
        rebuilt_pin, tap_point, hier_point = hier_pin_layout(
            net_name=hierarchical_pin.net_name,
            direction=hierarchical_pin.direction,
            label_y=label_y,
            min_label_y=min_label_y,
            paper_width_mm=paper_width_mm,
            edge=hierarchical_pin.edge,
        )
        routing_wires.extend(manhattan_wires(tap_point, hier_point))
        pin_source = pin_sources.get(hierarchical_pin.net_name)
        if pin_source is not None:
            routing_wires.extend(
                connect_pin_to_tap(pin_source, tap_point, channel_x)
            )
        rebuilt_pins.append(rebuilt_pin)

    return kept_wires + routing_wires, rebuilt_pins


def _deconflict_merged_hier_pins(
    sections: tuple[Block, ...],
    section_wires: list[list[Wire]],
) -> list[HierarchicalPin]:
    """Section-aware Y packing with full hier wire rebuild."""
    occupied_y: set[float] = set()
    all_label_ys: list[float] = []
    section_pin_entries: list[
        list[tuple[HierarchicalPin, float, dict[str, Point]]]
    ] = []

    for section_index, section in enumerate(sections):
        paper_width_mm = section.layout.width_mm
        hier_x = hier_edge_x(paper_width_mm)
        stub_x = snap_to_grid(hier_x - HIER_STUB_LENGTH_MM)
        pin_sources = _extract_pin_sources_for_hier(
            section_wires[section_index],
            section.hierarchical_pins,
            stub_x,
            hier_x,
        )
        section_entries: list[tuple[HierarchicalPin, float, dict[str, Point]]] = []
        for hierarchical_pin in section.hierarchical_pins:
            if hierarchical_pin.label_position is None:
                continue
            desired_y = hierarchical_pin.label_position.y
            section_entries.append((hierarchical_pin, desired_y, pin_sources))
        section_entries.sort(key=lambda item: item[1])
        section_pin_entries.append(section_entries)

    label_y_by_net: dict[str, float] = {}
    for section_entries in section_pin_entries:
        for hierarchical_pin, desired_y, _pin_sources in section_entries:
            label_y = deconflict_label_y(desired_y, occupied_y)
            label_y_by_net[hierarchical_pin.net_name] = label_y
            all_label_ys.append(label_y)

    if not all_label_ys:
        return [
            hierarchical_pin
            for section in sections
            for hierarchical_pin in section.hierarchical_pins
        ]

    min_label_y = min(all_label_ys)
    adjusted_pins: list[HierarchicalPin] = []

    for section_index, section in enumerate(sections):
        paper_width_mm = section.layout.width_mm
        hier_x = hier_edge_x(paper_width_mm)
        stub_x = snap_to_grid(hier_x - HIER_STUB_LENGTH_MM)
        pin_sources = _extract_pin_sources_for_hier(
            section_wires[section_index],
            section.hierarchical_pins,
            stub_x,
            hier_x,
        )
        section_wires[section_index], rebuilt_pins = _rebuild_hier_routing_for_section(
            section=section,
            section_wires=section_wires[section_index],
            pin_sources=pin_sources,
            label_y_by_net=label_y_by_net,
            min_label_y=min_label_y,
        )
        adjusted_pins.extend(rebuilt_pins)

    return adjusted_pins


def merge_hand_sections(merged: HandSectionMerge) -> Block:
    if not merged.sections:
        raise ValueError("merge_hand_sections: sections must not be empty")

    layout = merged.sections[0].layout
    components: list[PlacedComponent] = []
    section_wires: list[list[Wire]] = []
    local_labels: list[LocalLabel] = []
    library_paths: list[str] = []

    power_ref_offset = 1000
    for section in merged.sections:
        section_components = list(section.components)
        _renumber_power_refs(section_components, power_ref_offset)
        power_ref_offset += len(section_components) + 50
        components.extend(section_components)
        section_wires.append(list(section.wires))
        local_labels.extend(section.local_labels)
        for library_path in section.symbol_library_paths:
            if library_path not in library_paths:
                library_paths.append(library_path)

    hierarchical_pins = _deconflict_merged_hier_pins(merged.sections, section_wires)
    wires: list[Wire] = []
    for wire_list in section_wires:
        wires.extend(wire_list)

    wires.extend(merged.inter_wires)

    seen_hier: set[str] = set()
    for hierarchical_pin in hierarchical_pins:
        if hierarchical_pin.net_name in seen_hier:
            raise ValueError(
                f"{merged.name}: duplicate hierarchical pin "
                f"{hierarchical_pin.net_name!r}"
            )
        seen_hier.add(hierarchical_pin.net_name)

    return Block(
        name=merged.name,
        title=merged.title,
        layout=layout,
        components=tuple(components),
        wires=tuple(wires),
        local_labels=tuple(local_labels),
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=tuple(library_paths),
    )


def build_io_symbol_section(
    *,
    symbol_name: str,
    ic_reference: str,
    io_destinations: tuple[str, ...],
    ic_anchor: Point | None = None,
) -> tuple[Block, SymbolGeometryCache, dict[str, Point]]:
    """Place dynamic IO connector symbol only; no hierarchical pins or hier wires."""
    io_rows = load_io_rows(*io_destinations)
    if not io_rows:
        raise ValueError(
            f"build_io_symbol_section: no io rows for {io_destinations}"
        )

    carrier_signals = unique_carrier_signals(io_rows)
    symbol_path = emit_io_connector_symbol(
        symbol_name=symbol_name,
        pin_names=carrier_signals,
        output_path=IO_SYMBOLS_DIR / f"{symbol_name}.kicad_sym",
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((symbol_path,))

    anchor = ic_anchor or Point(CONNECTOR_X_MM, snap_to_grid(50.8 + len(carrier_signals) * 1.27))
    lib_id = f"{symbol_name}:{symbol_name}"

    components = [
        PlacedComponent(
            lib_id=lib_id,
            reference=ic_reference,
            value=symbol_name,
            position=anchor,
            footprint="",
        )
    ]

    pin_by_carrier: dict[str, Point] = {}
    for carrier_signal in carrier_signals:
        pin_key = pin_name_for_carrier_signal(carrier_signal)
        pin_by_carrier[carrier_signal] = geometry_cache.absolute_pin_by_name(
            lib_id,
            anchor,
            pin_key,
        )

    _require_tap_sources(
        block_name=symbol_name,
        io_rows=io_rows,
        tap_sources=pin_by_carrier,
    )

    section = Block(
        name=symbol_name,
        title=symbol_name,
        layout=a4_layout(),
        components=tuple(components),
        wires=(),
        hierarchical_pins=(),
        symbol_library_paths=(str(symbol_path),),
    )
    return section, geometry_cache, pin_by_carrier


def build_io_connector_section(
    *,
    symbol_name: str,
    ic_reference: str,
    io_destinations: tuple[str, ...],
    signal_pin_map: dict[str, str] | None = None,
    ic_anchor: Point | None = None,
) -> tuple[Block, SymbolGeometryCache, dict[str, Point]]:
    """Place dynamic IO connector; return section with pin tap points keyed by carrier_signal."""
    io_rows = load_io_rows(*io_destinations)
    if not io_rows:
        raise ValueError(
            f"build_io_connector_section: no io rows for {io_destinations}"
        )

    carrier_signals = unique_carrier_signals(io_rows)
    symbol_path = emit_io_connector_symbol(
        symbol_name=symbol_name,
        pin_names=carrier_signals,
        output_path=IO_SYMBOLS_DIR / f"{symbol_name}.kicad_sym",
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((symbol_path,))

    anchor = ic_anchor or Point(CONNECTOR_X_MM, snap_to_grid(50.8 + len(carrier_signals) * 1.27))
    lib_id = f"{symbol_name}:{symbol_name}"

    components = [
        PlacedComponent(
            lib_id=lib_id,
            reference=ic_reference,
            value=symbol_name,
            position=anchor,
            footprint="",
        )
    ]

    pin_by_carrier: dict[str, Point] = {}
    for carrier_signal in carrier_signals:
        pin_key = pin_name_for_carrier_signal(carrier_signal)
        pin_by_carrier[carrier_signal] = geometry_cache.absolute_pin_by_name(
            lib_id,
            anchor,
            pin_key,
        )

    layout = a4_layout()
    align_y = {signal: point.y for signal, point in pin_by_carrier.items()}
    hierarchical_pins, hier_wires, tap_points = build_hier_pins_from_rows(
        io_rows,
        paper_width_mm=layout.width_mm,
        align_y_to_pin=align_y,
    )

    wires: list[Wire] = list(hier_wires)
    channel_x = hier_channel_x(layout.width_mm)
    for carrier_signal, tap_point in tap_points.items():
        source = pin_by_carrier.get(carrier_signal)
        if source is None:
            continue
        wires.extend(connect_pin_to_tap(source, tap_point, channel_x))

    _require_tap_sources(
        block_name=symbol_name,
        io_rows=io_rows,
        tap_sources=pin_by_carrier,
    )

    section = Block(
        name=symbol_name,
        title=symbol_name,
        layout=layout,
        components=tuple(components),
        wires=tuple(wires),
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=(str(symbol_path),),
    )
    return section, geometry_cache, pin_by_carrier


def build_hand_section(
    *,
    name: str,
    title: str,
    ref_circuit: ReferenceCircuit,
    registry_token: str,
    ic_reference: str,
    ic_anchor: Point | None = None,
    io_destinations: tuple[str, ...],
    designator_prefix: str = "C",
    extra_local_labels: tuple[tuple[str, Point], ...] = (),
    ic_lib_id: str | None = None,
    signal_pin_map: dict[str, str] | None = None,
    carrier_signals_filter: frozenset[str] | None = None,
    require_all_hier_wired: bool = True,
) -> Block:
    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    anchor = ic_anchor or Point(101.6, 101.6)
    ic_build = build_ic_block(
        ref_circuit=ref_circuit,
        ic_reference=ic_reference,
        ic_anchor=anchor,
        registry_token=registry_token,
        geometry_cache=geometry_cache,
        designator_prefix=designator_prefix,
        ic_lib_id=ic_lib_id or lib_id_for_token(registry_token),
    )

    io_rows = load_io_rows(*io_destinations)
    if carrier_signals_filter is not None:
        io_rows = tuple(
            row
            for row in io_rows
            if row.carrier_signal in carrier_signals_filter
        )
    layout = a4_layout()

    signal_to_pin = _signal_to_pin_map(ref_circuit, ic_build)
    if signal_pin_map:
        signal_to_pin.update(signal_pin_map)

    resolved_lib_id = ic_lib_id or lib_id_for_token(registry_token)

    align_y: dict[str, float] = {}
    tap_sources: dict[str, Point] = {}
    seen_signals: set[str] = set()
    for row in io_rows:
        if row.carrier_signal in seen_signals:
            continue
        seen_signals.add(row.carrier_signal)
        source = _resolve_tap_source(
            row.carrier_signal,
            signal_to_pin=signal_to_pin,
            ic_build=ic_build,
        )
        if source is not None:
            align_y[row.carrier_signal] = source.y
            tap_sources[row.carrier_signal] = source

    if signal_pin_map:
        for carrier_signal, pin_name in signal_pin_map.items():
            if carrier_signal in tap_sources:
                continue
            symbol_pin = resolve_symbol_pin(pin_name, registry_token)
            try:
                pin_point = geometry_cache.absolute_pin_by_name(
                    resolved_lib_id,
                    anchor,
                    symbol_pin,
                )
            except KeyError:
                continue
            tap_sources[carrier_signal] = pin_point
            align_y[carrier_signal] = pin_point.y

    hierarchical_pins: list[HierarchicalPin] = []
    hier_wires: list[Wire] = []
    tap_points: dict[str, Point] = {}
    if io_rows:
        hierarchical_pins, hier_wires, tap_points = build_hier_pins_from_rows(
            io_rows,
            paper_width_mm=layout.width_mm,
            align_y_to_pin=align_y or None,
        )

    if require_all_hier_wired and io_rows:
        _require_tap_sources(
            block_name=name,
            io_rows=io_rows,
            tap_sources=tap_sources,
        )

    wires: list[Wire] = list(ic_build.wires)
    channel_x = hier_channel_x(layout.width_mm)

    for carrier_signal, tap_point in tap_points.items():
        source = tap_sources.get(carrier_signal)
        if source is not None:
            wires.extend(connect_pin_to_tap(source, tap_point, channel_x))

    wires.extend(hier_wires)

    local_labels = list(ic_build.local_labels)
    for net_name, label_position in extra_local_labels:
        local_labels.append(LocalLabel(net_name, label_position))

    library_paths = [str(CARRIER_SYMBOLS)]
    for generated_path in IO_SYMBOLS_DIR.glob("*.kicad_sym"):
        library_paths.append(str(generated_path.resolve()))

    return Block(
        name=name,
        title=title,
        layout=layout,
        components=tuple(ic_build.components),
        wires=tuple(wires),
        local_labels=tuple(local_labels),
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=tuple(dict.fromkeys(library_paths)),
    )


def wire_hier_from_taps(
    *,
    interface_nets: tuple[tuple[str, PinDirection], ...],
    tap_points: dict[str, Point],
    paper_width_mm: float,
    start_y: float | None = None,
    occupied_y: set[float] | None = None,
) -> tuple[list[HierarchicalPin], list[Wire]]:
    """Hierarchical pins from explicit tap dict with unified edge positions."""
    hierarchical_pins: list[HierarchicalPin] = []
    wires: list[Wire] = []
    cursor_y = start_y if start_y is not None else snap_to_grid(12.7)
    occupied = set(occupied_y or ())

    planned: list[tuple[str, PinDirection, Point, float]] = []
    for net_name, direction in interface_nets:
        tap = tap_points[net_name]
        label_y = deconflict_label_y(max(cursor_y, tap.y), occupied)
        planned.append((net_name, direction, tap, label_y))
        cursor_y = label_y + KICAD_GRID_MM

    if not planned:
        return hierarchical_pins, wires

    min_label_y = min(label_y for *_rest, label_y in planned)
    for net_name, direction, tap, label_y in planned:
        hier_pin, segment_wires = add_hier_pin_from_tap(
            net_name=net_name,
            tap=tap,
            direction=direction,
            paper_width_mm=paper_width_mm,
            label_y=label_y,
            min_label_y=min_label_y,
        )
        hierarchical_pins.append(hier_pin)
        wires.extend(segment_wires)

    return hierarchical_pins, wires
