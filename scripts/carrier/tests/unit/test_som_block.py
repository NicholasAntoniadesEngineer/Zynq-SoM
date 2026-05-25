"""Unit tests for SoM connector blocks (J1 / J2 / J3)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.carrier.blocks._block_common import IO_ASSIGNMENT_PATH
from scripts.carrier.blocks import som_connector
from scripts.carrier.registry import bom_io


SCRIPTS_DIR = Path(__file__).resolve().parents[3]
CARRIER_TEMPLATE_DIR = SCRIPTS_DIR / "carrier_template"


@pytest.fixture(scope="module", autouse=True)
def ensure_io_assignment() -> None:
    bom_io.emit_io_assignment_csv(CARRIER_TEMPLATE_DIR / "io_assignment.csv")


def _signals_for_connector(connector_name: str) -> set[str]:
    with open(IO_ASSIGNMENT_PATH, encoding="utf-8") as csv_file:
        return {
            row["carrier_signal"]
            for row in csv.DictReader(csv_file)
            if row["som_connector"] == connector_name and row["carrier_signal"]
        }


@pytest.mark.parametrize(
    ("builder", "connector_name"),
    [
        (som_connector.build_j1, "J1"),
        (som_connector.build_j2, "J2"),
        (som_connector.build_j3, "J3"),
    ],
)
def test_som_block_emits_one_connector(builder, connector_name: str) -> None:
    block = builder()
    references = {component.reference for component in block.components}
    assert references == {connector_name}


@pytest.mark.parametrize(
    ("builder", "connector_name"),
    [
        (som_connector.build_j1, "J1"),
        (som_connector.build_j2, "J2"),
        (som_connector.build_j3, "J3"),
    ],
)
def test_som_hierarchical_pin_count_matches_connector_signals(
    builder,
    connector_name: str,
) -> None:
    block = builder()
    expected_count = len(_signals_for_connector(connector_name))
    assert len(block.hierarchical_pins) == expected_count


@pytest.mark.parametrize("builder", [som_connector.build_j1, som_connector.build_j2, som_connector.build_j3])
def test_som_block_has_wires(builder) -> None:
    block = builder()
    assert len(block.wires) > 0


@pytest.mark.parametrize("builder", [som_connector.build_j1, som_connector.build_j2, som_connector.build_j3])
def test_som_hierarchical_pin_names_unique(builder) -> None:
    block = builder()
    net_names = [pin.net_name for pin in block.hierarchical_pins]
    assert len(net_names) == len(set(net_names))
