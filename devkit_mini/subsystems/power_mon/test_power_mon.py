from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from devkit_mini.subsystems.power_mon import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "power_mon.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return build()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _pins(c: Circuit, net: str) -> set[str]:
    return {f"{p.ref}.{p.pin}" for p in c.nets[net].pins} if net in c.nets else set()


def test_is_power_mon(c: Circuit):
    assert c.name == "power_mon"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert len(c.nc_pins) == 6
    nc_refs = sorted({str(p).split(".")[0] for p in c.nc_pins})
    assert nc_refs == ["U1", "U2"]


def test_decoupling_and_pad_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("ep", 0) >= 2
    assert r.checked.get("decap", 0) >= 2


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")
                or ref.startswith("RS")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_shunts_split_each_rail_with_documented_values(c: Circuit):
    expect = {
        "RS1": ("+VIN", "+VIN_SYS", "10mR"),
        "RS2": ("+5V_REG", "+5V", "10mR"),
        "RS3": ("+3V3_REG", "+3V3", "10mR"),
        "RS4": ("+1V8_REG", "+1V8", "20mR"),
    }
    for ref, (hi, lo, val) in expect.items():
        assert c.parts[ref].value == val, (ref, c.parts[ref].value)
        assert f"{ref}.1" in _pins(c, hi), (ref, hi)
        assert f"{ref}.2" in _pins(c, lo), (ref, lo)
    assert parse_si("10mR") == 0.01 and parse_si("20mR") == 0.02


def test_unused_u2_channels_to_gnd(c: Circuit):
    """Deliberately weak: at least four ch2/ch3 inputs on GND, not which pin is which."""
    gnd = _pins(c, "GND")
    u2_on_gnd = {p for p in gnd if p.startswith("U2.")}
    assert len(u2_on_gnd) >= 4, u2_on_gnd


def _cir_elems(prefix: str) -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt power_mon"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(rf"^{prefix}\w", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


_CIR_RS = {"RS1", "RS2", "RS3", "RS4"}
_CIR_CAPS = {"C1", "C2", "C3"}


def test_cir_subckt_pins_are_the_carrier_externals():
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt power_mon"))
    pins = header.split()[2:]
    assert pins == ["+VIN", "+VIN_SYS", "+5V_REG", "+5V", "+3V3_REG", "+3V3",
                    "+1V8_REG", "+1V8", "+3V3_SC", "GND"], pins


def test_cir_shunts_match_netlist(c: Circuit):
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_RS)
    cir = sorted(v for k, v in _cir_elems("R").items() if k in _CIR_RS)
    assert cir == netlist, (cir, netlist)


def test_cir_caps_match_netlist(c: Circuit):
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_CAPS)
    cir = sorted(_cir_elems("C").values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_address_straps_0x40_0x41(c: Circuit):
    """Asserted as a pin-count delta: A0 shares its rail with the VS/VPU supply pins."""
    sc = _pins(c, "+3V3_SC")
    assert {"R1.1", "C1.1", "C2.1", "C3.1"} <= sc
    assert sum(1 for p in sc if p.startswith("U1.")) == 2
    assert sum(1 for p in sc if p.startswith("U2.")) == 3


def test_alert_wire_or_critical_defined_high(c: Circuit):
    alert = _pins(c, "PMON_ALERT_N")
    assert {"U1.9", "U2.9", "R1.2"} <= alert, alert
    assert c.parts["R1"].value == "10k"
    assert "R1.1" in _pins(c, "+3V3_SC")


def test_i2c_ports_typed_on_stm32_bus(c: Circuit):
    assert c.port_type_of("STM32_I2C2_SDA").kind == "i2c"
    assert c.port_type_of("STM32_I2C2_SDA").role == "sda"
    assert c.port_type_of("STM32_I2C2_SCL").role == "scl"
    assert c.port_type_of("STM32_I2C2_SDA").bus == "STM32_I2C2"
    assert c.port_type_of("STM32_I2C2_SDA").speed_hz == 400_000
    sda, scl = _pins(c, "STM32_I2C2_SDA"), _pins(c, "STM32_I2C2_SCL")
    assert {"U1.7", "U2.7"} <= sda, sda
    assert {"U1.6", "U2.6"} <= scl, scl


def test_both_are_the_ina3221(c: Circuit):
    for ref in ("U1", "U2"):
        assert c.parts[ref].lib_id.split(":")[-1] == "INA3221AIRGVR"
        assert (c.parts[ref].fields or {}).get("LCSC") == "C181255"
