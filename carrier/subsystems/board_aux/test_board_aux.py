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

from carrier.subsystems.board_aux import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "board_aux.cir"


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


def test_is_board_aux(c: Circuit):
    assert c.name == "board_aux"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"SW1.2", "SW1.4", "SW1.6"}


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 2


def test_supply_pins_each_have_a_100n(c: Circuit):
    def caps_on(rail: str) -> int:
        n = 0
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = {x.name for x in (c.net_of(PinRef(ref, "1")),
                                      c.net_of(PinRef(ref, "2"))) if x}
            if rail in names and "GND" in names and p.value == "100n":
                n += 1
        return n
    assert caps_on("+3V3") >= 1
    assert caps_on("+3V3_SC") >= 1
    assert caps_on("+3V3_AUX") >= 1


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")
                or p.lib_id.endswith(":LED")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt board_aux"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_carrier_externals():
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt board_aux"))
    pins = header.split()[2:]
    assert pins == ["V3V3", "V3V3_AUX", "GND", "V3V3_SC", "STM32_I2C2_SCL",
                    "STM32_I2C2_SDA", "AUX_I2C_SCL", "AUX_I2C_SDA"], pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_gate_sources_the_aux_rail(c: Circuit):
    assert "U1.1" in _pins(c, "+3V3_AUX")
    assert "U1.5" in _pins(c, "+3V3")


def test_manual_enable_defaults_off(c: Circuit):
    en = _pins(c, "EN_AUX")
    assert "U1.4" in en
    assert "SW1.8" in en
    rrefs = {p.ref for p in c.nets["EN_AUX"].pins if p.ref.startswith("R")}
    assert any(r in {p.ref for p in c.nets["GND"].pins} for r in rrefs), \
        "EN_AUX has no pulldown to GND"


def test_pca9306_reference_split(c: Circuit):
    assert "U2.2" in _pins(c, "+3V3_SC")
    assert "U2.7" in _pins(c, "+3V3_AUX")


def test_pca9306_en_follows_gated_rail(c: Circuit):
    en_net = next(n for n in c.nets if "U2.8" in _pins(c, n))
    rrefs = {p.ref for p in c.nets[en_net].pins if p.ref.startswith("R")}
    assert rrefs, "PCA9306 EN has no pull resistor"
    pulled_to_aux = any(r in {p.ref for p in c.nets["+3V3_AUX"].pins}
                        for r in rrefs)
    assert pulled_to_aux, "PCA9306 EN is not pulled to +3V3_AUX"


def test_aux_bus_pullups_live_here(c: Circuit):
    for line in ("AUX_I2C_SCL", "AUX_I2C_SDA"):
        rrefs = {p.ref for p in c.nets[line].pins if p.ref.startswith("R")}
        pulled = [r for r in rrefs
                  if r in {p.ref for p in c.nets["+3V3_AUX"].pins}
                  and c.parts[r].value == "4k7"]
        assert pulled, f"{line} has no 4k7 pull-up to +3V3_AUX"


def test_both_i2c_busses_typed(c: Circuit):
    assert c.port_type_of("STM32_I2C2_SCL").bus == "STM32_I2C2"
    assert c.port_type_of("STM32_I2C2_SDA").bus == "STM32_I2C2"
    assert c.port_type_of("AUX_I2C_SCL").bus == "AUX_I2C"
    assert c.port_type_of("AUX_I2C_SDA").bus == "AUX_I2C"
    for p in ("STM32_I2C2_SCL", "STM32_I2C2_SDA", "AUX_I2C_SCL", "AUX_I2C_SDA"):
        assert c.port_type_of(p).kind == "i2c"
        assert c.port_type_of(p).speed_hz == 400_000
