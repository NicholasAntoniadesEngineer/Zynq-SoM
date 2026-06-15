"""Tests for the power-tree BUDGET gate (schgen/verify/powertree.py).

Locks: the SI value parser; rail-voltage resolution by name; the CURRENT board
passes (every regulator/source within its limit, real regulator coverage); and
a synthetic LDO loaded past its datasheet current limit FAILS with an OVERRUN.
Pure/offline (the tree + per-rail totals come from the model + c.draws budget;
no kicad-cli, no network)."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import powertree


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_parse_si():
    assert powertree.parse_si("6.8k") == 6800.0
    assert powertree.parse_si("4k7") == 4700.0
    assert powertree.parse_si("22k1") == 22100.0
    assert abs(powertree.parse_si("100n") - 100e-9) < 1e-18
    assert abs(powertree.parse_si("10mR") - 0.010) < 1e-9
    assert powertree.parse_si("1.5R") == 1.5
    assert powertree.parse_si("not-a-value") is None


def test_rail_volts_by_name():
    assert powertree.rail_volts("+VIN") == 20.0
    assert powertree.rail_volts("+5V_SOM") == 4.65       # PWR-5 re-centre
    assert powertree.rail_volts("+5V_REG") == 5.0
    assert powertree.rail_volts("+3V3") == 3.3
    assert powertree.rail_volts("+1V8") == 1.8
    assert powertree.rail_volts("+2V5") == 2.5
    assert powertree.rail_volts("SOME_SIGNAL") is None


def test_current_board_passes_powertree():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = powertree.analyze(sheets)
    assert r.ok, f"unexpected power-tree overruns: {r.errors}"
    assert len(r.regs) > 10          # real regulator coverage, not a no-op


def test_ldo_over_current_fails():
    # an AP2112K LDO (600 mA datasheet limit) feeding +3V3 with a declared
    # 1.5 A draw must FAIL the regulator-overrun gate. A non-library lib_id is
    # used so the model accepts the IN(1)/OUT(5) pins the RegSpec resolves
    # (the gate is model-only; it never renders the symbol).
    c = Circuit("pt", "pt")
    c.part("U1", "Fake:LDO", "AP2112K-3.3", "")
    c.net("+5V_REG", "U1.1")          # IN rail (5.0 V)
    c.net("+3V3", "U1.5")             # OUT rail (3.3 V)
    c.draws("+3V3", 1.5, "synthetic 1.5 A overload")
    r = powertree.analyze([_sheet("pt", c)])
    assert not r.ok, "1.5 A on a 0.6 A LDO must FAIL"
    assert any("OVERRUN" in e and "U1" in e for e in r.errors), r.errors


def test_ldo_within_limit_passes():
    # the same LDO at 0.3 A (< 0.6 A limit) is fine — proves the negative
    # above is the load, not the topology.
    c = Circuit("pt", "pt")
    c.part("U1", "Fake:LDO", "AP2112K-3.3", "")
    c.net("+5V_REG", "U1.1")
    c.net("+3V3", "U1.5")
    c.draws("+3V3", 0.3, "synthetic 0.3 A load")
    r = powertree.analyze([_sheet("pt", c)])
    assert r.ok, r.errors
    reg = next(reg for reg in r.regs if reg.ref == "U1")
    assert reg.kind == "ldo" and abs(reg.i_out - 0.3) < 1e-9
