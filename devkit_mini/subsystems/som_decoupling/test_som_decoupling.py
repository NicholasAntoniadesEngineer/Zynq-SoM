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

import devkit_mini.subsystems.som_decoupling.som_decoupling as som_decoupling

HERE = Path(__file__).resolve().parent
CIR = HERE / "som_decoupling.cir"

RAILS = ("+5V_SOM", "+3V3", "+3V3_SC")


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return som_decoupling.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins, sorted(str(p) for p in c.nc_pins)


def test_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in RAILS:
        assert cls[rail] is NetClass.POWER, (rail, cls.get(rail))
    assert cls["GND"] is NetClass.GROUND


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_each_rail_has_2x22u_plus_4x100n_to_gnd(c: Circuit):
    per_rail: dict[str, list[str]] = {r: [] for r in RAILS}
    for ref, p in c.parts.items():
        assert p.lib_id.endswith(":C"), f"{ref} is not a cap ({p.lib_id})"
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        assert "GND" in names, f"{ref} has no GND foot ({names})"
        rail = (names - {"GND"}).pop()
        assert rail in RAILS, f"{ref} bypasses a non-SoM rail {rail!r}"
        per_rail[rail].append(p.value)
    for rail in RAILS:
        assert sorted(per_rail[rail]) == ["100n", "100n", "100n", "100n",
                                          "22u", "22u"], (rail, per_rail[rail])
    assert sum(len(v) for v in per_rail.values()) == 18


def test_every_bom_cap_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"caps with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> list[float]:
    out: list[float] = []
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt som_decoupling"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            out.append(parse_si(s.split()[3]))
    return out


def test_cir_caps_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for p in c.parts.values())
    assert sorted(_cir_caps()) == netlist, (sorted(_cir_caps()), netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors
