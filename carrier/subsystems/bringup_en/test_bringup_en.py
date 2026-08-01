from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si

import carrier.subsystems.bringup_en.bringup_en as bringup_en

HERE = Path(__file__).resolve().parent
CIR = HERE / "bringup_en.cir"

EN_NETS = ("EN_5V0", "EN_3V3", "EN_1V8")
B_NETS = ("STM32_RAIL_EN_5V0", "STM32_RAIL_EN_3V3", "STM32_RAIL_EN_1V8")
A_NETS = ("BU_DIP_5V0", "BU_DIP_3V3", "BU_DIP_1V8")


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return bringup_en.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins


def test_three_rail_cells_present(c: Circuit):
    gates = [r for r, p in c.parts.items()
             if r.startswith("U") and p.value == "SN74LVC1G08"]
    assert len(gates) == 3, gates


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
    assert r.checked.get("decap", 0) == 3


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def _resistors_on(c: Circuit, net: str) -> list[str]:
    out = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":R"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if net in nets:
            out.append((p.value, nets))
    return out


def test_each_A_input_has_a_100k_pulldown_to_gnd(c: Circuit):
    for a in A_NETS:
        pulls = [(v, nets) for v, nets in _resistors_on(c, a)
                 if "GND" in nets]
        assert [v for v, _ in pulls] == ["100k"], (a, pulls)


def test_each_B_input_has_a_100k_pullup_to_3v3sc(c: Circuit):
    for b in B_NETS:
        pulls = [(v, nets) for v, nets in _resistors_on(c, b)
                 if "+3V3_SC" in nets]
        assert [v for v, _ in pulls] == ["100k"], (b, pulls)


def test_every_enable_is_probeable(c: Circuit):
    tp_nets = set()
    for ref, p in c.parts.items():
        if "TestPoint" not in p.lib_id and "TP" not in ref:
            continue
        for pr in (PinRef(ref, "1"),):
            n = c.net_of(pr)
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
        if s.lower().startswith(".subckt bringup_en"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if not in_subckt:
            continue
        if re.match(r"^R", s):
            res.append(parse_si(s.split()[3]))
        elif re.match(r"^C", s):
            caps.append(parse_si(s.split()[3]))
    return sorted(res), sorted(caps)


def test_cir_subckt_pins_are_the_rail_and_cell_nets():
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt bringup_en"))
    pins = header.split()[2:]
    assert pins[:2] == ["VDD", "GND"]
    assert len(pins) == 8


def test_cir_passives_match_netlist(c: Circuit):
    net_r = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":R"))
    net_c = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":C"))
    cir_r, cir_c = _cir_passives()
    assert cir_r == net_r, (cir_r, net_r)
    assert cir_c == net_c, (cir_c, net_c)
