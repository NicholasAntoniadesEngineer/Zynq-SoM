"""Per-IC canonical validation tests."""

from __future__ import annotations

import pytest

from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.validate.canonical import run_canonical_validation
from scripts.carrier.validate.canonical.registry import CANONICAL_VALIDATORS


@pytest.mark.parametrize("circuit_name", sorted(REFCIRCUITS.keys()))
def test_refcircuit_has_verified_metadata(circuit_name: str) -> None:
    ref_circuit = REFCIRCUITS[circuit_name]
    assert ref_circuit.minimum_circuit_verified
    assert ref_circuit.local_datasheet_path
    assert ref_circuit.app_circuit_page


@pytest.mark.parametrize("circuit_name", sorted(REFCIRCUITS.keys()))
def test_every_refcircuit_has_canonical_validator(circuit_name: str) -> None:
    assert circuit_name in CANONICAL_VALIDATORS


def test_canonical_validation_passes() -> None:
    errors = [
        result
        for result in run_canonical_validation()
        if result.severity == "error"
    ]
    assert errors == []
