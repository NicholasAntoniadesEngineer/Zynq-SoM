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

from carrier.subsystems.power_som import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "power_som.cir"

LM61460_VREF_V = 1.0
VOUT_NOM_MIN_V, VOUT_NOM_MAX_V = 4.6, 4.7
SOM_VIN_MIN_V, SOM_VIN_MAX_V = 4.2, 5.0


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


def test_is_power_som(c: Circuit):
    assert c.name == "power_som"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"U4.5"}


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1


def test_lm61460_heat_path_on_gnd(c: Circuit):
    """The VQFN-HR part has no centre EP: PGND1/PGND2/AGND are the heat path."""
    gnd = _pins(c, "GND")
    for pin in ("3", "9", "11"):
        assert f"U4.{pin}" in gnd, pin


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


def test_fb_divider_sets_documented_output(c: Circuit):
    rtop = parse_si(c.parts["R14"].value)
    rbot = parse_si(c.parts["R15"].value)
    assert rtop == parse_si("47.5k")
    assert rbot == parse_si("13k")
    vout = LM61460_VREF_V * (1 + rtop / rbot)
    assert VOUT_NOM_MIN_V < vout < VOUT_NOM_MAX_V, vout
    assert SOM_VIN_MIN_V <= vout <= SOM_VIN_MAX_V, vout
    fb = _pins(c, "FB_5V_SOM")
    assert {"U4.4", "R14.2", "R15.1", "R19.2"} <= fb, fb


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt power_som"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


_CIR_CAP_REFS = {"C14", "C25", "C15", "C16", "C18", "C19"}


def test_cir_subckt_pins_are_the_carrier_externals():
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt power_som"))
    pins = header.split()[2:]
    assert pins == ["+VIN_SYS", "+5V_SOM", "GND"], pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_CAP_REFS)
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_pwr1_en_clamp_topology(c: Circuit):
    en = _pins(c, "EN_5V_SOM")
    assert {"U4.7", "R12.2", "D5.1", "C20.1"} <= en, en
    assert "R12.1" in _pins(c, "+VIN_SYS")
    assert {"D5.2", "C20.2"} <= _pins(c, "GND")
    assert c.parts["D5"].value == "MMSZ5231B"
    assert c.parts["R12"].value == "10k"


def test_en_is_always_on_no_bringup_port(c: Circuit):
    assert not getattr(c, "ports", {})
    assert "U4.7" in _pins(c, "EN_5V_SOM")


def test_boot_rboot_short_and_bias_tie(c: Circuit):
    boot = _pins(c, "BOOT_5V_SOM")
    assert {"U4.14", "U4.13", "C17.1"} <= boot, boot
    assert "R17.1" in _pins(c, "+5V_SOM")
    bias = _pins(c, "BIAS_5V_SOM")
    assert {"U4.1", "R17.2", "C23.1"} <= bias, bias


def test_input_and_output_bulk_present(c: Circuit):
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            on = {n for n in c.nets if {f"{ref}.1", f"{ref}.2"} & _pins(c, n)}
            if on == {rail, "GND"}:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VIN_SYS") == ["100n", "100n", "10u", "10u"]
    assert caps_to_gnd("+5V_SOM") == ["22u", "22u"]


def test_u4_is_the_lm61460_ep_buck(c: Circuit):
    u4 = c.parts["U4"]
    assert u4.lib_id.split(":")[-1] == "LM61460AANRJRR"
    assert not u4.lib_id.startswith("schgen:"), u4.lib_id
    assert (u4.fields or {}).get("LCSC") == "C2864505"
