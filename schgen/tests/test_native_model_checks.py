from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

from schgen.core.model import Circuit
from schgen.verify import powertree, thermal


def test_native_result_keeps_numeric_field_types():
    from schgen.core.link import load_subsystem
    result = powertree.analyze([load_subsystem("power_som")])
    assert result.regs
    for reg in result.regs:
        assert type(reg.n) is int
        for field in fields(reg):
            if field.type in (float, "float"):
                assert type(getattr(reg, field.name)) is float
    assert all(type(value) is float for value in result.rails.values())
    assert all(type(value) is float for value in result.source_load.values())


def test_native_policy_snapshot_honors_caller_overrides(monkeypatch):
    monkeypatch.setattr(powertree, "_VOLT_PATTERNS", ((r"^CUSTOM$", 7.0),))
    assert powertree.rail_volts("CUSTOM") == 7.0
    assert powertree.rail_volts("+3V3") is None
    monkeypatch.setattr(powertree, "_VOLT_PATTERNS", ((r"^CUSTOM$", 9.0),))
    assert powertree.rail_volts("CUSTOM") == 9.0


def test_supplied_power_result_not_recomputed_by_thermal():
    sheet = SimpleNamespace(name="caller", circuit=Circuit("caller", "caller"))
    power = powertree.Result(regs=[powertree.Reg(
        1, "caller", "U1", "AP2112K", "ldo", "+5V", "+1V8", 0.6, 1.0, "edited", 0.5, 0.5)])
    result = thermal.analyze([sheet], pt_res=power)
    assert len(result.devices) == 1
    assert result.devices[0].i_out == 0.5
    assert result.devices[0].pd == (5.0 - 1.8) * 0.5
    assert not result.ok
    power.regs[0].i_out = 0.01
    revised = thermal.analyze([sheet], pt_res=power)
    assert revised.devices[0].i_out == 0.01
    assert revised.ok
