from __future__ import annotations

import json
from pathlib import Path

import pytest

from schgen.core import native as nat
from schgen.core.link import all_subsystem_paths, exec_subsystem_py, load_subsystem
from schgen.core.model import CIRCUIT_SCHEMA, Circuit, CircuitError


_REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def geom():
    if not nat.loaded():
        pytest.skip("schgen._geom not built — run scripts/build_native.sh")
    return nat.module()


def test_circuit_ir_roundtrip_usbc_otg():
    py = exec_subsystem_py("usbc_otg").circuit
    ir = py.to_ir()
    assert ir["schema"] == CIRCUIT_SCHEMA
    assert ir["name"] == "usbc_otg"
    assert Circuit.from_ir(ir).to_ir() == ir


def test_circuit_ir_rejects_unknown_key():
    ir = exec_subsystem_py("usbc_otg").circuit.to_ir()
    ir["extra"] = "nope"
    with pytest.raises(CircuitError, match="unknown key"):
        Circuit.from_ir(ir)


def test_every_carrier_circuit_json_matches_python_exec():
    paths = all_subsystem_paths()
    assert len(paths) == 37
    for py_path in paths:
        py = exec_subsystem_py(str(py_path)).circuit
        json_path = py_path.parent / "circuit.json"
        if py_path.parent.name != py_path.stem:
            json_path = py_path.parent / py_path.stem / "circuit.json"
        payload = json.loads(json_path.read_text())
        assert Circuit.from_ir(payload).to_ir() == py.to_ir(), py_path.name


def test_circuit_catalog_matches_every_sheet(geom, tmp_path):
    from schgen.core import native as nat_mod

    circuits_root = _REPO / "carrier" / "subsystems"
    json_paths = sorted(circuits_root.glob("*/circuit.json"))
    assert len(json_paths) == 37
    catalog_bin = tmp_path / "circuits.bin"
    assert geom.circuit_compile(str(circuits_root), str(catalog_bin)) is True
    assert geom.circuit_open(str(catalog_bin)) is True
    assert geom.circuit_count() == 37
    for json_path in json_paths:
        payload = json.loads(json_path.read_text())
        rec = geom.circuit_lookup(payload["name"])
        assert Circuit.from_ir(rec).to_ir() == Circuit.from_ir(payload).to_ir()
        py = exec_subsystem_py(payload["name"]).circuit
        assert Circuit.from_ir(rec).to_ir() == py.to_ir()
    geom.circuit_close()
    nat_mod._CIRCUITS_OPEN = False


def test_load_subsystem_uses_circuit_catalog():
    py = exec_subsystem_py("usbc_otg").circuit
    loaded = load_subsystem("usbc_otg").circuit
    assert loaded.to_ir() == py.to_ir()
    assert loaded.parts["J2"].pin_numbers
    assert "+5V_USB" in loaded.nets or "+VBUS_SUPPLY" in loaded.nets


def test_circuit_catalog_rejects_unknown_name(geom, tmp_path):
    from schgen.core import native as nat_mod

    circuits_root = _REPO / "carrier" / "subsystems"
    catalog_bin = tmp_path / "circuits.bin"
    assert geom.circuit_compile(str(circuits_root), str(catalog_bin)) is True
    assert geom.circuit_open(str(catalog_bin)) is True
    with pytest.raises(RuntimeError, match="unknown circuit"):
        geom.circuit_lookup("not_a_sheet")
    geom.circuit_close()
    nat_mod._CIRCUITS_OPEN = False
