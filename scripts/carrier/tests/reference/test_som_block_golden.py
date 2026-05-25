"""Golden-file regression test for SoM sub-sheets."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

import pytest

from scripts.carrier.blocks.som_connector import build_j1
from scripts.carrier.emit.kicad_sch import emit_block
from scripts.carrier.registry import bom_io


SCRIPTS_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def ensure_io_assignment() -> None:
    bom_io.emit_io_assignment_csv(
        SCRIPTS_DIR / "carrier_template" / "io_assignment.csv"
    )


def _normalise_schematic_text(text: str) -> str:
    without_uuids = re.sub(
        r'\(uuid "[0-9a-f-]+"\)',
        '(uuid "NORMALISED")',
        text,
    )
    return without_uuids


def test_som_j1_emits_schematic() -> None:
    block = build_j1()
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "som_j1.kicad_sch"
        stats = emit_block(
            block=block,
            output_path=output_path,
            parent_uuid=str(uuid.uuid4()),
            sheet_uuid=str(uuid.uuid4()),
        )
        assert stats.placed_symbol_count == 1
        assert stats.wire_count > 0
        assert stats.hierarchical_label_count == len(block.hierarchical_pins)

        emitted_text = _normalise_schematic_text(output_path.read_text(encoding="utf-8"))
        assert "(symbol" in emitted_text
        assert "Zynq_SoM_J1" in emitted_text
        assert "hierarchical_label" in emitted_text
