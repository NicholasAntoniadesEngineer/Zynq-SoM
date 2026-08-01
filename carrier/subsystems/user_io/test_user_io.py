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

import carrier.subsystems.user_io.user_io as user_io

HERE = Path(__file__).resolve().parent
CIR = HERE / "user_io.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return user_io.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins, sorted(str(p) for p in c.nc_pins)


def test_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3_USER_LED"] is NetClass.POWER
    assert cls["+3V3"] is NetClass.POWER
    assert cls["GND"] is NetClass.GROUND


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert not r.reset, r.reset


def _leds(c: Circuit) -> list[tuple[str, str]]:
    return [(ref, p.value) for ref, p in c.parts.items()
            if p.lib_id == "Device:LED"]


def test_four_leds_distinct_colors_on_gated_rail(c: Circuit):
    leds = dict(_leds(c))
    assert len(leds) == 4
    assert sorted(leds.values()) == ["blue", "green", "red", "white"]
    rail = c.nets["+3V3_USER_LED"]
    anode_pins = {str(p) for p in rail.pins}
    for ref in leds:
        assert f"{ref}.2" in anode_pins, f"{ref} anode not on +3V3_USER_LED"


def test_led_series_R_is_per_color(c: Circuit):
    """Green/blue/white need 200R or their higher Vf leaves them invisible at 3.3 V."""
    color_to_rval: dict[str, str] = {}
    for ref, p in c.parts.items():
        if p.lib_id != "Device:LED":
            continue
        k_net = c.net_of(PinRef(ref, "1"))
        assert k_net is not None and k_net.name.endswith("_K")
        rrefs = {pr.ref for pr in k_net.pins if pr.ref != ref}
        (rref,) = rrefs
        color_to_rval[p.value] = c.parts[rref].value
    assert color_to_rval["red"] == "1k"
    assert color_to_rval["green"] == "200R"
    assert color_to_rval["blue"] == "200R"
    assert color_to_rval["white"] == "200R"


def test_four_buttons_pullup_to_ungated_3v3_contacts_to_gnd(c: Circuit):
    """Tact switches are use_part, so buttons are matched by their 4-contact GND footing."""
    sws = [ref for ref, p in c.parts.items() if p.lib_id.endswith("TS-1187A-B-A-B")
           or "TS-1187A" in (p.lib_id + p.value)]
    gnd_pins = {str(p) for p in c.nets["GND"].pins}
    pu_rail_pins = {str(p) for p in c.nets["+3V3"].pins}
    n_buttons = 0
    for ref, p in c.parts.items():
        if f"{ref}.3" in gnd_pins and f"{ref}.4" in gnd_pins:
            n_buttons += 1
    assert n_buttons == 4, f"expected 4 buttons grounding contacts 3/4, got {n_buttons}"
    pulls = [ref for ref, p in c.parts.items()
             if p.lib_id == "Device:R" and p.value == "10k"]
    assert len(pulls) == 4
    for rref in pulls:
        assert f"{rref}.1" in pu_rail_pins, f"{rref} pull not on +3V3"


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id == "Device:R"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_passives() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt user_io"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id == "Device:R" or p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_draws_on_both_rails(c: Circuit):
    assert "+3V3_USER_LED" in c.loads
    assert "+3V3" in c.loads
