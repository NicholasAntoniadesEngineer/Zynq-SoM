from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from carrier.subsystems.board_services import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "board_services.cir"


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


def test_is_board_services(c: Circuit):
    assert c.name == "board_services"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"U2.1", "U3.3"}


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 3


def test_each_ic_supply_has_a_local_100n(c: Circuit):
    n = 0
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        names = {x.name for x in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if x}
        if names == {"+3V3_AUX", "GND"}:
            assert p.value == "100n", (ref, p.value)
            n += 1
    assert n == 3, n


def test_rtc_vbackup_decap_waived_not_vdd(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert "U2.7" in _pins(c, "+3V3_AUX")


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt board_services"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_carrier_externals():
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt board_services"))
    pins = header.split()[2:]
    assert pins == ["VDD_AUX", "GND", "AUX_I2C_SCL", "AUX_I2C_SDA",
                    "WATCHDOG_KICK", "WATCHDOG_RST_N"], pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_i2c_ports_typed_on_aux_bus(c: Circuit):
    assert c.port_type_of("AUX_I2C_SCL").kind == "i2c"
    assert c.port_type_of("AUX_I2C_SCL").role == "scl"
    assert c.port_type_of("AUX_I2C_SDA").role == "sda"
    assert c.port_type_of("AUX_I2C_SCL").bus == "AUX_I2C" == \
        c.port_type_of("AUX_I2C_SDA").bus
    assert c.port_type_of("AUX_I2C_SCL").speed_hz == 400_000
    scl, sda = _pins(c, "AUX_I2C_SCL"), _pins(c, "AUX_I2C_SDA")
    assert {"U1.1", "U2.3"} <= scl, scl
    assert {"U1.3", "U2.4"} <= sda, sda


def test_eeprom_address_strap_0x51(c: Circuit):
    assert "U1.5" in _pins(c, "+3V3_AUX")
    assert "U1.4" in _pins(c, "GND")


def test_eeprom_rtc_watchdog_parts_present(c: Circuit):
    assert c.parts["U1"].lib_id.split(":")[-1] == "24AA025E48T-I_OT"
    assert c.parts["U2"].lib_id.split(":")[-1] == "RV-3028-C7-32.768kHz-1ppm-TA-QC"
    assert c.parts["U3"].lib_id.split(":")[-1] == "TPS3823-33DBVR"
    assert c.parts["BT1"].lib_id.split(":")[-1] == "KH-CR1220-2"


def test_rtc_unused_pins_and_coin_cell(c: Circuit):
    assert "U2.8" in _pins(c, "GND")
    assert not any("U2.1" in _pins(c, n) for n in c.nets)
    bat = _pins(c, "V_RTC_BAT")
    assert "U2.6" in bat and "BT1.1" in bat


def test_watchdog_cannot_reset_the_system_at_power_up(c: Circuit):
    assert "U3.5" in _pins(c, "+3V3_AUX")
    assert not any("U3.3" in _pins(c, n) for n in c.nets)
    assert "U3.1" in _pins(c, "WATCHDOG_RST_N")


def test_watchdog_nets_are_on_bank33_not_bank35(c: Circuit):
    assert "WATCHDOG_KICK" in c.nets and "WATCHDOG_RST_N" in c.nets
    assert "IO_L16_P_35" not in c.nets
    assert "IO_L16_N_35" not in c.nets
