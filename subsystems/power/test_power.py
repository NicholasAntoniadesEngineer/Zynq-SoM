from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.power.power as power
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "power.cir"

_CARRIER_BIND = {
    "+VIN": "+VIN_SYS",
    "+VOUT_5V_REG": "+5V_REG",
    "+VOUT_5V": "+5V",
    "+VOUT_3V3_REG": "+3V3_REG",
    "+VOUT_3V3": "+3V3",
    "+VOUT_1V8_REG": "+1V8_REG",
    "+VOUT_1V8": "+1V8",
    "GND": "GND",
    "EN_VOUT_5V": "EN_5V0",
    "EN_VOUT_3V3": "EN_3V3",
    "EN_VOUT_1V8": "EN_1V8",
}

_CIR_REFS = {"C1", "C25", "C2", "C3", "C5", "C6", "C26",
             "C7", "C29", "C8", "C30", "C10", "C11", "C12", "C13"}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return power.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _cap_nets(c: Circuit, ref: str) -> set[str]:
    return {n.name for n in (c.net_of(PinRef(ref, "1")),
                             c.net_of(PinRef(ref, "2"))) if n}


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(power.INTERFACE), externals
    carrier = {"+VIN_SYS", "+5V", "+5V_REG", "+3V3", "+3V3_REG", "+1V8",
               "+1V8_REG", "EN_5V0", "EN_3V3", "EN_1V8"}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in power.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in power.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_lm61460_faithful_dossier_symbol(c: Circuit):
    u1 = c.parts["U1"]
    assert u1.lib_id == "LM61460AANRJRR:LM61460AANRJRR", u1.lib_id
    assert not u1.lib_id.startswith("schgen:"), u1.lib_id
    assert u1.footprint == "LM61460AANRJRR:LM61460AANRJRR", u1.footprint


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"U1.5", "U2.5", "U3.4"}


def test_lm61460_heat_path_on_gnd(c: Circuit):
    for pin in ("3", "9", "11"):
        n = c.net_of(PinRef("U1", pin))
        assert n is not None and n.name == "GND", (pin, n)


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_each_stage_input_and_output_has_caps(c: Circuit):
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = _cap_nets(c, ref)
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VIN") == ["100n", "100n", "10u", "10u"]
    assert caps_to_gnd("+VOUT_5V_REG") == ["22u", "22u", "22u"]
    assert caps_to_gnd("+VOUT_5V") == ["100n", "100n", "22u", "22u"]
    assert caps_to_gnd("+VOUT_3V3_REG") == ["22u", "22u"]
    assert caps_to_gnd("+VOUT_3V3") == ["1u"]
    assert caps_to_gnd("+VOUT_1V8_REG") == ["1u"]


def _r_value(c: Circuit, ref: str) -> float:
    return parse_si(c.parts[ref].value)


def test_fb_divider_ratios_set_documented_outputs(c: Circuit):
    vout_5v = 1.0 * (1 + _r_value(c, "R1") / _r_value(c, "R2"))
    assert abs(vout_5v - 5.02) < 0.05, vout_5v
    assert _r_value(c, "R1") == 40.2e3
    vout_3v3 = 1.0 * (1 + _r_value(c, "R4") / _r_value(c, "R5"))
    assert 3.201 <= vout_3v3 <= 3.399, vout_3v3
    assert _r_value(c, "R4") == 23.2e3 and _r_value(c, "R5") == 10e3


def test_reg_side_vs_rail_side_split(c: Circuit):
    assert _cap_nets(c, "C5") == {"+VOUT_5V_REG", "GND"}
    assert "+VOUT_5V_REG" in {n.name for n in
                              (c.net_of(PinRef("R1", "1")),) if n}
    assert _cap_nets(c, "C7") == {"+VOUT_5V", "GND"}
    assert _cap_nets(c, "C8") == {"+VOUT_5V", "GND"}
    assert _cap_nets(c, "C12") == {"+VOUT_3V3", "GND"}
    assert _cap_nets(c, "C13") == {"+VOUT_1V8_REG", "GND"}
    for reg, rail in (("+VOUT_5V_REG", "+VOUT_5V"),
                      ("+VOUT_3V3_REG", "+VOUT_3V3"),
                      ("+VOUT_1V8_REG", "+VOUT_1V8")):
        assert reg in c.nets and rail in c.nets and reg != rail


def test_internal_signal_nets_kept_verbatim(c: Circuit):
    signal = {n.name for n in c.nets.values()
              if n.net_class is NetClass.SIGNAL}
    assert signal == {
        "U1_VCC", "BIAS_5V0", "RT_5V0", "BOOT_5V0", "SW_5V0", "FB_5V0",
        "CFF_5V0", "PG_5V0",
        "U2_VCC", "BIAS_3V3", "RT_3V3", "BOOT_3V3", "SW_3V3", "FB_3V3",
        "CFF_3V3", "PG_3V3",
        "PG_1V8_G", "PG_1V8_D", "PG_1V8_K"}, signal


def test_bulk_bypass_caps_have_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        rail_v = max((power.RAIL_WORST_V.get(n, 0.0)
                      for n in _cap_nets(c, ref)), default=0.0)
        if rail_v <= 0 or "GND" not in _cap_nets(c, ref):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"rail bypass caps with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    worst = power.RAIL_WORST_V
    checked_vin = False
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = _cap_nets(c, ref)
        rail_v = max((worst.get(n, 0.0) for n in nets), default=0.0)
        if rail_v <= 0 or "GND" not in nets:
            continue
        lcsc = p.fields.get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            continue
        rat = RATINGS_BY_LCSC[lcsc]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail "
            f"(<1.3x margin)")
        if "+VIN" in nets:
            checked_vin = True
    assert checked_vin, "the +VIN 21 V input caps were not exercised"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt power"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt power"))
    pins = header.split()[2:]
    assert pins == ["VIN", "VOUT_5V_REG", "VOUT_5V", "VOUT_3V3_REG",
                    "VOUT_3V3", "VOUT_1V8_REG", "VOUT_1V8", "GND"], pins
    iface = {n.lstrip("+") for n in power.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_REFS)
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)
    assert set(_cir_caps()) == _CIR_REFS


def test_cir_excludes_internal_signal_caps(c: Circuit):
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C") or ref in _CIR_REFS:
            continue
        nets = _cap_nets(c, ref)
        signal = {n for n in nets
                  if c.nets[n].net_class is NetClass.SIGNAL}
        assert signal, (ref, nets)


def test_spice_analytic_slice_runs_clean_when_bound():
    bound = power.circuit({"bind": _CARRIER_BIND})
    res = spice.extract_checks([_sheet(bound)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = power.circuit()
    bound = power.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert "SW_5V0" in bound.nets and "FB_5V0" in bound.nets
    assert bound.parts["U1"].lib_id == "LM61460AANRJRR:LM61460AANRJRR"
    assert "+5V" in bound.loads and "+VOUT_5V" not in bound.loads
    assert "+3V3" in bound.loads and "+1V8" in bound.loads


def test_bind_identity_is_noop():
    base = power.circuit()
    ident = power.circuit({"bind": {n: n for n in power.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_expects_and_notes_override_house_style():
    base = power.circuit()
    m = power.circuit({
        "expects": {"EN_VOUT_5V": "my-bringup-sheet"},
        "notes": {"draws_5v": "custom 5v note"},
    })
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("EN_VOUT_5V").expect == "my-bringup-sheet"
    assert m.loads["+VOUT_5V"][0][1] == "custom 5v note"
    assert m.loads["+VOUT_1V8"][0][1] == power.DRAWS_1V8_NOTE


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        power.circuit({"note": {"draws_5v": "X"}})


def test_bind_rejects_unknown_name():
    c = power.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_RAIL": "+5V"})


def test_bind_rejects_signal_net():
    c = power.circuit()
    assert c.nets["SW_5V0"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"SW_5V0": "SOMETHING"})


def test_bind_rejects_collision():
    c = power.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"+VOUT_5V_REG": "SHARED", "+VOUT_5V": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = power.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
