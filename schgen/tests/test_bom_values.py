"""Tests for the LCSC-value gate (schgen/verify/bom_values.py).

Locks: the value normaliser (unit suffix, EIA R-notation, SI prefix); the
CURRENT board passes (every catalogued inline passive's declared value matches
the part behind its LCSC); the C25750 POISON entry FAILS a 40.2k resistor
(the board-killer this gate exists to stop); and the correct C12447 passes.
Pure/offline (the catalog is a committed data file)."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import bom_values


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def _is(got, cls, mag):
    return got is not None and got[0] == cls and abs(got[1] - mag) <= 1e-9 * max(1.0, mag)


def test_value_normaliser():
    n = bom_values._norm
    assert _is(n("40.2k", "R"), "R", 40200.0)
    assert _is(n("40.2kΩ", None), "R", 40200.0)
    assert _is(n("40.2kOhm", None), "R", 40200.0)
    assert _is(n("4k7", "R"), "R", 4700.0)
    assert _is(n("22k1", "R"), "R", 22100.0)
    assert _is(n("49.9R", "R"), "R", 49.9)
    assert _is(n("100R", "R"), "R", 100.0)
    assert _is(n("10mR", "R"), "R", 0.010)        # shunt milliohm
    assert _is(n("100n", "C"), "C", 100e-9)
    assert _is(n("100nF", None), "C", 100e-9)
    assert _is(n("2.2u", "C"), "C", 2.2e-6)
    assert _is(n("22p", "C"), "C", 22e-12)
    assert _is(n("10uH", "L"), "L", 10e-6)
    assert n("LM61460AANRJRR", None) is None      # MPN, not a magnitude


def test_current_board_passes_bom_values():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = bom_values.run(sheets)
    assert r.ok, f"unexpected value mismatches: {r.mismatches}"
    assert r.checked > 20            # real passive coverage, not a no-op


def test_c25750_poison_fails():
    # the board-killer: a 40.2k FB resistor re-keyed to C25750 (really 120k).
    c = Circuit("t", "t")
    c.part("R1", "Device:R", "40.2k", "Resistor_SMD:R_0603_1608Metric",
           LCSC="C25750")
    c.net("A", "R1.1")
    c.net("B", "R1.2")
    r = bom_values.run([_sheet("t", c)])
    assert not r.ok, "C25750 (120k) on a 40.2k resistor must FAIL"
    assert any("R1" in m and "C25750" in m for m in r.mismatches), r.mismatches


def test_correct_code_passes():
    # C12447 IS a 40.2k 0603 part — the corrected R1 LCSC.
    c = Circuit("t", "t")
    c.part("R1", "Device:R", "40.2k", "Resistor_SMD:R_0603_1608Metric",
           LCSC="C12447")
    c.net("A", "R1.1")
    c.net("B", "R1.2")
    r = bom_values.run([_sheet("t", c)])
    assert r.ok, r.mismatches
    assert r.checked == 1


def test_uncatalogued_is_unverified_not_failing():
    c = Circuit("t", "t")
    c.part("R9", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric",
           LCSC="C0000000")
    c.net("A", "R9.1")
    c.net("B", "R9.2")
    r = bom_values.run([_sheet("t", c)])
    assert r.ok                       # unknown code never fails the build
    assert any("C0000000" in u for u in r.unverified)
