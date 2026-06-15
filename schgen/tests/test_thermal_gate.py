"""Tests for the per-device JUNCTION-TEMPERATURE gate (schgen/verify/thermal.py).

Locks: the dissipation model per device kind; the CURRENT board passes (every
speced regulator under its Tj guard band, real device coverage); a synthetic
LDO dropping too much power runs OVER Tj and FAILS; and an author waive_thermal
demotes that ERROR to a note. Pure/offline (Tj = Ta + Pd*RthJA over the
powertree tree; no kicad-cli, no network)."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import powertree, thermal


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_dissipation_model():
    spec = thermal.ThermalSpec(rth_ja=250.0, tj_max=125.0, rds_on=0.1, eff=0.85)
    # LDO: (Vin - Vout) * Iout
    assert abs(thermal.dissipation("ldo", 5.0, 1.8, 0.3, spec) - 0.96) < 1e-9
    # buck: (1/eff - 1) * Vout * Iout
    assert abs(thermal.dissipation("buck", 20.0, 5.0, 1.0, spec)
               - (1 / 0.85 - 1) * 5.0 * 1.0) < 1e-9
    # load_switch / efuse: Iout^2 * Rds_on
    assert abs(thermal.dissipation("efuse", 5.0, 5.0, 2.0, spec)
               - 4.0 * 0.1) < 1e-9
    # an unknown kind dissipates nothing in the model
    assert thermal.dissipation("mystery", 5.0, 1.8, 1.0, spec) == 0.0


def test_current_board_passes_thermal():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = thermal.analyze(sheets)
    assert r.ok, f"unexpected over-Tj devices: {r.errors}"
    assert not r.findings, f"unspeced devices: {r.findings}"
    assert len(r.devices) > 10        # real device coverage, not a no-op


def _hot_ldo_sheet():
    # an AP2112K (RthJA 250 C/W, Tj_max 125 C) dropping 5.0 -> 1.8 V at 0.3 A
    # (well inside its 0.6 A current limit) dissipates 0.96 W -> Tj = 50 +
    # 0.96*250 = 290 C, far over the 115 C guard (Tj_max 125 - 10 C margin).
    c = Circuit("th", "th")
    c.part("U1", "Fake:LDO", "AP2112K-1.8", "")
    c.net("+5V_REG", "U1.1")
    c.net("+1V8", "U1.5")
    c.draws("+1V8", 0.3, "synthetic hot LDO")
    return c


def test_over_tj_fails():
    c = _hot_ldo_sheet()
    pt = powertree.analyze([_sheet("th", c)])
    assert pt.ok, f"powertree itself must pass (0.3 A < 0.6 A): {pt.errors}"
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    assert not r.ok, "Tj 290 C must FAIL the guard band"
    assert any("OVER Tj" in e and "U1" in e for e in r.errors), r.errors
    dev = next(d for d in r.devices if d.ref == "U1")
    assert dev.over and dev.margin < 0.0


def test_thermal_waiver_demotes_to_note():
    c = _hot_ldo_sheet()
    c.waive_thermal("U1", "bench-validated copper pour + thermal vias")
    pt = powertree.analyze([_sheet("th", c)])
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    assert r.ok, "an author thermal waiver must clear the hard ERROR"
    assert any("WAIVED over-limit" in n and "U1" in n for n in r.notes), r.notes
    assert "th:U1" in r.waived
