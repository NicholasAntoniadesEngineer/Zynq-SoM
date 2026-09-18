from __future__ import annotations

import types

import pytest

from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.verify import design_rules

_MCU = "MCU_ST_STM32F0:STM32F030F4Px"


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_power_pin_name_inference():
    assert design_rules.is_power_pin_name("VDD")
    assert design_rules.is_power_pin_name("VDDA")
    assert design_rules.is_power_pin_name("VDDIO2")
    assert design_rules.is_power_pin_name("VCC_3V3")
    assert not design_rules.is_power_pin_name("VSS")
    assert not design_rules.is_power_pin_name("VOUT")
    assert not design_rules.is_power_pin_name("VLAN")
    assert not design_rules.is_power_pin_name("")


def test_current_board_passes_design_rules():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = design_rules.check(sheets, Library())
    assert r.ok, f"unexpected design-rule findings: {r.findings}"
    assert r.checked.get("decap", 0) > 20
    assert r.checked.get("i2c", 0) >= 1


def test_missing_decap_fails():
    c = Circuit("dr", "dr")
    c.part("U1", _MCU, "STM32F030", "")
    c.net("+3V3", "U1.16", "U1.5")
    c.net("GND", "U1.15")
    r = design_rules.check([_sheet("dr", c)], Library())
    assert not r.ok, "a supply pin with no bypass cap must FAIL DECAP"
    assert r.decap and any("U1" in f and "+3V3" in f for f in r.decap), r.decap


def test_decap_present_passes():
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
    assert r.ok
    assert any("DECAP" in w and "U1" in w and "mezzanine" in w
               for w in r.waived), r.waived


@pytest.mark.parametrize("failure", [KeyboardInterrupt, SystemExit,
                                     MemoryError, OSError])
def test_native_adapter_propagates_cancellation_and_resource_errors(failure):
    c = Circuit("errors")
    c.part("U1", "Fixture:Missing", "unknown", "")

    class BrokenLibrary:
        def get(self, _):
            raise failure("intentional failure")

    with pytest.raises(failure, match="intentional failure"):
        design_rules.check([_sheet("errors", c)], BrokenLibrary())


def test_native_adapter_resolves_each_symbol_once_and_preserves_unknown_skip():
    c = Circuit("unknown")
    c.part("U1", "Fixture:Missing", "unknown", "")
    c.part("U2", "Fixture:Missing", "unknown", "")

    class MissingLibrary:
        calls = 0

        def get(self, _):
            self.calls += 1
            raise KeyError("missing symbol")

    lib = MissingLibrary()
    result = design_rules.check([_sheet("unknown", c)], lib)
    assert lib.calls == 1
    assert result.ok  # Electrical completeness remains a separate mandatory gate.
    result.i2c.append("injected missing pull-up")
    assert "injected missing pull-up" in result.report()
    assert "DESIGN RULES: FAIL" in result.summary()


def test_native_testpoint_adapter_observes_current_circuit_and_report_mutations():
    from schgen.verify import testpoints

    c = Circuit("probes")
    c.part("R1", "Device:R", "10k", "")
    c.net("+3V3", "R1.1")
    c.net("GND", "R1.2")
    sheets = [_sheet("probes", c)]
    before = testpoints.check_coverage(sheets)
    assert not before.ok and len(before.errors) == 2
    c.testpoint("+3V3")
    c.waive_tp("GND", "fixture-only waiver")
    after = testpoints.check_coverage(sheets)
    assert after.ok and after.covered == 1
    assert not before.ok  # Prior result is a snapshot, not a shared mutable cache.
    after.errors.append("injected failure")
    assert "TESTPOINTS: FAIL" in after.report()
    assert "injected failure" in after.report()


def test_design_rule_command_writes_selected_project(tmp_path, monkeypatch):
    from schgen.core import link, project

    selected = tmp_path / "selected-project"
    monkeypatch.setattr(project, "PROJECT_ROOT", selected)
    monkeypatch.setattr(link, "all_subsystem_paths", lambda: [])
    assert design_rules.cmd_design_rules(types.SimpleNamespace(subsystems=[])) == 0
    report = selected / "reports" / "design_rules.txt"
    assert report.read_text().endswith("DESIGN RULES: PASS (0 findings, 0 waived)\n")
