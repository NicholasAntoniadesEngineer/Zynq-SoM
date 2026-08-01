from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice

from devkit_mini.subsystems.som_j3.som_j3 import circuit

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_j3.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_is_the_j3_connector(c: Circuit):
    assert c.name == "som_j3"
    assert c.title == "SoM J3: FPGA bank 33/34/35 IO + VCCO rails"
    assert sorted(c.parts) == ["J3"]
    assert c.parts["J3"].lib_id.endswith("DF40C-100DP-0.4V_51")
    assert c.parts["J3"].value == "DF40C-100DP-0.4V(51)"


def test_connector_has_no_discretes(c: Circuit):
    passive = [r for r, p in c.parts.items()
               if p.lib_id.endswith((":C", ":R", ":L"))]
    assert passive == [], passive


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"J3.101", "J3.102", "J3.103", "J3.104"}


def test_every_part_pin_is_accounted_for(c: Circuit, lib: Library):
    total = len(lib.pin_numbers(c.parts["J3"].lib_id))
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


def test_vcco_rails_present_and_classed(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls.get("+3V3") is NetClass.POWER
    assert "+2V5_VADJ" not in cls
    assert cls.get("GND") is NetClass.GROUND
    assert "+VCCO_34" not in cls and "+VCCO_35" not in cls


def test_vcco_draws_declared(c: Circuit):
    assert sum(a for a, _ in c.loads["+3V3"]) == pytest.approx(0.020)


def test_no_function_pairs_typed(c: Circuit):
    assert "CAM_CLK_P" not in c.nets and "FMC_LA00_CC_P" not in c.nets
    assert "IO_L13_MRCC_P_35" in c.nets
    assert c.port_type_of("IO_L13_MRCC_P_35").pair_with is None


def test_key_function_ports_present(c: Circuit):
    for spare in ("IO_L7_P_34", "IO_L16_P_34", "IO_L4_P_33", "IO_L1_P_33",
                  "IO_L3P_PUDC_34"):
        assert spare in c.nets, spare
    assert "PUDC_34" not in c.nets


def test_cir_subckt_parses_and_declares_rails():
    text = CIR.read_text()
    header = next(l for l in text.splitlines()
                  if l.strip().lower().startswith(".subckt som_j3"))
    pins = header.split()[2:]
    assert pins[-1] == "GND"
    assert "V3V3" in pins
    assert not re.search(r"(?m)^C\d", text)
