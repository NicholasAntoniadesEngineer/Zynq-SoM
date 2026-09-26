"""Transport regressions: live inputs, immutable independent expectations."""
from __future__ import annotations

import copy
import importlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from schgen.core import authoring
from schgen.core.model import Circuit, CircuitError
from schgen.core.subsystem import Meta
from schgen.verify import copper_debt, thermal
from subsystems import basis, basis_census

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "native/tests/data/authoring"
AUDIT_FIXTURES = ROOT / "native/tests/data/component_basis"
LIBRARIES = {
    path.stem: json.loads(path.read_text())
    for path in sorted(FIXTURES.glob("*.json"))
    if not path.stem.startswith(("gate_", "connector_"))
}
LIBRARY_CASES = [
    pytest.param(name, row, id=f"{name}-{i}")
    for name, fixture in LIBRARIES.items()
    for i, row in enumerate(fixture["cases"])
]
PROJECT_CASES = [
    pytest.param(project, row, id=f"{project}-{row['name']}")
    for project in ("carrier", "devkit_mini")
    for row in json.loads((FIXTURES / f"gate_{project}.json").read_text())["packages"]
]
CONNECTOR_CASES = [
    pytest.param(project, row, id=f"{project}-{i}")
    for project in ("carrier", "devkit_mini")
    for i, row in enumerate(json.loads(
        (FIXTURES / f"connector_{project}.json").read_text())["cases"])
]


@pytest.fixture
def live():
    return authoring.audit_inputs()


def _forbidden(*args, **kwargs):
    raise AssertionError("native audit attempted a Python source fallback")


@pytest.mark.parametrize("name,row", LIBRARY_CASES)
@pytest.mark.parametrize("as_meta", (False, True), ids=("dict", "Meta"))
def test_parameterized_library_adapters_preserve_original_python(name, row, as_meta):
    module = importlib.import_module(f"subsystems.{name}.{name}")
    meta = Meta(row["meta"]) if as_meta else row["meta"]
    assert not hasattr(module, "_legacy_circuit")
    assert module.INTERFACE == tuple(LIBRARIES[name]["interface"])
    if "error" in row:
        with pytest.raises(CircuitError) as exc:
            module.circuit(meta)
        assert str(exc.value) == row["error"]
    else:
        assert module.circuit(meta).to_ir() == row["circuit"]


@pytest.mark.parametrize("project,row", PROJECT_CASES)
def test_all_project_adapters_preserve_original_python(project, row):
    name = row["name"]
    suffix = name if row["adapter"] else f"{name}.{name}"
    module = importlib.import_module(f"{project}.subsystems.{suffix}")
    assert not hasattr(module, "_legacy_circuit")
    assert module.circuit().to_ir() == row["circuit"]


def test_no_inactive_connector_or_helper_implementations_remain():
    for project in ("carrier", "devkit_mini"):
        module = importlib.import_module(f"{project}.som_conn_gen")
        assert not hasattr(module, "_legacy_connector_circuit")
    assert not hasattr(Circuit, "_legacy_bind")
    assert not hasattr(Circuit, "_legacy_mounting_hole")


@pytest.mark.parametrize("project,row", CONNECTOR_CASES)
def test_connector_adapters_preserve_live_parameters(project, row, monkeypatch):
    module = importlib.import_module(f"{project}.som_conn_gen")
    pins = module.contract_pins(row["ref"])
    pins.update(row.get("pin_edits", {}))
    monkeypatch.setattr(module, "contract_pins", lambda ref: pins)
    monkeypatch.setattr(module, "FUNCTION_MAP",
                        {**module.FUNCTION_MAP, **row.get("map_edit", {})})
    for source, target in (("module_draw_a", "MODULE_DRAW_A"),
                           ("sdio_level_v", "SDIO_LEVEL_V")):
        if source in row:
            monkeypatch.setattr(module, target, row[source])
    if "error" in row:
        with pytest.raises(CircuitError) as exc:
            module.connector_circuit(row["ref"], "dynamic", "dynamic fixture")
        assert str(exc.value) == row["error"]
    else:
        assert module.connector_circuit(
            row["ref"], "dynamic", "dynamic fixture").to_ir() == row["circuit"]


def test_default_basis_audit_never_uses_source_scanner(monkeypatch):
    monkeypatch.setattr(basis_census, "check_python_sources", _forbidden)
    result = basis_census.check()
    assert result.ok, result.summary()
    assert result.native
    assert (result.n_registered, result.n_files, result.n_consumers,
            result.n_sites) == (214, 17, 49, 685)


def test_basis_audit_sees_live_component_edits(live):
    camera = next(row["circuit"] for row in live
                  if row["scope"] == "library" and row["sheet"] == "camera")
    next(p for p in camera["parts"] if p["ref"] == "R1")["value"] = "999k"
    result = basis_census.check_native(live)
    assert not result.ok
    assert any("camera:R1.value" in x and "999k" in x for x in result.broken)


def test_basis_audit_sees_new_unregistered_components(live):
    camera = next(row["circuit"] for row in live
                  if row["scope"] == "library" and row["sheet"] == "camera")
    part = copy.deepcopy(next(p for p in camera["parts"] if p["ref"] == "R1"))
    part["ref"] = "R999"
    camera["parts"].append(part)
    result = basis_census.check_native(live)
    assert not result.ok
    assert any("R999" in x for x in result.raw)


def test_basis_audit_sees_public_constant_drift(monkeypatch):
    monkeypatch.setattr(basis, "CAMERA_LANE_TERM", "999k")
    result = basis_census.check()
    assert not result.ok
    assert any("CAMERA_LANE_TERM: public constant" in x for x in result.broken)


@pytest.mark.parametrize("field,value", [
    ("value", "999k"), ("unit", "furlong"), ("basis", " "), ("klass", "vibes"),
])
def test_basis_audit_checks_live_registration_fields(monkeypatch, field, value):
    entry = basis.REGISTRY["CAMERA_LANE_TERM"]
    monkeypatch.setitem(basis.REGISTRY, entry.name, replace(entry, **{field: value}))
    assert not basis_census.check().ok


def test_basis_audit_rejects_removed_registration(monkeypatch):
    monkeypatch.delitem(basis.REGISTRY, "CAMERA_LANE_TERM")
    result = basis_census.check()
    assert not result.ok
    assert any("CAMERA_LANE_TERM" in x for x in result.undeclared)


def test_basis_audit_rejects_dead_registration(monkeypatch):
    entry = replace(basis.REGISTRY["CAMERA_LANE_TERM"], name="UNUSED_AUDIT_VALUE")
    monkeypatch.setitem(basis.REGISTRY, entry.name, entry)
    monkeypatch.setattr(basis, entry.name, entry.value, raising=False)
    result = basis_census.check()
    assert not result.ok
    assert any(entry.name in x for x in result.unused)


@pytest.mark.parametrize("project", ("carrier", "devkit_mini"))
def test_audit_input_transport_replaces_complete_project_scope(project):
    rows = authoring.audit_inputs([], project=project)
    assert not any(row["scope"] == project for row in rows)
    result = basis_census.check_native(rows)
    assert not result.ok
    assert any(project + "/" in x and "missing live sheet" in x
               for x in result.broken)


@pytest.mark.parametrize("name", ("unmeasured", "carrier", "devkit_mini"))
def test_copper_adapter_matches_independent_report_fields(name, monkeypatch):
    monkeypatch.setattr(copper_debt, "_where", _forbidden)
    captures = json.loads((AUDIT_FIXTURES / "python_copper.json").read_text())
    expected = next(row["result"] for row in captures if row["name"] == name)
    pcb = None if name == "unmeasured" else (
        ROOT / "native/tests/data/pcb_emit" / f"{name}.kicad_pcb")
    result = copper_debt.analyze(pcb)
    assert result.inventory == expected["inventory"]
    for got, want in zip(result.entries, expected["entries"], strict=True):
        raw = asdict(got)
        del raw["where"]
        assert raw == {k: v for k, v in want.items() if k != "where"}
        assert all(p.startswith("native/src/copper_debt.cpp:") for p in got.where)
    assert copper_debt.report(result) == authoring._engine().copper_debt_report(
        asdict(result))


def test_copper_adapter_supplies_live_thermal_policy(monkeypatch):
    spec = thermal.THERMAL_SPECS["LM61460"]
    monkeypatch.setitem(thermal.THERMAL_SPECS, "LM61460", replace(spec, rth_ja=1))
    with pytest.raises(RuntimeError, match="CD-01"):
        copper_debt.analyze(None)


def test_copper_adapter_supplies_live_isolation_policy(monkeypatch):
    from schgen.generate.pcb import constants
    monkeypatch.setattr(constants, "ISO_VOID_VALUES", ())
    with pytest.raises(RuntimeError, match="CD-06"):
        copper_debt.analyze(None)


def test_copper_adapter_sees_actual_netlisted_connections(live):
    sheets = [SimpleNamespace(name=row["sheet"],
                              circuit=Circuit.from_ir(row["circuit"]))
              for row in live if row["scope"] == "carrier"]
    assert copper_debt.analyze(None, sheets=sheets, project="carrier").n_entries == 8
    eth = next(s.circuit for s in sheets if s.name == "ethernet")
    eth.nets["BS_COMMON"].pins.pop()
    with pytest.raises(RuntimeError, match="CD-05"):
        copper_debt.analyze(None, sheets=sheets, project="carrier")


def test_copper_adapter_does_not_fill_in_omitted_project_sheets():
    with pytest.raises(RuntimeError, match="missing live sheet"):
        copper_debt.analyze(None, sheets=[], project="carrier")
