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


def test_tps54302_spec_matches_datasheet():
    """LAW-4 honesty lock: the TPS54302 row carries the DATASHEET RthJA + the
    RECOMMENDED Tj-max, not a fabricated value or the abs-max. TI SLVSDG6C 5.4
    (RthJA 118.9 C/W JESD51-7) + 5.3 (Tj rec-op-max 125 C). No EP -> no pour
    credit (rth_eff == bare). Regression-locks the 2026-06-16 re-base so nobody
    can quietly restore the masking 70.6 C/W / 150 C guard."""
    spec = thermal.THERMAL_SPECS["TPS54302"]
    assert spec.rth_ja == 118.9, "must be the DS JESD51-7 RthJA, not 70.6"
    assert spec.tj_max == 125.0, "must be the rec-op Tj-max, not the 150 abs-max"
    assert spec.rth_ja_pour is None, "no-EP SOT-23 has no pad to pour"
    assert spec.rth_eff == 118.9, "no pour credit -> Tj judged at bare RthJA"


def _tps54302_buck_sheet(iout, vout_rail="+3V3", vin_rail="+5V"):
    """A TPS54302 buck (SW->L->rail) carrying `iout` on its output rail, built
    so powertree detects it (value prefix + SW->inductor->rail hop)."""
    c = Circuit("th", "th")
    c.part("U1", "Regulator_Switching:TPS54302", "TPS54302DDCR",
           "Package_TO_SOT_SMD:TSOT-23-6")
    c.part("L1", "Device:L", "10uH", "")
    c.net(vin_rail, "U1.3")               # VIN (pin 3)
    c.net("GND", "U1.1")                   # GND (pin 1)
    c.net("SW_X", "U1.2", "L1.1")          # SW (pin 2) -> inductor
    c.net(vout_rail, "L1.2")               # inductor -> output rail
    c.draws(vout_rail, iout, "synthetic buck load")
    return c


def test_tps54302_over_2A_fails_at_datasheet_rthja():
    """The whole point of the finding: a TPS54302 (no EP) carrying the real
    +3V3 load (~2.745 A) runs OVER its 125 C rec-max even at the conservative
    eff floor. At the DS RthJA the gate MUST fail it (no waiver)."""
    c = _tps54302_buck_sheet(2.745, "+3V3", "+5V")
    pt = powertree.analyze([_sheet("th", c)])
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    dev = next(d for d in r.devices if d.ref == "U1")
    # Pd = (1/0.85-1)*3.3*2.745 = 1.599 W ; Tj = 50 + 1.599*118.9 = 240 C
    assert dev.tj > 200.0, f"Tj should be ~240 C at DS RthJA, got {dev.tj:.1f}"
    assert dev.tj_max == 125.0
    assert not r.ok and dev.over, "must FAIL the 125 C rec-max guard"


def test_lm61460_ep_buck_passes_same_load():
    """The swap target: the LM61460 (EP-equivalent PGND/SW pads -> GND pour,
    pour-credit 30 C/W) carries the SAME +3V3 load comfortably under its 150 C
    rec-max guard — proving the reselection actually fixes the finding."""
    c = Circuit("th", "th")
    c.part("U1", "LM61460AANRJRR:LM61460AANRJRR", "LM61460AANRJRR", "")
    c.part("L1", "Device:L", "10uH", "")
    c.net("+5V", "U1.8")                   # VIN1 (pin 8)
    c.net("GND", "U1.9", "U1.11", "U1.3")  # PGND1/PGND2/AGND heat path
    c.net("SW_X", "U1.10", "L1.1")         # SW (pin 10) -> inductor
    c.net("+3V3", "L1.2")
    c.draws("+3V3", 2.745, "synthetic buck load")
    pt = powertree.analyze([_sheet("th", c)])
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    dev = next(d for d in r.devices if d.ref == "U1")
    # Pd = (1/0.85-1)*3.3*2.745 = 1.599 W ; Tj = 50 + 1.599*30 = 98 C < 140 guard
    assert dev.poured, "LM61460 must take the cited pour-aware RthJA credit"
    assert dev.tj < 110.0, f"Tj should be ~98 C at the pour RthJA, got {dev.tj:.1f}"
    assert r.ok and not dev.over, "the EP buck must PASS with real margin"
