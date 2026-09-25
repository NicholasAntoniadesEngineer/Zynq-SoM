from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

_ENABLED = os.environ.get("SCHGEN_BOARD_TESTS") == "1"


def test_native_emission_respects_current_thermal_evidence_policy(
        carrier_model, tmp_path, monkeypatch, capsys):
    from schgen.generate.pcb.emit import emit_pcb
    from schgen.verify import thermal

    baseline = tmp_path / "baseline.kicad_pcb"
    emit_pcb(carrier_model, baseline)
    capsys.readouterr()
    monkeypatch.setattr(thermal, "POUR_EVIDENCE", {
        "strict": thermal.PourNeed(value_prefix="LM61460", min_vias=1000,
                                   radius_mm=10.0, pour_layers=("F.Cu", "B.Cu"))})
    changed = tmp_path / "changed.kicad_pcb"
    emit_pcb(carrier_model, changed)
    report = capsys.readouterr().out
    assert "THERMAL VIA SHORTFALL" in report
    assert "/1000 GND vias" in report
    assert changed.read_bytes() == baseline.read_bytes()


@pytest.mark.skipif(not _ENABLED,
                    reason="slow end-to-end build; set SCHGEN_BOARD_TESTS=1 "
                           "(mandatory at every T1 phase gate)")
def test_board_build_twice_is_byte_identical(tmp_path: Path):
    from schgen.generate.pcb.emit import emit_pcb
    from schgen.generate.pcb.placement import build_model

    hashes: list[str] = []
    sizes: list[tuple[float, float]] = []
    for i in (1, 2):
        model = build_model()
        out = tmp_path / f"board_{i}.kicad_pcb"
        emit_pcb(model, out)
        hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
        sizes.append((model.board_w, model.board_h))

    assert sizes[0] == sizes[1], (
        f"board size nondeterministic: {sizes[0]} vs {sizes[1]} "
        f"(the fp.BOARD_W/H race class)")
    assert hashes[0] == hashes[1], (
        "emitted .kicad_pcb bytes differ between two in-process builds — "
        "the placement chain is nondeterministic")
