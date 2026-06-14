"""Tests for the per-part rule engine (schgen/verify/part_rules.py).

Locks: the CURRENT board passes (0 findings — it self-derates); a synthetic
under-rated cap FAILS the CAP_VOLTAGE rule; the value parser; and a waiver
demotes a finding to a note. Pure/offline (powertree.rail_volts only)."""

from __future__ import annotations

import types

from schgen import powertree
from schgen.model import Circuit
from schgen.verify import part_rules


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_value_parser():
    assert part_rules._ohms("10k") == 10000.0
    assert part_rules._ohms("330R") == 330.0
    assert part_rules._ohms("4k7") == 4700.0
    assert part_rules._ohms("1") == 1.0
    assert abs(part_rules._ohms("10m") - 0.010) < 1e-9


def test_current_board_passes_part_rules():
    from schgen.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = part_rules.analyze(sheets)
    assert r.ok, f"unexpected findings: {r.findings}"
    assert r.checked > 50            # real coverage, not a no-op


def test_underrated_cap_fails():
    # a 25 V X5R cap (C15850) directly across the 20 V +VIN rail needs >= 2x =
    # 40 V -> must FAIL CAP_VOLTAGE.
    c = Circuit("t", "t")
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric",
           LCSC="C15850")
    c.net("+VIN", "C1.1")
    c.net("GND", "C1.2")
    r = part_rules.analyze([_sheet("t", c)], pt_res=powertree.Result())
    assert any("CAP_V" in f and "C1" in f for f in r.findings), r.findings


def test_adequately_rated_cap_passes():
    # the same 25 V cap on +3V3 (needs 2x = 6.6 V) is fine.
    c = Circuit("t", "t")
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric",
           LCSC="C15850")
    c.net("+3V3", "C1.1")
    c.net("GND", "C1.2")
    r = part_rules.analyze([_sheet("t", c)], pt_res=powertree.Result())
    assert r.ok and r.checked == 1


def test_waiver_demotes_cap_finding_to_note():
    c = Circuit("t", "t")
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric",
           LCSC="C15850")
    c.net("+VIN", "C1.1")
    c.net("GND", "C1.2")
    c.waive_part_rule("C1", "bench-validated under the actual DC bias")
    r = part_rules.analyze([_sheet("t", c)], pt_res=powertree.Result())
    assert r.ok                                   # no hard finding
    assert any("WAIVED" in n and "C1" in n for n in r.notes), r.notes
