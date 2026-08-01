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

import carrier.subsystems.fmc.fmc as fmc

HERE = Path(__file__).resolve().parent
CIR = HERE / "fmc.cir"

POPULATED_STEMS = tuple(stem for stem, _, _ in fmc.HEADER_PAIRS)


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return fmc.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _pin_net(c: Circuit, pin: str) -> str | None:
    ref, num = pin.split(".")
    n = c.net_of(PinRef(ref, num))
    return n.name if n else None


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert "U1.4" in {str(p) for p in c.nc_pins}


def test_all_forty_header_pins_assigned(c: Circuit):
    for pin in range(1, 41):
        assert _pin_net(c, f"J1.{pin}") is not None, f"header pin {pin} unconnected"


def test_header_is_stock_2x20(c: Circuit):
    j1 = c.parts["J1"]
    assert j1.lib_id == fmc.HDR_SYM
    assert "PinHeader_2x20" in (j1.footprint or "")


def test_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3"] is NetClass.POWER
    assert cls["+2V5_VADJ"] is NetClass.POWER
    assert cls["GND"] is NetClass.GROUND


def test_power_and_ground_pins(c: Circuit):
    assert _pin_net(c, "J1.1") == "+3V3"
    assert _pin_net(c, "J1.2") == "+2V5_VADJ"
    for g in fmc.GND_PINS:
        assert _pin_net(c, f"J1.{g}") == "GND", f"pin {g} should be GND"
    assert len(fmc.GND_PINS) == 10


def test_each_pair_on_its_documented_pins(c: Circuit):
    for stem, p_pin, n_pin in fmc.HEADER_PAIRS:
        assert _pin_net(c, f"J1.{p_pin}") == f"{stem}_P", (stem, p_pin)
        assert _pin_net(c, f"J1.{n_pin}") == f"{stem}_N", (stem, n_pin)


def test_vadj_ldo_present_in_out_and_ep_to_gnd(c: Circuit):
    ldos = [ref for ref, p in c.parts.items()
            if p.lib_id.endswith("TLV75725PDYDR")]
    assert ldos, "TLV75725 VADJ LDO missing"
    (u1,) = ldos
    assert _pin_net(c, f"{u1}.1") == "+3V3"
    assert _pin_net(c, f"{u1}.2") == "GND"
    assert _pin_net(c, f"{u1}.3") == "+3V3"
    assert _pin_net(c, f"{u1}.5") == "+2V5_VADJ"
    assert _pin_net(c, f"{u1}.6") == "GND"

    def caps_on(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                      c.net_of(PinRef(ref, "2"))) if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert "1u" in caps_on("+3V3") or "10u" in caps_on("+3V3")
    assert any(v in caps_on("+2V5_VADJ") for v in ("1u", "10u", "100n"))


def test_vadj_rail_has_a_testpoint(c: Circuit):
    tp_nets = {p.value for ref, p in c.parts.items() if p.lib_id == c.TP_LIB_ID}
    assert "+2V5_VADJ" in tp_nets, tp_nets


def test_fourteen_la_clk_diff_pairs_typed_100ohm(c: Circuit):
    for stem in POPULATED_STEMS:
        pn, nn = f"{stem}_P", f"{stem}_N"
        assert pn in c.nets and nn in c.nets, stem
        pt = c.port_type_of(pn)
        assert pt.kind == "diff_pair", (stem, pt.kind)
        assert pt.pair_with == nn, (stem, pt.pair_with)
        assert pt.impedance == 100, (stem, pt.impedance)
    assert len(POPULATED_STEMS) == 14


def test_design_rules_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("ep", 0) >= 1
    assert not r.findings, r.findings


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id != "Device:R" and not p.lib_id.endswith(":C"):
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
        if s.lower().startswith(".subckt fmc"):
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


def test_draws_on_3v3_and_vadj(c: Circuit):
    assert "+3V3" in c.loads
    assert "+2V5_VADJ" in c.loads
