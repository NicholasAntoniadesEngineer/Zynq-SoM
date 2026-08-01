from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice

from devkit_mini.subsystems.som_j2.som_j2 import circuit

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_j2.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_is_the_j2_connector(c: Circuit):
    assert c.name == "som_j2"
    assert c.title == "SoM J2: FPGA bank 13/33 IO + VCCO rails"
    assert sorted(c.parts) == ["J2"]
    assert c.parts["J2"].lib_id.endswith("DF40C-100DP-0.4V_51")
    assert c.parts["J2"].value == "DF40C-100DP-0.4V(51)"


def test_connector_has_no_discretes(c: Circuit):
    passive = [r for r, p in c.parts.items()
               if p.lib_id.endswith((":C", ":R", ":L"))]
    assert passive == [], passive


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"J2.101", "J2.102", "J2.103", "J2.104"}


def test_every_part_pin_is_accounted_for(c: Circuit, lib: Library):
    total = len(lib.pin_numbers(c.parts["J2"].lib_id))
    netted = {pr for n in c.nets.values() for pr in n.pins}
    assert total == 104
    assert len(netted) + len(c.nc_pins) == total


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) == 0


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_vcco_rail_present_and_classed(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls.get("+3V3") is NetClass.POWER
    assert cls.get("GND") is NetClass.GROUND
    assert "+VCCO_13" not in cls and "+VCCO_33" not in cls


def test_vcco_draw_declared(c: Circuit):
    assert "+3V3" in c.loads
    amps = sum(a for a, _ in c.loads["+3V3"])
    assert amps == pytest.approx(0.020)


def test_no_function_pairs_typed(c: Circuit):
    assert "HDMI_RX_CLK_P" not in c.nets
    assert "IO_L12_MRCC_P_33" in c.nets
    assert c.port_type_of("IO_L12_MRCC_P_33").pair_with is None


def test_key_function_ports_present(c: Circuit):
    for port in ("ZYNQ_PS_UART0_CTS_N", "ZYNQ_PS_UART0_RTS_N"):
        assert port in c.nets, port
    for spare in ("IO_L16_P_13", "IO_L13_MRCC_P_13", "IO_L11_SRCC_P_13",
                  "IO_L6_N_VREF_13", "IO_25_33", "IO_L6_P_33"):
        assert spare in c.nets, spare


def test_cir_subckt_parses_and_declares_rail():
    text = CIR.read_text()
    header = next(l for l in text.splitlines()
                  if l.strip().lower().startswith(".subckt som_j2"))
    pins = header.split()[2:]
    assert pins[-1] == "GND"
    assert "V3V3" in pins
    assert not re.search(r"(?m)^C\d", text)
