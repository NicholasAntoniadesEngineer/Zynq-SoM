from __future__ import annotations

import json

from schgen.verify import carrier_structure as gate


def test_real_carrier_structure_accepts_equivalent_ir_companions():
    result = gate.check()
    assert result.ok, result.summary()


def test_adapter_companion_rejects_netlist_drift_and_extra_code(tmp_path):
    name = "usbc_otg"
    for filename in gate.required_files(name, adapter=True):
        (tmp_path / filename).write_text(
            (gate.CARRIER_SUBSYSTEMS_DIR / filename).read_text())
    companion = tmp_path / name
    companion.mkdir()
    payload = json.loads(
        (gate.CARRIER_SUBSYSTEMS_DIR / name / "circuit.json").read_text())
    target = companion / "circuit.json"
    target.write_text(json.dumps(payload))
    assert gate.check_package(name, tmp_path).ok
    payload["title"] += " changed"
    target.write_text(json.dumps(payload))
    assert "circuit.json differs" in " ".join(gate.check_package(name, tmp_path).errors)
    (companion / "hidden.py").write_text("pass\n")
    assert gate.check_package(name, tmp_path).missing
