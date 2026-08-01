from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si

import carrier.subsystems.bringup_en_modules.bringup_en_modules as bem

HERE = Path(__file__).resolve().parent
CIR = HERE / "bringup_en_modules.cir"

EN_NETS = ("EN_HDMI_TX", "EN_HDMI_RX", "EN_LCD", "EN_CAM", "EN_SD", "EN_USB",
           "EN_PMOD", "EN_USER_LED", "EN_LCD_BL", "EN_HDMI_TX_5V", "EN_LCD_5V")
B_PULLED = ("BU_OVR_HDMI_TX", "BU_OVR_HDMI_RX", "BU_OVR_LCD", "BU_OVR_CAM",
            "BU_OVR_SD", "BU_OVR_USB", "BU_OVR_PMOD", "BU_OVR_USER_LED",
            "BU_OVR_HDMI_TX_5V", "BU_OVR_LCD_5V")
B_NO_PULL = "BU_OVR_LCD_BL"
A_NETS = ("BU_DIP_HDMI_TX", "BU_DIP_HDMI_RX", "BU_DIP_LCD", "BU_DIP_CAM",
          "BU_DIP_SD", "BU_DIP_USB", "BU_DIP_PMOD", "BU_DIP_USER_LED",
          "BU_DIP_SPARE", "BU_DIP_HDMI_TX_5V", "BU_DIP_LCD_5V")


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return bem.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _resistors_on(c: Circuit, net: str):
    out = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":R"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if net in nets:
            out.append((p.value, nets))
    return out


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins


def test_eleven_module_cells_present(c: Circuit):
    gates = [r for r, p in c.parts.items()
             if r.startswith("U") and p.value == "SN74LVC1G08"]
    assert len(gates) == 11, gates


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3_SC"] is NetClass.POWER
    assert cls["GND"] is NetClass.GROUND
    for en in EN_NETS:
        assert cls[en] is NetClass.PORT, (en, cls.get(en))


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.strap, r.strap
    assert not r.ep, r.ep
    assert r.checked.get("decap", 0) == 11


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_each_A_input_has_a_100k_pulldown_to_gnd(c: Circuit):
    for a in A_NETS:
        pulls = [v for v, nets in _resistors_on(c, a) if "GND" in nets]
        assert pulls == ["100k"], (a, pulls)


def test_pulled_B_inputs_have_a_100k_pullup_to_3v3sc(c: Circuit):
    for b in B_PULLED:
        pulls = [v for v, nets in _resistors_on(c, b) if "+3V3_SC" in nets]
        assert pulls == ["100k"], (b, pulls)


def test_spare_lcd_bl_has_no_pullup_here(c: Circuit):
    """bringup_rails P10 pulls this B down; a pull-up here would fight it."""
    pulls = [v for v, nets in _resistors_on(c, B_NO_PULL)
             if "+3V3_SC" in nets]
    assert pulls == [], (B_NO_PULL, pulls)


def test_pullup_count_is_ten(c: Circuit):
    rs = [p for p in c.parts.values() if p.lib_id.endswith(":R")]
    assert len(rs) == 21, len(rs)
    to_sc = sum(1 for ref, p in c.parts.items() if p.lib_id.endswith(":R")
                and "+3V3_SC" in {n.name for n in
                                  (c.net_of(PinRef(ref, "1")),
                                   c.net_of(PinRef(ref, "2"))) if n})
    assert to_sc == 10, to_sc


def test_every_enable_is_probeable(c: Circuit):
    tp_nets = set()
    for ref, p in c.parts.items():
        if not ref.startswith("TP"):
            continue
        n = c.net_of(PinRef(ref, "1"))
        if n:
            tp_nets.add(n.name)
    for en in EN_NETS:
        assert en in tp_nets, (en, sorted(tp_nets))


def test_power_draw_declared(c: Circuit):
    assert "+3V3_SC" in c.loads


def _cir_passives() -> tuple[list[float], list[float]]:
    res, caps = [], []
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt bringup_en_modules"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if not in_subckt or s.startswith("+"):
            continue
        if re.match(r"^R", s):
            res.append(parse_si(s.split()[3]))
        elif re.match(r"^C", s):
            caps.append(parse_si(s.split()[3]))
    return sorted(res), sorted(caps)


def test_cir_passives_match_netlist(c: Circuit):
    net_r = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":R"))
    net_c = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":C"))
    cir_r, cir_c = _cir_passives()
    assert cir_r == net_r, (len(cir_r), len(net_r))
    assert cir_c == net_c, (len(cir_c), len(net_c))
