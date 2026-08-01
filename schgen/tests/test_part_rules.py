from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import part_rules, powertree


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_value_parser():
    assert part_rules._ohms("10k") == 10000.0
    assert part_rules._ohms("330R") == 330.0
    assert part_rules._ohms("4k7") == 4700.0
    assert part_rules._ohms("1") == 1.0
    assert abs(part_rules._ohms("10m") - 0.010) < 1e-9


def test_current_board_passes_part_rules():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = part_rules.analyze(sheets)
    assert r.ok, f"unexpected findings: {r.findings}"
    assert r.checked > 50


def test_underrated_cap_fails():
    c = Circuit("t", "t")
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric",
           LCSC="C15850")
    c.net("+VIN", "C1.1")
    c.net("GND", "C1.2")
    r = part_rules.analyze([_sheet("t", c)], pt_res=powertree.Result())
    assert any("CAP_V" in f and "C1" in f for f in r.findings), r.findings


def test_adequately_rated_cap_passes():
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
    assert r.ok
    assert any("WAIVED" in n and "C1" in n for n in r.notes), r.notes
