"""Tests for the RAIL-AMPACITY gate (schgen/verify/rail_ampacity.py).

Two layers, in the ``test_pcb_gate_mutation``/``test_thermal_gate`` discipline:

1. UNIT — a hand-built (sheets, interface) fixture PASSES with an adequate
   contact count, then the SAME rail with too FEW contacts (or too much current)
   FAILS — the seeded-defect kill that proves the gate BITES (a gate that never
   fires proves nothing).
2. INTEGRATION — the REAL carrier sheets + som_interface.json run, the gate is
   well-formed, and the real board's healthy +5V_SOM margin is asserted (the
   red-on-before note: this rail is the one the critique flagged as the tightest,
   and it must PASS at the datasheet 0.3 A/contact + 20% derate).

The unit fixtures use tiny fake circuits/interfaces so no repo data is needed and
the arithmetic is exact and legible.
"""

from __future__ import annotations

import json
from pathlib import Path

from schgen.verify import powertree
from schgen.verify import rail_ampacity as g


# ---------------------------------------------------------------------------
# fixtures: a minimal sheet exposing ``circuit.loads`` + a tiny interface JSON
# ---------------------------------------------------------------------------
class _FakeCircuit:
    """Just enough of Circuit for the gate: a name + a ``loads`` dict."""

    def __init__(self, name: str, loads: dict):
        self.name = name
        self.loads = loads


class _FakeSheet:
    def __init__(self, name: str, loads: dict):
        self.name = name
        self.circuit = _FakeCircuit(name, loads)


def _interface(pins_by_conn: dict[str, dict[str, str]]) -> dict:
    """{ref: {pad: net}} -> a som_interface.json-shaped dict."""
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
    """analyze() with the powertree-draw path fed by the fake sheets' loads and
    the linker maps forced to identity (so a bare rail name resolves to itself
    and is POWER-classified by Circuit.classify)."""
    # resolve_net = identity, no isolated rails: the fake nets ARE carrier rails.
    monkeypatch.setattr(g, "_link_maps", lambda: (lambda n: n, {}))
    # a fresh (empty) powertree Result — the gate reads current from the SHEET
    # loads, not from pt_res, so an empty Result is fine and avoids repo data.
    return g.analyze(sheets, pt_res=powertree.Result(),
                     interface_json=iface_path)


# ---------------------------------------------------------------------------
# (1) adequate contacts -> PASS
# ---------------------------------------------------------------------------
def test_adequate_contacts_pass(tmp_path, monkeypatch):
    # +5V rail: 1.0 A across 5 contacts -> cap = 5*0.3*0.8 = 1.2 A -> ok.
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


# ---------------------------------------------------------------------------
# (2) too FEW contacts -> FAIL (the seeded-defect KILL — proves the gate bites)
# ---------------------------------------------------------------------------
def test_too_few_contacts_fails(tmp_path, monkeypatch):
    # Same 1.0 A rail but only 2 contacts -> cap = 2*0.3*0.8 = 0.48 A < 1.0 A.
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


# ---------------------------------------------------------------------------
# (3) mutation-style: the PASSING fixture, current bumped past capacity, flips
# ---------------------------------------------------------------------------
def test_mutation_current_over_capacity_flips(tmp_path, monkeypatch):
    iface = _interface({"J1": {str(i): "+5V" for i in range(1, 6)}})  # 5 -> 1.2 A
    passing = [_FakeSheet("som_j1", {"+5V": [(1.0, "load")]})]
    assert _run(passing, _write(tmp_path, iface), monkeypatch).ok is True
    # MUTANT: same 5 contacts, current raised to 1.5 A > 1.2 A cap.
    mutant = [_FakeSheet("som_j1", {"+5V": [(1.5, "heavier load")]})]
    mres = _run(mutant, _write(tmp_path, iface), monkeypatch)
    assert mres.ok is False
    assert mres.rails[0].over


# ---------------------------------------------------------------------------
# (4) a delivery rail with contacts but no declared draw -> finding, still ok
# ---------------------------------------------------------------------------
def test_unbooked_rail_is_a_finding_not_an_error(tmp_path, monkeypatch):
    iface = _interface({"J1": {"1": "+5V", "2": "+5V"}})
    sheets = [_FakeSheet("som_j1", {})]           # no draw declared
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert res.ok is True
    assert len(res.findings) == 1
    assert "unbooked" in res.findings[0]
    assert abs(res.rails[0].current_a) < 1e-9


# ---------------------------------------------------------------------------
# (5) only som_j* sheet draws are counted (a carrier-side draw is ignored)
# ---------------------------------------------------------------------------
def test_only_connector_sheet_draws_cross_the_df40(tmp_path, monkeypatch):
    iface = _interface({"J1": {"1": "+3V3", "2": "+3V3"}})   # cap = 0.48 A
    sheets = [
        _FakeSheet("som_j1", {"+3V3": [(0.1, "VCCO tap through the DF40")]}),
        # a carrier-side consumer NOT on a som_j* sheet — must NOT be counted
        _FakeSheet("power", {"+3V3": [(5.0, "carrier-local load")]}),
    ]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert res.ok is True                         # only the 0.1 A crosses the DF40
    assert abs(res.rails[0].current_a - 0.1) < 1e-9


# ---------------------------------------------------------------------------
# non-power nets never become rails
# ---------------------------------------------------------------------------
def test_signal_and_gnd_nets_are_not_delivery_rails(tmp_path, monkeypatch):
    iface = _interface({"J1": {
        "1": "+5V", "2": "+5V",
        "3": "GND", "4": "SOME_SIGNAL_P", "5": "SOME_SIGNAL_N"}})
    sheets = [_FakeSheet("som_j1", {"+5V": [(0.2, "load")]})]
    res = _run(sheets, _write(tmp_path, iface), monkeypatch)
    assert {r.name for r in res.rails} == {"+5V"}   # GND / signals excluded


# ---------------------------------------------------------------------------
# constants are the cited/derating values (a silent edit alarms)
# ---------------------------------------------------------------------------
def test_rating_constants_are_the_cited_values():
    assert g.PER_CONTACT_A == 0.3            # Hirose DF40 rated current, CITED
    assert g.DERATING == 0.8                 # 20% power-derating margin
    assert "0.3 A/contact" in g.PER_CONTACT_BASIS
    assert "Hirose DF40" in g.PER_CONTACT_BASIS


# ---------------------------------------------------------------------------
# INTEGRATION: the real carrier. Well-formed + the flagged +5V_SOM is healthy.
# ---------------------------------------------------------------------------
def _real_sheets():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def test_real_board_runs_and_is_wellformed():
    res = g.analyze(_real_sheets())
    assert isinstance(res.ok, bool)
    names = {r.name for r in res.rails}
    # the SoM's four DF40-delivered POWER rails (VIN rebind + VCCO ties)
    assert "+5V_SOM" in names
    assert "+3V3" in names
    assert "+2V5_VADJ" in names
    for r in res.rails:
        assert r.contacts >= 1
        assert r.capacity_a > 0


def test_real_board_5v_som_is_the_tight_rail_and_passes():
    """+5V_SOM is the rail the completeness critique flagged as tightest
    (2.15 A across 14 contacts). At the datasheet 0.3 A/contact + 20% derate it
    PASSES with real margin — the correct (green) result the task predicted, and
    the rail whose numbers this gate must reproduce exactly."""
    res = g.analyze(_real_sheets())
    som = next(r for r in res.rails if r.name == "+5V_SOM")
    assert som.contacts == 14                       # J1.1-14, the VIN rebind
    assert abs(som.current_a - 2.15) < 1e-3         # SoM 10 W @ 4.65 V estimate
    assert not som.over                             # healthy at 0.3 A x 0.8
    assert som.util < 0.8                           # real guard band remains


def test_real_board_gate_passes():
    """The whole real board is ampacity-adequate today (no rail under-contacted)
    — so wiring this gate HARD into `schgen board` keeps BOARD green."""
    res = g.analyze(_real_sheets())
    assert res.ok is True, report_on_fail(res)


def report_on_fail(res) -> str:
    return "\n" + g.report(res)


def test_real_board_determinism():
    a = g.report(g.analyze(_real_sheets()))
    b = g.report(g.analyze(_real_sheets()))
    assert a == b
