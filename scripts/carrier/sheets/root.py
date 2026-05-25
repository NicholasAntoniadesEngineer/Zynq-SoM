"""Emit the root ``carrier_template.kicad_sch`` and all sub-sheets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import kicad_sch_api as ksa

from scripts.carrier.build_logs import BlockStats
from scripts.carrier.emit.kicad_sch import BlockEmissionStats, emit_block
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point, snap_to_grid
from scripts.carrier.model.interface import SheetEdge
from scripts.carrier.model.nets import is_power_rail
from scripts.carrier.sheets.layout import ROOT_ORIGIN_MM, pack_sheet_placements


POWER_SYMBOL_LIBS: dict[str, str] = {
    "GND": "power:GND",
    "+3V3": "power:+3V3",
    "+3V3_SC": "power:+3V3",
    "+5V": "power:+5V",
    "+VIN": "power:+5V",
    "+1V8": "power:+3V3",
    "+2V5": "power:+3V3",
    "CHASSIS_GND": "power:GND",
}


@dataclass(frozen=True)
class RootEmissionResult:
    root_schematic_path: Path
    root_uuid: str
    block_stats: tuple[BlockStats, ...]
    child_sheet_count: int
    hierarchical_pin_count: int


def _edge_for_hierarchical_pin(edge: SheetEdge) -> str:
    return edge.value


def _connect_shared_nets_on_root(
    root_schematic: ksa.Schematic,
    net_to_sheet_pins: dict[str, list[tuple[Point, Point]]],
) -> float:
    """Stitch shared power nets via a vertical bus and horizontal stubs."""
    bus_x = snap_to_grid(ROOT_ORIGIN_MM + 12.7)
    for net_name, pin_endpoints in net_to_sheet_pins.items():
        if not is_power_rail(net_name):
            continue
        if len(pin_endpoints) < 2:
            continue

        pin_points = [pin_point for _sheet_corner, pin_point in pin_endpoints]
        min_pin_y = min(pin_point.y for pin_point in pin_points)
        max_pin_y = max(pin_point.y for pin_point in pin_points)
        root_schematic.add_wire(
            (bus_x, min_pin_y),
            (bus_x, max_pin_y),
        )
        for pin_point in pin_points:
            root_schematic.add_wire(
                (bus_x, pin_point.y),
                pin_point.as_tuple(),
            )
    return bus_x


def _emit_root_power_symbols(
    root_schematic: ksa.Schematic,
    net_to_sheet_pins: dict[str, list[tuple[Point, Point]]],
    *,
    bus_x: float,
) -> None:
    """Place global power symbols on the bus and wire each net to its bus Y."""
    power_nets = sorted(
        net_name
        for net_name in net_to_sheet_pins
        if is_power_rail(net_name)
    )
    if not power_nets:
        return

    power_ref_index = 100
    for net_name in power_nets:
        pin_endpoints = net_to_sheet_pins[net_name]
        if not pin_endpoints:
            continue
        pin_points = [pin_point for _sheet_corner, pin_point in pin_endpoints]
        bus_y = snap_to_grid(min(pin_point.y for pin_point in pin_points))
        lib_id = POWER_SYMBOL_LIBS.get(net_name, "power:+3V3")
        symbol_position = (bus_x, bus_y)
        root_schematic.components.add(
            lib_id,
            reference=f"#PWR{power_ref_index}",
            value=net_name,
            position=symbol_position,
        )
        power_ref_index += 1
        root_schematic.add_wire(symbol_position, (bus_x, bus_y))


def emit_hierarchical_project(
    blocks: dict[str, Block],
    output_dir: Path,
    root_filename: str = "carrier_template.kicad_sch",
) -> RootEmissionResult:
    if not blocks:
        raise ValueError("emit_hierarchical_project: blocks dict is empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir = output_dir / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    root_schematic = ksa.create_schematic("Zynq SoM Carrier")
    root_schematic.set_paper_size("A1")
    root_schematic.title_block["title"] = "Zynq SoM Carrier - Hierarchical"
    root_schematic.title_block["rev"] = "A"
    root_schematic.title_block["company"] = "Zynq-SoM"
    root_uuid = root_schematic.uuid

    block_stats: list[BlockStats] = []
    net_to_sheet_pins: dict[str, list[tuple[Point, Point]]] = {}
    total_hier_pins = 0

    sheet_placements = pack_sheet_placements(blocks)

    for sheet_placement in sheet_placements:
        block_name = sheet_placement.block_name
        block = blocks[block_name]
        sheet_origin = sheet_placement.origin
        sheet_width = sheet_placement.width_mm
        sheet_height = sheet_placement.height_mm
        sheet_filename = f"sheets/{block_name}.kicad_sch"
        sheet_uuid = root_schematic.add_sheet(
            name=block_name,
            filename=sheet_filename,
            position=sheet_origin.as_tuple(),
            size=(sheet_width, sheet_height),
            uuid=str(uuid.uuid4()),
        )

        for hierarchical_pin in block.hierarchical_pins:
            root_schematic.add_sheet_pin(
                sheet_uuid=sheet_uuid,
                name=hierarchical_pin.net_name,
                pin_type=hierarchical_pin.direction.value,
                edge=_edge_for_hierarchical_pin(hierarchical_pin.edge),
                position_along_edge=hierarchical_pin.position_along_edge,
            )
            if hierarchical_pin.edge == SheetEdge.RIGHT:
                pin_x = sheet_origin.x + sheet_width
            elif hierarchical_pin.edge == SheetEdge.LEFT:
                pin_x = sheet_origin.x
            else:
                raise NotImplementedError(
                    f"Root sheet pin placement for edge {hierarchical_pin.edge} "
                    "is not implemented"
                )
            pin_y = sheet_origin.y + hierarchical_pin.position_along_edge
            pin_point = Point(snap_to_grid(pin_x), snap_to_grid(pin_y))
            net_to_sheet_pins.setdefault(hierarchical_pin.net_name, []).append(
                (sheet_origin, pin_point)
            )
            total_hier_pins += 1

        sub_sheet_path = sheets_dir / f"{block_name}.kicad_sch"
        emission_stats: BlockEmissionStats = emit_block(
            block=block,
            output_path=sub_sheet_path,
            parent_uuid=root_uuid,
            sheet_uuid=sheet_uuid,
        )
        block_stats.append(
            BlockStats(
                block_name=emission_stats.block_name,
                schematic_path=emission_stats.schematic_path,
                placed_symbol_count=emission_stats.placed_symbol_count,
                wire_count=emission_stats.wire_count,
                junction_count=emission_stats.junction_count,
                local_label_count=emission_stats.local_label_count,
                hierarchical_label_count=emission_stats.hierarchical_label_count,
                sheet_pin_count=len(block.hierarchical_pins),
            )
        )

    bus_x = _connect_shared_nets_on_root(root_schematic, net_to_sheet_pins)
    _emit_root_power_symbols(root_schematic, net_to_sheet_pins, bus_x=bus_x)

    root_path = output_dir / root_filename
    root_schematic.save_as(root_path)

    return RootEmissionResult(
        root_schematic_path=root_path,
        root_uuid=root_uuid,
        block_stats=tuple(block_stats),
        child_sheet_count=len(blocks),
        hierarchical_pin_count=total_hier_pins,
    )
