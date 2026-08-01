from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.lcd.lcd as lcd
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "lcd.cir"

RAIL_WORST_V = {"+VBOOST_IN": 5.0, "+VDD_LCD": 3.3, "+VDD_TP_CLAMP": 3.3,
                "GND": 0.0}
VLED_OVP_CLAMP_V = 30.0

SIGNAL_NODES = ("LCD_BL_SW", "LCD_VLED_P", "LCD_VLED_N", "LCD_PCLK_PANEL",
                "CTP_SDA_FFC", "CTP_SCL_FFC")

_PANEL_PORTS = (
    [f"LCD_R{i}" for i in range(8)] + [f"LCD_G{i}" for i in range(8)]
    + [f"LCD_B{i}" for i in range(8)]
    + ["LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE", "LCD_PCLK"])
_CARRIER_BIND = {
    "+VBOOST_IN": "+5V_LCD", "+VDD_LCD": "+3V3_LCD",
    "+VDD_TP_CLAMP": "+3V3", "GND": "GND",
    **{p: p for p in _PANEL_PORTS},
    "BL_PWM": "LCD_BL_PWM",
    "TP_SDA": "LCD_CTP_SDA", "TP_SCL": "LCD_CTP_SCL",
    "TP_RST": "LCD_CTP_RST", "TP_INT": "LCD_CTP_INT",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return lcd.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _caps_to_gnd(c: Circuit, rail: str) -> list[str]:
    out = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        if rail in names and "GND" in names:
            out.append(p.value)
    return sorted(out)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(lcd.INTERFACE), externals
    carrier_real = set(_CARRIER_BIND.values()) - {"GND"} | {"LCD_CTP_INT"}
    leaked = externals & {r for r in carrier_real
                          if r not in lcd.INTERFACE}
    assert not leaked, leaked
    assert "LCD_CTP_SDA" not in externals and "+5V_LCD" not in externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in lcd.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in lcd.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_internal_signal_nodes_kept_verbatim(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for node in SIGNAL_NODES:
        assert cls.get(node) is NetClass.SIGNAL, (node, cls.get(node))
        assert node not in lcd.INTERFACE, node


def test_touch_i2c_typed(c: Circuit):
    assert c.port_type_of("TP_SDA").kind == "i2c"
    assert c.port_type_of("TP_SDA").role == "sda"
    assert c.port_type_of("TP_SCL").role == "scl"
    assert c.port_type_of("TP_SDA").bus == c.port_type_of("TP_SCL").bus
    assert c.port_type_of("TP_SDA").bus == lcd.I2C_BUS


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"J1.35", "J1.41", "J1.42"}


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert not r.i2c, r.i2c
    assert r.checked.get("i2c", 0) >= 2
    assert r.checked.get("reset", 0) >= 1


def test_touch_i2c_pullups_on_gated_rail(c: Circuit):
    for ref, val, leg in (("R2", "4k7", "TP_SDA"), ("R3", "4k7", "TP_SCL"),
                          ("R6", "10k", "LCD_DISP")):
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        assert c.parts[ref].value == val, ref
        assert names == {"+VDD_LCD", leg}, (ref, names)


def test_default_state_pulls(c: Circuit):
    for ref, leg in (("R5", "TP_RST"), ("R4", "BL_PWM")):
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        assert c.parts[ref].value == "100k", ref
        assert names == {"GND", leg}, (ref, names)


def test_boost_topology(c: Circuit):
    assert "10u" in _caps_to_gnd(c, "+VBOOST_IN")
    assert _caps_to_gnd(c, "LCD_VLED_P") == ["2.2u"]
    r1 = {n.name for n in (c.net_of(PinRef("R1", "1")),
                           c.net_of(PinRef("R1", "2"))) if n}
    assert c.parts["R1"].value == "1.5R" and r1 == {"LCD_VLED_N", "GND"}, r1
    l1 = {n.name for n in (c.net_of(PinRef("L1", "1")),
                           c.net_of(PinRef("L1", "2"))) if n}
    assert l1 == {"+VBOOST_IN", "LCD_BL_SW"}, l1
    d1 = {n.name for n in (c.net_of(PinRef("D1", "1")),
                           c.net_of(PinRef("D1", "2"))) if n}
    assert d1 == {"LCD_BL_SW", "LCD_VLED_P"}, d1


def test_pclk_source_series_damping(c: Circuit):
    r7 = {n.name for n in (c.net_of(PinRef("R7", "1")),
                           c.net_of(PinRef("R7", "2"))) if n}
    assert c.parts["R7"].value == "22R" and r7 == {"LCD_PCLK", "LCD_PCLK_PANEL"}


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_rail_caps_voltage_derated(c: Circuit):
    worst = RAIL_WORST_V
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = [c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))]
        rail_v = max((worst.get(n.name, 0.0) for n in nets if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail "
            f"(<1.3x margin)")


def test_boost_output_cap_clears_ovp_clamp(c: Circuit):
    c2 = next(p for ref, p in c.parts.items()
              if p.lib_id.endswith(":C")
              and "LCD_VLED_P" in {n.name for n in
                                   (c.net_of(PinRef(ref, "1")),
                                    c.net_of(PinRef(ref, "2"))) if n})
    assert RATINGS_BY_LCSC[c2.fields["LCSC"]].v_max >= VLED_OVP_CLAMP_V
    assert "C2" in c.part_rule_waivers


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_passives() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt lcd"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[-1])
    return out


def test_cir_subckt_pins_are_abstract_interface():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt lcd"))
    pins = header.split()[2:]
    assert pins == ["VBOOST_IN", "VDD_LCD", "VDD_TP_CLAMP", "LCD_DISP",
                    "TP_SDA", "TP_SCL", "TP_RST", "LCD_PCLK", "BL_PWM",
                    "GND"], pins
    iface = {n.lstrip("+") for n in lcd.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C") or p.lib_id.endswith(":R"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = lcd.circuit()
    bound = lcd.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    for node in SIGNAL_NODES:
        assert node in bound.nets, node
    assert bound.port_type_of("LCD_CTP_SDA").role == "sda"
    assert bound.port_type_of("LCD_CTP_SCL").bus == lcd.I2C_BUS
    assert "+3V3_LCD" in bound.loads and "+VDD_LCD" not in bound.loads
    assert "+5V_LCD" in bound.loads and "+VBOOST_IN" not in bound.loads
    tp_vals = {p.value for r, p in bound.parts.items()
               if p.lib_id == bound.TP_LIB_ID}
    assert "+5V_LCD" in tp_vals and "LCD_CTP_SDA" in tp_vals


def test_bind_identity_is_noop():
    base = lcd.circuit()
    ident = lcd.circuit({"bind": {n: n for n in lcd.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    base = lcd.circuit()
    m = lcd.circuit({"buses": {"i2c": "MY_TOUCH_I2C"},
                     "notes": {"draws_lcd": "lcd note",
                               "draws_boost": "boost note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("TP_SDA").bus == "MY_TOUCH_I2C"
    assert m.port_type_of("TP_SCL").bus == "MY_TOUCH_I2C"
    assert m.loads["+VDD_LCD"][0][1] == "lcd note"
    assert m.loads["+VBOOST_IN"][0][1] == "boost note"


def test_meta_expects_attaches_port_deferral():
    m = lcd.circuit({"expects": {"LCD_R0": "som_j3 (bank 34)",
                                 "TP_SDA": "som_j2 (bank 13)"}})
    assert m.port_type_of("LCD_R0").expect == "som_j3 (bank 34)"
    assert m.port_type_of("TP_SDA").expect == "som_j2 (bank 13)"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        lcd.circuit({"bus": {"i2c": "X"}})


def test_bind_rejects_unknown_name():
    c = lcd.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_LCD"})


def test_bind_rejects_signal_net():
    c = lcd.circuit()
    assert c.nets["LCD_BL_SW"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"LCD_BL_SW": "SOMETHING"})


def test_bind_rejects_collision():
    c = lcd.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"TP_SDA": "SHARED", "TP_SCL": "SHARED"})


def test_bound_circuit_passes_local_design_rules(lib: Library):
    bound = lcd.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap or r.i2c), r.findings
