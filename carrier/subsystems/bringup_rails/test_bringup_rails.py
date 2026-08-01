from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si

import carrier.subsystems.bringup_rails.bringup_rails as br

HERE = Path(__file__).resolve().parent
CIR = HERE / "bringup_rails.cir"

I2C_NETS = ("STM32_I2C2_SCL", "STM32_I2C2_SDA")
DONT_FLOAT_PULLDOWNS = ("BU_OVR_LCD_BL", "BU_P16", "BU_P17")
BUTTON_NETS = ("PL_BTN0", "PL_BTN1")


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return br.circuit()


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
    assert {str(p) for p in c.nc_pins} == {"SW6.4", "SW6.6"}


def test_three_dip_switches_present(c: Circuit):
    sws = {ref: p.value for ref, p in c.parts.items()
           if ref in ("SW1", "SW2", "SW6")}
    assert sws == {"SW1": "DSHP04TSGER", "SW2": "DSHP08TSGER",
                   "SW6": "DSHP04TSGER"}, sws


def _dip_column_pairs(mpn: str):
    """DSHP04 numbers its bottom row 8..5, DSHP08 numbers it 9..16 — read the pads."""
    import collections
    root = HERE.parents[2]
    s = (root / "parts" / mpn / f"{mpn}.kicad_mod").read_text()
    cols: dict[float, dict] = collections.defaultdict(dict)
    for blk in re.split(r"\n\s*\(pad\b", s)[1:]:
        num = re.search(r'^\s*"([^"]+)"', blk)
        at = re.search(r"\(at\s+([-0-9.]+)\s+([-0-9.]+)", blk)
        if not (num and at):
            continue
        x, y = round(float(at.group(1)), 2), float(at.group(2))
        cols[x]["top" if y > 0 else "bot"] = num.group(1)
    return [(d["top"], d["bot"]) for d in cols.values()
            if "top" in d and "bot" in d]


def test_sw2_dip_bridges_3v3_to_one_unique_enable_each(c: Circuit):
    """A shorted DIP map once passed DRC, ERC and netlist-equivalence (2026-06-19)."""
    seen = set()
    pairs = _dip_column_pairs("DSHP08TSGER")
    assert len(pairs) == 8, pairs
    for top, bot in pairs:
        nets = {n.name for n in (c.net_of(PinRef("SW2", top)),
                                 c.net_of(PinRef("SW2", bot))) if n}
        assert "+3V3_SC" in nets, f"SW2 rocker ({top},{bot}) misses +3V3_SC: {nets}"
        sig = nets - {"+3V3_SC"}
        assert len(sig) == 1, f"SW2 rocker ({top},{bot}) must bridge ONE net: {nets}"
        en = sig.pop()
        assert en.startswith("BU_DIP_"), f"SW2 ({top},{bot}) signal {en!r} not an enable"
        assert en not in seen, f"SW2 enable {en!r} wired on two rockers (short)"
        seen.add(en)
    assert len(seen) == 8, seen


def test_sw1_dip_bridges_3v3_to_one_unique_enable_each(c: Circuit):
    seen = set()
    for top, bot in _dip_column_pairs("DSHP04TSGER"):
        nets = {n.name for n in (c.net_of(PinRef("SW1", top)),
                                 c.net_of(PinRef("SW1", bot))) if n}
        assert "+3V3_SC" in nets and len(nets - {"+3V3_SC"}) == 1, (top, bot, nets)
        en = (nets - {"+3V3_SC"}).pop()
        assert en.startswith("BU_DIP_") and en not in seen, (top, bot, en)
        seen.add(en)
    assert len(seen) == 4, seen


def test_tca9535_expander_present(c: Circuit):
    assert "U1" in c.parts and "TCA9535" in c.parts["U1"].value


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3_SC"] is NetClass.POWER
    assert cls["+3V3"] is NetClass.POWER
    assert cls["GND"] is NetClass.GROUND
    for net in I2C_NETS + ("SC_INT_N", "STM32_NRST", "PUDC_34"):
        assert cls[net] is NetClass.PORT, (net, cls.get(net))


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.i2c, r.i2c
    assert not r.reset, r.reset
    assert not r.strap, r.strap
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert r.checked.get("i2c", 0) >= 1
    assert r.checked.get("reset", 0) >= 1


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_shared_i2c_bus_has_4k7_pullups_to_3v3sc(c: Circuit):
    for net in I2C_NETS:
        pulls = [v for v, nets in _resistors_on(c, net) if "+3V3_SC" in nets]
        assert pulls == ["4k7"], (net, pulls)


def test_single_10k_pullup_owns_the_wire_or_interrupt(c: Circuit):
    pulls = [v for v, nets in _resistors_on(c, "SC_INT_N") if "+3V3_SC" in nets]
    assert pulls == ["10k"], pulls


def test_spare_expander_ports_dont_float(c: Circuit):
    for net in DONT_FLOAT_PULLDOWNS:
        pulls = [v for v, nets in _resistors_on(c, net) if "GND" in nets]
        assert pulls == ["100k"], (net, pulls)


def test_user_buttons_have_10k_pullups_to_3v3(c: Circuit):
    for net in BUTTON_NETS:
        pulls = [v for v, nets in _resistors_on(c, net) if "+3V3" in nets]
        assert pulls == ["10k"], (net, pulls)


def test_pudc_strap_is_10k_to_gnd(c: Circuit):
    """PUDC held LOW during config is what enables the Zynq internal pull-ups."""
    pulls = [v for v, nets in _resistors_on(c, "PUDC_34") if "GND" in nets]
    assert pulls == ["10k"], pulls


def test_sc_rail_and_i2c_bus_are_probeable(c: Circuit):
    tp_nets = set()
    for ref, p in c.parts.items():
        if not ref.startswith("TP"):
            continue
        n = c.net_of(PinRef(ref, "1"))
        if n:
            tp_nets.add(n.name)
    for net in ("+3V3_SC",) + I2C_NETS:
        assert net in tp_nets, (net, sorted(tp_nets))


def test_power_draw_declared(c: Circuit):
    assert "+3V3_SC" in c.loads
    assert "+3V3" in c.loads


def _cir_passives() -> tuple[list[float], list[float]]:
    res, caps = [], []
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt bringup_rails"):
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
    return sorted(res), sorted(caps)


def test_cir_passives_match_netlist(c: Circuit):
    net_r = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":R"))
    net_c = sorted(parse_si(p.value) for ref, p in c.parts.items()
                   if p.lib_id.endswith(":C"))
    cir_r, cir_c = _cir_passives()
    assert cir_r == net_r, (cir_r, net_r)
    assert cir_c == net_c, (cir_c, net_c)
