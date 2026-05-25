"""Root-sheet layout: functional grouping with pin-height sheet symbols."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid


SHEET_SYMBOL_MIN_WIDTH_MM = snap_to_grid(50.8)
SHEET_SYMBOL_MIN_HEIGHT_MM = snap_to_grid(40.64)
SHEET_PIN_SPACING_MM = snap_to_grid(2.54)
SHEET_HORIZONTAL_GAP_MM = snap_to_grid(63.5)
SHEET_VERTICAL_GAP_MM = snap_to_grid(25.4)
ROOT_ORIGIN_MM = snap_to_grid(25.4)
A1_WIDTH_MM = snap_to_grid(841.0)
A1_HEIGHT_MM = snap_to_grid(594.0)
A1_PAGE_MARGIN_MM = snap_to_grid(25.4)

# Functional columns on the root A1 sheet (left → right).
FUNCTIONAL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "SoM",
        ("som_j1", "som_j2", "som_j3"),
    ),
    (
        "Power / USB-PD",
        ("power", "power_mon", "usb_pd"),
    ),
    (
        "USB / UART",
        ("usbc_otg", "uart_bridge"),
    ),
    (
        "Video",
        ("hdmi_tx", "hdmi_rx", "lvds_lcd", "mipi_camera"),
    ),
    (
        "Network / Storage",
        ("ethernet", "microsd"),
    ),
    (
        "Expansion",
        ("fmc_lpc", "pmod"),
    ),
    (
        "Debug",
        ("jtag_swd", "boot_switches"),
    ),
    (
        "IO",
        ("aux_io", "xadc_clk"),
    ),
)


@dataclass(frozen=True)
class SheetPlacement:
    block_name: str
    origin: Point
    width_mm: float
    height_mm: float


def functional_block_order(blocks: dict[str, Block]) -> tuple[str, ...]:
    """Return block names in functional root-sheet order."""
    ordered: list[str] = []
    grouped: set[str] = set()
    for _group_name, block_names in FUNCTIONAL_GROUPS:
        for block_name in block_names:
            if block_name in blocks:
                ordered.append(block_name)
                grouped.add(block_name)
    for block_name in blocks:
        if block_name not in grouped:
            ordered.append(block_name)
    return tuple(ordered)


def sheet_symbol_size(block: Block) -> tuple[float, float]:
    pin_count = len(block.hierarchical_pins)
    if pin_count == 0:
        return SHEET_SYMBOL_MIN_WIDTH_MM, SHEET_SYMBOL_MIN_HEIGHT_MM

    label_positions = [
        hierarchical_pin.label_position
        for hierarchical_pin in block.hierarchical_pins
        if hierarchical_pin.label_position is not None
    ]
    if label_positions:
        min_label_y = min(label_point.y for label_point in label_positions)
        max_label_y = max(label_point.y for label_point in label_positions)
        label_height = max_label_y - min_label_y + snap_to_grid(25.4)
        return (
            SHEET_SYMBOL_MIN_WIDTH_MM,
            max(SHEET_SYMBOL_MIN_HEIGHT_MM, snap_to_grid(label_height)),
        )

    count_height = pin_count * SHEET_PIN_SPACING_MM + snap_to_grid(25.4)
    edge_height = snap_to_grid(25.4)
    if block.hierarchical_pins:
        edge_height = max(
            hierarchical_pin.position_along_edge
            for hierarchical_pin in block.hierarchical_pins
        ) + snap_to_grid(25.4)

    return (
        SHEET_SYMBOL_MIN_WIDTH_MM,
        max(SHEET_SYMBOL_MIN_HEIGHT_MM, snap_to_grid(max(count_height, edge_height))),
    )


def pack_sheet_placements(blocks: dict[str, Block]) -> tuple[SheetPlacement, ...]:
    """Place sheet symbols in functional columns; wrap when page bounds exceeded."""
    placements: list[SheetPlacement] = []
    max_x = A1_WIDTH_MM - A1_PAGE_MARGIN_MM
    max_y = A1_HEIGHT_MM - A1_PAGE_MARGIN_MM
    column_pitch = SHEET_SYMBOL_MIN_WIDTH_MM + SHEET_HORIZONTAL_GAP_MM
    row_origin_y = ROOT_ORIGIN_MM
    row_max_height = 0.0
    column_heights: list[float] = []

    def _start_new_row_band() -> None:
        nonlocal row_origin_y, row_max_height, column_heights
        row_origin_y = snap_to_grid(row_origin_y + row_max_height + SHEET_VERTICAL_GAP_MM)
        row_max_height = 0.0
        column_heights = []

    def _append_placement(
        block_name: str,
        block: Block,
        column_index: int,
    ) -> int:
        nonlocal row_max_height
        sheet_width, sheet_height = sheet_symbol_size(block)

        while True:
            x = ROOT_ORIGIN_MM + column_index * column_pitch
            if x + sheet_width > max_x:
                _start_new_row_band()
                column_index = 0
                continue

            while len(column_heights) <= column_index:
                column_heights.append(0.0)
            y = row_origin_y + column_heights[column_index]
            if y + sheet_height > max_y:
                column_index += 1
                continue

            origin = Point(snap_to_grid(x), snap_to_grid(y))
            placements.append(
                SheetPlacement(
                    block_name=block_name,
                    origin=origin,
                    width_mm=sheet_width,
                    height_mm=sheet_height,
                )
            )
            column_heights[column_index] += sheet_height + SHEET_VERTICAL_GAP_MM
            row_max_height = max(row_max_height, column_heights[column_index])
            return column_index

    for _group_name, block_names in FUNCTIONAL_GROUPS:
        column_index = len(column_heights)
        column_heights.append(0.0)
        for block_name in block_names:
            block = blocks.get(block_name)
            if block is None:
                continue
            column_index = _append_placement(block_name, block, column_index)

    placed = {placement.block_name for placement in placements}
    column_index = len(column_heights)
    column_heights.append(0.0)
    for block_name, block in blocks.items():
        if block_name in placed:
            continue
        _append_placement(block_name, block, column_index)

    return tuple(placements)
