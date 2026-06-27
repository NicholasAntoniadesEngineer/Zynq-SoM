"""Tests for the DESIGN-RULE COMPLETENESS gate (schgen/verify/design_rules.py).

Locks: the power-pin-name inference; the CURRENT board passes (netlist is
electrically complete, real subject coverage across all four rules); a synthetic
multi-pin IC whose VDD rail has NO local decoupling cap FAILS the DECAP rule;
the same circuit WITH a bypass cap passes; and an author waive_decap demotes the
finding to a verbatim waiver. Pure/offline (model + symbol pin tables only; no
kicad-cli, no network)."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.verify import design_rules

# A real KiCad symbol with named power pins (VDD pin 16, VDDA pin 5, VSS 15) —
# the gate reads its pin table from the library, so the lib_id must resolve.
_MCU = "MCU_ST_STM32F0:STM32F030F4Px"


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_power_pin_name_inference():
    assert design_rules.is_power_pin_name("VDD")
    assert design_rules.is_power_pin_name("VDDA")
    assert design_rules.is_power_pin_name("VDDIO2")
    assert design_rules.is_power_pin_name("VCC_3V3")
    assert not design_rules.is_power_pin_name("VSS")        # ground, not a supply
    assert not design_rules.is_power_pin_name("VOUT")       # output rail, not an input
    # VL prefix must not over-match
    assert not design_rules.is_power_pin_name("VLAN")
    assert not design_rules.is_power_pin_name("")


def test_current_board_passes_design_rules():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = design_rules.check(sheets, Library())
    assert r.ok, f"unexpected design-rule findings: {r.findings}"
    # real coverage across the rules, not a no-op
    assert r.checked.get("decap", 0) > 20
    assert r.checked.get("i2c", 0) >= 1


def test_missing_decap_fails():
    # a multi-pin IC with VDD on +3V3 and NO cap-to-GND on its sheet must FAIL
    # the DECAP rule.
    c = Circuit("dr", "dr")
    c.part("U1", _MCU, "STM32F030", "")
    c.net("+3V3", "U1.16", "U1.5")     # VDD(16) + VDDA(5)
    c.net("GND", "U1.15")              # VSS
    r = design_rules.check([_sheet("dr", c)], Library())
    assert not r.ok, "a supply pin with no bypass cap must FAIL DECAP"
    assert r.decap and any("U1" in f and "+3V3" in f for f in r.decap), r.decap


def test_decap_present_passes():
    # the same IC WITH a 100n cap from +3V3 to GND on the sheet passes.
    c = Circuit("dr", "dr")
    c.part("U1", _MCU, "STM32F030", "")
    c.part("C1", "Device:C", "100n", "")
    c.net("+3V3", "U1.16", "U1.5", "C1.1")
    c.net("GND", "U1.15", "C1.2")
    r = design_rules.check([_sheet("dr", c)], Library())
    assert r.ok, r.findings
    assert r.checked.get("decap", 0) >= 1


def test_decap_waiver_is_listed_verbatim():
    c = Circuit("dr", "dr")
    c.part("U1", _MCU, "STM32F030", "")
    c.net("+3V3", "U1.16", "U1.5")
    c.net("GND", "U1.15")
    c.waive_decap("U1", "bulk bypass lives on the mezzanine board")
    r = design_rules.check([_sheet("dr", c)], Library())
    assert r.ok                                       # no hard finding
    assert any("DECAP" in w and "U1" in w and "mezzanine" in w
               for w in r.waived), r.waived
