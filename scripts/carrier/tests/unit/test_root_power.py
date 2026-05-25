"""Root sheet power distribution tests."""

from __future__ import annotations

import re

from scripts.carrier.blocks import all_block_factories
from scripts.carrier.model.nets import is_power_rail
from scripts.carrier.sheets.layout import (
    A1_HEIGHT_MM,
    A1_PAGE_MARGIN_MM,
    A1_WIDTH_MM,
    pack_sheet_placements,
)
from scripts.carrier.sheets.root import emit_hierarchical_project


def test_root_schematic_has_power_symbols(tmp_path) -> None:
    built_blocks = {
        name: factory()
        for name, factory in all_block_factories().items()
    }
    result = emit_hierarchical_project(
        blocks=built_blocks,
        output_dir=tmp_path,
    )
    root_text = result.root_schematic_path.read_text(encoding="utf-8")
    assert "power:GND" in root_text
    assert "power:+3V3" in root_text or "power:+5V" in root_text
    assert root_text.count("#PWR") >= 2


def test_root_sheet_stitches_power_nets_only(tmp_path) -> None:
    built_blocks = {
        name: factory()
        for name, factory in all_block_factories().items()
    }
    result = emit_hierarchical_project(
        blocks=built_blocks,
        output_dir=tmp_path,
    )
    root_text = result.root_schematic_path.read_text(encoding="utf-8")
    wire_count = root_text.count("(wire")
    assert wire_count < 80, f"root wire count {wire_count} suggests signal net stitching"

    label_names = re.findall(r'\(label\s+"([^"]+)"', root_text)
    signal_labels = [
        name for name in label_names if not is_power_rail(name)
    ]
    assert not signal_labels, (
        "root sheet must not place global labels on signal nets: "
        + ", ".join(sorted(set(signal_labels))[:10])
    )


def test_root_sheet_placements_fit_a1_page() -> None:
    built_blocks = {
        name: factory()
        for name, factory in all_block_factories().items()
    }
    max_y = A1_HEIGHT_MM - A1_PAGE_MARGIN_MM
    max_x = A1_WIDTH_MM - A1_PAGE_MARGIN_MM
    for placement in pack_sheet_placements(built_blocks):
        bottom_edge = placement.origin.y + placement.height_mm
        right_edge = placement.origin.x + placement.width_mm
        assert bottom_edge <= max_y + 0.01, (
            f"{placement.block_name} bottom y={bottom_edge} exceeds page max {max_y}"
        )
        assert right_edge <= max_x + 0.01, (
            f"{placement.block_name} right x={right_edge} exceeds page max {max_x}"
        )

