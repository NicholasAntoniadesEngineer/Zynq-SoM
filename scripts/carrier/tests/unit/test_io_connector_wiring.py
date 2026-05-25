"""IO connector pin tip and merged-block hier Y tests."""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.blocks import all_block_factories
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.model.grid import KICAD_GRID_MM


def _io_pin_connection_wire(block, io_reference: str):
    io_component = next(
        component for component in block.components if component.reference == io_reference
    )
    geometry_cache = SymbolGeometryCache()
    for library_path in block.symbol_library_paths:
        geometry_cache.register_libraries((Path(library_path),))

    first_pin = geometry_cache.absolute_pin_connection_by_name(
        io_component.lib_id,
        io_component.position,
        "1",
    )
    for wire in block.wires:
        if wire.start == first_pin or wire.end == first_pin:
            return wire, first_pin
        if abs(wire.start.x - first_pin.x) <= KICAD_GRID_MM and abs(
            wire.start.y - first_pin.y
        ) <= KICAD_GRID_MM:
            return wire, first_pin
    return None, first_pin


def test_fmc_lpc_first_wire_at_pin_tip() -> None:
    block = all_block_factories()["fmc_lpc"]()
    stub_wire, first_pin = _io_pin_connection_wire(block, "JFMC1")
    assert stub_wire is not None
    assert abs(stub_wire.start.x - first_pin.x) <= KICAD_GRID_MM
    assert abs(stub_wire.start.y - first_pin.y) <= KICAD_GRID_MM


def test_ethernet_merged_hier_pins_have_distinct_y() -> None:
    block = all_block_factories()["ethernet"]()
    label_positions = [
        (hierarchical_pin.net_name, hierarchical_pin.label_position.y)
        for hierarchical_pin in block.hierarchical_pins
        if hierarchical_pin.label_position is not None
    ]
    seen_y: dict[float, str] = {}
    for net_name, label_y in label_positions:
        assert label_y not in seen_y or seen_y[label_y] == net_name, (
            f"ethernet hier Y collision at y={label_y}: "
            f"{seen_y.get(label_y)!r} vs {net_name!r}"
        )
        seen_y[label_y] = net_name


def test_pmod_io_wires_present() -> None:
    block = all_block_factories()["pmod"]()
    io_component = next(
        component for component in block.components if component.reference == "JPMIO1"
    )
    header_components = [
        component
        for component in block.components
        if component.reference in {"JPM1", "JPM2"}
    ]
    assert io_component is not None
    assert len(header_components) == 2
    assert len(block.wires) >= len(block.hierarchical_pins)


def test_usbc_otg_hier_labels_are_wired() -> None:
    block = all_block_factories()["usbc_otg"]()
    wire_endpoints = {
        (wire.start.x, wire.start.y)
        for wire in block.wires
    } | {
        (wire.end.x, wire.end.y)
        for wire in block.wires
    }
    for hierarchical_pin in block.hierarchical_pins:
        label_point = hierarchical_pin.label_position
        assert label_point is not None
        assert (label_point.x, label_point.y) in wire_endpoints, (
            f"usbc_otg hier pin {hierarchical_pin.net_name!r} is unwired"
        )
