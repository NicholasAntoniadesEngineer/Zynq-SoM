from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, spice
from schgen.verify.powertree import parse_si

from carrier.subsystems.board_qwiic import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "board_qwiic.cir"


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


def test_is_board_qwiic(c: Circuit):
    assert c.name == "board_qwiic"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == set()


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """checked == 0 is asserted so a decap rule that stopped running cannot pass."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) == 0


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt board_qwiic"):
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
                  if l.strip().lower().startswith(".subckt board_qwiic"))
    pins = header.split()[2:]
    assert pins == ["GND", "V3V3_AUX", "AUX_I2C_SDA", "AUX_I2C_SCL", "V3V3"], pins


def test_cir_has_no_netlist_passive_caps(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    assert netlist == []
    assert sorted(_cir_caps().values()) == netlist


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_parts_present(c: Circuit):
    assert c.parts["J1"].lib_id.split(":")[-1] == "ZX-SH1.0-4PWT"
    assert c.parts["U1"].lib_id.split(":")[-1] == "USBLC6-2SC6"


def test_esd_passthrough(c: Circuit):
    assert "U1.1" in _pins(c, "QWIIC_SDA")
    assert "U1.3" in _pins(c, "QWIIC_SCL")
    assert "U1.6" in _pins(c, "AUX_I2C_SDA")
    assert "U1.4" in _pins(c, "AUX_I2C_SCL")


def test_external_lines_reach_bus_only_through_array(c: Circuit):
    assert not ({"J1.3", "J1.4"} & _pins(c, "AUX_I2C_SDA"))
    assert not ({"J1.3", "J1.4"} & _pins(c, "AUX_I2C_SCL"))


def test_clamp_reference_is_always_on(c: Circuit):
    assert "U1.5" in _pins(c, "+3V3")
    assert "U1.5" not in _pins(c, "+3V3_AUX")
    assert "J1.2" in _pins(c, "+3V3_AUX")


def test_aux_i2c_ports_typed(c: Circuit):
    assert c.port_type_of("AUX_I2C_SDA").bus == "AUX_I2C"
    assert c.port_type_of("AUX_I2C_SCL").bus == "AUX_I2C"
    assert c.port_type_of("AUX_I2C_SDA").kind == "i2c"
    assert c.port_type_of("AUX_I2C_SDA").role == "sda"
    assert c.port_type_of("AUX_I2C_SCL").role == "scl"
    assert c.port_type_of("AUX_I2C_SCL").speed_hz == 400_000
