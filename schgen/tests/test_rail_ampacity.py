from __future__ import annotations

import json
from pathlib import Path

from schgen.verify import powertree
from schgen.verify import rail_ampacity as g


class _FakeCircuit:
    def __init__(self, name: str, loads: dict):
        self.name = name
        self.loads = loads


class _FakeSheet:
    def __init__(self, name: str, loads: dict):
        self.name = name
        self.circuit = _FakeCircuit(name, loads)


def _interface(pins_by_conn: dict[str, dict[str, str]]) -> dict:
    return {"connectors": {
        ref: {"value": "DF40C-100DS-0.4V_51",
              "footprint": "Mylibrary:HRS_DF40C-100DP-0.4V_51_",
              "pins": pins}
        for ref, pins in pins_by_conn.items()}}


def _write(tmp_path: Path, iface: dict) -> Path:
    p = tmp_path / "iface.json"
    p.write_text(json.dumps(iface))
    return p


def _run(sheets, iface_path, monkeypatch):
    monkeypatch.setattr(g, "_link_maps", lambda: (lambda n: n, {}))
    return g.analyze(sheets, pt_res=powertree.Result(),
                     interface_json=iface_path)


def test_adequate_contacts_pass(tmp_path, monkeypatch):
    iface = _interface({"J1": {str(i): "+5V" for i in range(1, 6)}})
    sheets = [_FakeSheet("som_j1", {"+5V": [(1.0, "load")]})]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert res.ok is True
    assert len(res.rails) == 1
    r = res.rails[0]
    assert r.name == "+5V"
    assert r.contacts == 5
    assert abs(r.current_a - 1.0) < 1e-9
    assert abs(r.capacity_a - 1.2) < 1e-9
    assert not r.over


def test_too_few_contacts_fails(tmp_path, monkeypatch):
    iface = _interface({"J1": {"1": "+5V", "2": "+5V"}})
    sheets = [_FakeSheet("som_j1", {"+5V": [(1.0, "load")]})]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert res.ok is False
    r = res.rails[0]
    assert r.contacts == 2
    assert r.over
    assert abs(r.capacity_a - 0.48) < 1e-9
    assert r.margin_a < 0
    assert len(res.errors) == 1
    assert "UNDER-CONTACTED" in res.errors[0]
    assert "+5V" in res.errors[0]


def test_mutation_current_over_capacity_flips(tmp_path, monkeypatch):
    iface = _interface({"J1": {str(i): "+5V" for i in range(1, 6)}})
    passing = [_FakeSheet("som_j1", {"+5V": [(1.0, "load")]})]
    assert _run(passing, _write(tmp_path, iface), monkeypatch).ok is True
    mutant = [_FakeSheet("som_j1", {"+5V": [(1.5, "heavier load")]})]
    mres = _run(mutant, _write(tmp_path, iface), monkeypatch)
    assert mres.ok is False
    assert mres.rails[0].over


def test_unbooked_rail_is_a_finding_not_an_error(tmp_path, monkeypatch):
    iface = _interface({"J1": {"1": "+5V", "2": "+5V"}})
    sheets = [_FakeSheet("som_j1", {})]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert res.ok is True
    assert len(res.findings) == 1
    assert "unbooked" in res.findings[0]
    assert abs(res.rails[0].current_a) < 1e-9


def test_only_connector_sheet_draws_cross_the_df40(tmp_path, monkeypatch):
    iface = _interface({"J1": {"1": "+3V3", "2": "+3V3"}})
    sheets = [
        _FakeSheet("som_j1", {"+3V3": [(0.1, "VCCO tap through the DF40")]}),
        _FakeSheet("power", {"+3V3": [(5.0, "carrier-local load")]}),
    ]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert res.ok is True
    assert abs(res.rails[0].current_a - 0.1) < 1e-9


def test_signal_and_gnd_nets_are_not_delivery_rails(tmp_path, monkeypatch):
    iface = _interface({"J1": {
        "1": "+5V", "2": "+5V",
        "3": "GND", "4": "SOME_SIGNAL_P", "5": "SOME_SIGNAL_N"}})
    sheets = [_FakeSheet("som_j1", {"+5V": [(0.2, "load")]})]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert {r.name for r in res.rails} == {"+5V"}


def test_rating_constants_are_the_cited_values():
    assert g.PER_CONTACT_A == 0.3
    assert g.DERATING == 0.8
    assert "0.3 A/contact" in g.PER_CONTACT_BASIS
    assert "Hirose DF40" in g.PER_CONTACT_BASIS


def _real_sheets():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def test_real_board_runs_and_is_wellformed():
    res = g.analyze(_real_sheets())
    assert isinstance(res.ok, bool)
    names = {r.name for r in res.rails}
    assert "+5V_SOM" in names
    assert "+3V3" in names
    assert "+2V5_VADJ" in names
    for r in res.rails:
        assert r.contacts >= 1
        assert r.capacity_a > 0


def test_real_board_5v_som_is_the_tight_rail_and_passes():
    res = g.analyze(_real_sheets())
    som = next(r for r in res.rails if r.name == "+5V_SOM")
    assert som.contacts == 14
    assert abs(som.current_a - 2.15) < 1e-3
    assert not som.over
    assert som.util < 0.8


def test_real_board_has_no_under_contacted_rail():
    res = g.analyze(_real_sheets())
    assert res.ok is True, report_on_fail(res)


def report_on_fail(res) -> str:
    return "\n" + g.report(res)


def test_real_board_determinism():
    a = g.report(g.analyze(_real_sheets()))
    b = g.report(g.analyze(_real_sheets()))
    assert a == b
