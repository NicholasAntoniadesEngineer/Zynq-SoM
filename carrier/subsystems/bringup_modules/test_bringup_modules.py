from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si

import carrier.subsystems.bringup_modules.bringup_modules as bm

HERE = Path(__file__).resolve().parent
CIR = HERE / "bringup_modules.cir"

GATED_RAILS = ("+3V3_HDMI_TX", "+3V3_HDMI_RX", "+3V3_LCD", "+3V3_CAM",
               "+3V3_SD", "+5V_USB", "+3V3_PMOD", "+3V3_USER_LED",
               "+5V_HDMI_TX", "+5V_LCD")
SOURCE_RAILS = ("+3V3", "+5V")
EN_NETS = ("EN_HDMI_TX", "EN_HDMI_RX", "EN_LCD", "EN_CAM", "EN_SD", "EN_USB",
           "EN_PMOD", "EN_USER_LED", "EN_HDMI_TX_5V", "EN_LCD_5V")


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return bm.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins


def test_ten_load_switches_present(c: Circuit):
    sw = [r for r, p in c.parts.items()
          if r.startswith("U") and "SY6280" in p.value]
    assert len(sw) == 10, sw


def test_gated_rails_are_power_nets(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in GATED_RAILS + SOURCE_RAILS:
        assert cls[rail] is NetClass.POWER, (rail, cls.get(rail))
    assert cls["GND"] is NetClass.GROUND
    for en in EN_NETS:
        assert cls[en] is NetClass.PORT, (en, cls.get(en))


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.strap, r.strap
    assert not r.ep, r.ep


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_each_switch_has_in_and_out_decoupling(c: Circuit):
    caps = [p.value for p in c.parts.values() if p.lib_id.endswith(":C")]
    assert len(caps) == 20, len(caps)
    assert set(caps) == {"100n"}, set(caps)


def test_rset_value_set(c: Circuit):
    rset = [p.value for ref, p in c.parts.items()
            if p.lib_id.endswith(":R")
            and any((n := c.net_of(PinRef(ref, pn))) and
                    n.name.startswith("BU_ISET_") for pn in ("1", "2"))]
    assert len(rset) == 10, rset
    assert set(rset) == {"13k", "6.8k"}, set(rset)


def test_each_gated_output_has_a_status_led(c: Circuit):
    leds = [p for p in c.parts.values() if p.lib_id.endswith(":LED")]
    assert len(leds) == 10, len(leds)
    assert all(p.value == "red" for p in leds)
    pg_rs = [p.value for ref, p in c.parts.items()
             if p.lib_id.endswith(":R")
             and any((n := c.net_of(PinRef(ref, pn))) and
                     n.name.startswith("BU_PG_") for pn in ("1", "2"))]
    assert len(pg_rs) == 10, pg_rs
    assert set(pg_rs) == {"330R", "1k"}, set(pg_rs)


def test_every_gated_rail_is_probeable(c: Circuit):
    tp_nets = set()
    for ref, p in c.parts.items():
        if not ref.startswith("TP"):
            continue
        n = c.net_of(PinRef(ref, "1"))
        if n:
            tp_nets.add(n.name)
    for rail in GATED_RAILS:
        assert rail in tp_nets, (rail, sorted(tp_nets))


def test_power_draw_declared_on_each_gated_rail(c: Circuit):
    for rail in GATED_RAILS:
        assert rail in c.loads, rail


def _cir_passives() -> tuple[list[float], list[float], int]:
    res, caps, leds = [], [], 0
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt bringup_modules"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if not in_subckt or s.startswith("+") or s.startswith("*"):
            continue
        if re.match(r"^R", s):
            res.append(parse_si(s.split()[3]))
        elif re.match(r"^C", s):
            caps.append(parse_si(s.split()[3]))
        elif re.match(r"^D", s):
            leds += 1
    return sorted(res), sorted(caps), leds


def test_cir_passives_match_netlist(c: Circuit):
    net_r = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":R"))
    net_c = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":C"))
    net_leds = sum(1 for p in c.parts.values() if p.lib_id.endswith(":LED"))
    cir_r, cir_c, cir_leds = _cir_passives()
    assert cir_r == net_r, (len(cir_r), len(net_r))
    assert cir_c == net_c, (len(cir_c), len(net_c))
    assert cir_leds == net_leds == 10, (cir_leds, net_leds)
