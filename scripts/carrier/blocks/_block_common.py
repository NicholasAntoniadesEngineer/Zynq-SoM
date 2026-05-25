"""Shared helpers for carrier block factories."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from scripts.carrier.blocks._wiring import (
    manhattan_wires,
    route_channel,
    route_horizontal,
)
from scripts.carrier.model.block import BlockLayout, Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from scripts.carrier.model.interface import HierarchicalPin, PinDirection, SheetEdge


SCRIPTS_DIR = Path(__file__).resolve().parents[2]
IO_ASSIGNMENT_PATH = SCRIPTS_DIR / "carrier_template" / "io_assignment.csv"
CARRIER_SYMBOLS = (SCRIPTS_DIR / "carrier" / "symbols" / "carrier.kicad_sym").resolve()

PAPER_A4_WIDTH_MM = snap_to_grid(297.0)
PAPER_A4_HEIGHT_MM = snap_to_grid(210.0)
PAPER_A2_WIDTH_MM = snap_to_grid(420.0)
PAPER_A2_HEIGHT_MM = snap_to_grid(594.0)
INTERIOR_MARGIN_MM = snap_to_grid(10.16)
HIER_PIN_SPACING_MM = snap_to_grid(2.54)
HIER_STUB_LENGTH_MM = snap_to_grid(12.7)
HIER_CHANNEL_X_OFFSET_MM = snap_to_grid(38.1)


@dataclass(frozen=True)
class IoAssignmentRow:
    som_connector: str
    som_pin: str
    som_net: str
    side: str
    destination: str
    carrier_signal: str
    interface: str


def load_io_rows(*destinations: str) -> tuple[IoAssignmentRow, ...]:
    if not IO_ASSIGNMENT_PATH.exists():
        raise FileNotFoundError(
            f"io_assignment.csv required at {IO_ASSIGNMENT_PATH}"
        )
    destination_set = frozenset(destinations)
    rows: list[IoAssignmentRow] = []
    with open(IO_ASSIGNMENT_PATH, encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for raw_row in reader:
            destination = raw_row.get("destination", "").strip()
            if destination not in destination_set:
                continue
            carrier_signal = raw_row.get("carrier_signal", "").strip()
            if not carrier_signal:
                continue
            rows.append(
                IoAssignmentRow(
                    som_connector=raw_row["som_connector"],
                    som_pin=raw_row["som_pin"],
                    som_net=raw_row["som_net"],
                    side=raw_row.get("side", ""),
                    destination=destination,
                    carrier_signal=carrier_signal,
                    interface=raw_row.get("interface", ""),
                )
            )
    return tuple(rows)


def pin_direction_for_interface(interface: str) -> PinDirection:
    interface_upper = interface.upper()
    if interface_upper == "POWER":
        return PinDirection.PASSIVE
    if interface_upper in {"I2C", "SPI", "UART", "SWD", "JTAG", "GPIO"}:
        return PinDirection.BIDIRECTIONAL
    return PinDirection.BIDIRECTIONAL


def a4_layout() -> BlockLayout:
    return BlockLayout(
        paper_size="A4",
        width_mm=PAPER_A4_WIDTH_MM,
        height_mm=PAPER_A4_HEIGHT_MM,
        interior_margin_mm=INTERIOR_MARGIN_MM,
    )


def a2_layout() -> BlockLayout:
    return BlockLayout(
        paper_size="A2",
        width_mm=PAPER_A2_WIDTH_MM,
        height_mm=PAPER_A2_HEIGHT_MM,
        interior_margin_mm=INTERIOR_MARGIN_MM,
    )


def hier_edge_x(paper_width_mm: float) -> float:
    return snap_to_grid(paper_width_mm - INTERIOR_MARGIN_MM)


def hier_channel_x(paper_width_mm: float) -> float:
    return snap_to_grid(hier_edge_x(paper_width_mm) - HIER_CHANNEL_X_OFFSET_MM)


def position_along_edge_for_label_y(label_y: float, min_label_y: float) -> float:
    return snap_to_grid(label_y - min_label_y + INTERIOR_MARGIN_MM)


def deconflict_label_y(
    desired_y: float,
    occupied_y: set[float],
    *,
    min_spacing_mm: float = HIER_PIN_SPACING_MM,
) -> float:
    label_y = snap_to_grid(desired_y)
    while label_y in occupied_y:
        label_y = snap_to_grid(label_y + min_spacing_mm)
    occupied_y.add(label_y)
    return label_y


def hier_pin_layout(
    *,
    net_name: str,
    direction: PinDirection,
    label_y: float,
    min_label_y: float,
    paper_width_mm: float,
    edge: SheetEdge = SheetEdge.RIGHT,
) -> tuple[HierarchicalPin, Point, Point]:
    """Build hier pin metadata with unified root/sub-sheet Y coordinates."""
    hier_x = hier_edge_x(paper_width_mm)
    resolved_label_y = snap_to_grid(label_y)
    hier_point = Point(hier_x, resolved_label_y)
    tap_point = Point(snap_to_grid(hier_x - HIER_STUB_LENGTH_MM), resolved_label_y)
    hierarchical_pin = HierarchicalPin(
        net_name=net_name,
        direction=direction,
        edge=edge,
        position_along_edge=position_along_edge_for_label_y(
            resolved_label_y,
            min_label_y,
        ),
        label_position=hier_point,
    )
    return hierarchical_pin, tap_point, hier_point


def build_hier_pins_from_rows(
    io_rows: tuple[IoAssignmentRow, ...],
    *,
    paper_width_mm: float,
    edge: SheetEdge = SheetEdge.RIGHT,
    align_y_to_pin: dict[str, float] | None = None,
) -> tuple[list[HierarchicalPin], list[Wire], dict[str, Point]]:
    """Build hierarchical pins sorted by geometry Y with unified edge positions."""
    wires: list[Wire] = []
    hierarchical_pins: list[HierarchicalPin] = []
    tap_points: dict[str, Point] = {}

    seen_signals: set[str] = set()
    unique_rows: list[IoAssignmentRow] = []
    for row in io_rows:
        if row.carrier_signal in seen_signals:
            continue
        seen_signals.add(row.carrier_signal)
        unique_rows.append(row)

    cursor_y = INTERIOR_MARGIN_MM + 12.7
    row_label_y: list[tuple[IoAssignmentRow, float]] = []
    for row in unique_rows:
        if align_y_to_pin and row.carrier_signal in align_y_to_pin:
            label_y = snap_to_grid(align_y_to_pin[row.carrier_signal])
        else:
            label_y = snap_to_grid(cursor_y)
            cursor_y += HIER_PIN_SPACING_MM
        row_label_y.append((row, label_y))

    row_label_y.sort(key=lambda item: item[1])
    min_label_y = min(label_y for _, label_y in row_label_y)

    for row, label_y in row_label_y:
        hierarchical_pin, tap_point, hier_point = hier_pin_layout(
            net_name=row.carrier_signal,
            direction=pin_direction_for_interface(row.interface),
            label_y=label_y,
            min_label_y=min_label_y,
            paper_width_mm=paper_width_mm,
            edge=edge,
        )
        tap_points[row.carrier_signal] = tap_point
        wires.extend(manhattan_wires(tap_point, hier_point))
        hierarchical_pins.append(hierarchical_pin)

    return hierarchical_pins, wires, tap_points


def connect_pin_to_tap(
    pin_point: Point,
    tap_point: Point,
    channel_x: float,
) -> list[Wire]:
    """Route pin to hier tap: direct horizontal when Y matches, else channel."""
    if abs(pin_point.y - tap_point.y) < KICAD_GRID_MM / 2:
        return list(route_horizontal(pin_point, tap_point.x))
    return list(route_channel(pin_point, channel_x, tap_point))
