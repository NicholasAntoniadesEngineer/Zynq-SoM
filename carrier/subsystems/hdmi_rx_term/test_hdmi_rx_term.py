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

import carrier.subsystems.hdmi_rx_term.hdmi_rx_term as hdmi_rx_term

HERE = Path(__file__).resolve().parent
CIR = HERE / "hdmi_rx_term.cir"

TMDS_LINES = (
    "HDMI_RX_D2_P", "HDMI_RX_D2_N",
    "HDMI_RX_D1_P", "HDMI_RX_D1_N",
    "HDMI_RX_D0_P", "HDMI_RX_D0_N",
    "HDMI_RX_CLK_P", "HDMI_RX_CLK_N",
)


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return hdmi_rx_term.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins, sorted(str(p) for p in c.nc_pins)


def test_ports_and_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3"] is NetClass.POWER
    assert cls["GND"] is NetClass.GROUND
    for line in TMDS_LINES:
        assert cls[line] is NetClass.PORT, (line, cls.get(line))


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_eight_terminations_each_49R9_to_avcc(c: Circuit):
    avcc_pins = {str(p) for p in c.nets["+3V3"].pins}
    term_value_by_line: dict[str, str] = {}
    for ref, p in c.parts.items():
        if p.lib_id != "Device:R":
            continue
        n1 = c.net_of(PinRef(ref, "1"))
        n2 = c.net_of(PinRef(ref, "2"))
        names = {n.name for n in (n1, n2) if n}
        assert f"{ref}.2" in avcc_pins, f"{ref} not terminated to AVCC(+3V3)"
        line = (names - {"+3V3"}).pop()
        assert line in TMDS_LINES, f"{ref} terminates a non-TMDS net {line!r}"
        term_value_by_line[line] = p.value
    assert set(term_value_by_line) == set(TMDS_LINES), term_value_by_line
    assert set(term_value_by_line.values()) == {"49.9R"}, term_value_by_line
    assert sum(1 for p in c.parts.values() if p.lib_id == "Device:R") == 8


def test_avcc_local_bypass_present(c: Circuit):
    caps_to_gnd = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        if "+3V3" in names and "GND" in names:
            caps_to_gnd.append(p.value)
    assert sorted(caps_to_gnd) == ["100n", "1u"], caps_to_gnd


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
        if s.lower().startswith(".subckt hdmi_rx_term"):
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


def test_draws_on_avcc(c: Circuit):
    assert "+3V3" in c.loads
    total = sum(a for a, _ in c.loads["+3V3"])
    assert total == pytest.approx(0.064), total
