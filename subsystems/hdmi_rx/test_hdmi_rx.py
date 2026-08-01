from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.hdmi_rx.hdmi_rx as hdmi_rx
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "hdmi_rx.cir"

_CARRIER_BIND = {
    "+VDD_LOGIC": "+3V3_HDMI_RX",
    "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
    "TMDS_RX_D2_P": "HDMI_RX_D2_P", "TMDS_RX_D2_N": "HDMI_RX_D2_N",
    "TMDS_RX_D1_P": "HDMI_RX_D1_P", "TMDS_RX_D1_N": "HDMI_RX_D1_N",
    "TMDS_RX_D0_P": "HDMI_RX_D0_P", "TMDS_RX_D0_N": "HDMI_RX_D0_N",
    "TMDS_RX_CLK_P": "HDMI_RX_CLK_P", "TMDS_RX_CLK_N": "HDMI_RX_CLK_N",
    "HDMI_5V_DET": "HDMI_RX_5V_DET",
    "CEC": "HDMI_RX_CEC",
}

_PRIVATE_SIGNAL = {"HDMI_RX_SDA", "HDMI_RX_SCL", "HDMI_RX_5V", "HDMI_RX_HPD"}

RAIL_WORST_V = {"+VDD_LOGIC": 3.3, "GND": 0.0, "CHASSIS_GND": 0.0}
CABLE_5V_NODE = "HDMI_RX_5V"
CABLE_5V_WORST_V = 5.25


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return hdmi_rx.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(hdmi_rx.INTERFACE), externals
    assert not any(n.startswith("+3V3_HDMI_RX") or n.startswith("HDMI_RX_")
                   for n in externals), externals
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == _PRIVATE_SIGNAL, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in hdmi_rx.RAILS:
        want = NetClass.GROUND if rail in ("GND", "CHASSIS_GND") \
            else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in hdmi_rx.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_tmds_pairs_typed(c: Circuit):
    for p_pos, p_neg in hdmi_rx.TMDS_PAIRS:
        tp, tn = c.port_type_of(p_pos), c.port_type_of(p_neg)
        assert tp.kind == "tmds_pair" and tn.kind == "tmds_pair"
        assert tp.impedance == 100 and tn.impedance == 100
        assert tp.pair_with == p_neg and tn.pair_with == p_pos
    assert c.port_type_of("CEC").kind == "single"
    assert c.port_type_of("HDMI_5V_DET").kind == "single"


def test_tmds_lane_is_one_dc_coupled_net(c: Circuit, lib: Library):
    for net, jpin, esd_ref, _esd_io in hdmi_rx.TMDS_LANES:
        pins = {str(p) for p in c.nets[net].pins}
        assert len(pins) == 2, (net, pins)
        assert f"J1.{jpin}" in pins, (net, pins)
        other = (pins - {f"J1.{jpin}"}).pop()
        ref, _, pad = other.partition(".")
        assert ref == esd_ref, (net, pins)
        assert pad in lib.pin_numbers(c.parts[esd_ref].lib_id), (net, other)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    nc = {str(p) for p in c.nc_pins}
    assert "J1.14" in nc, nc
    for ref in ("U2", "U3", "U4"):
        assert {f"{ref}.{pad}" for pad in ("6", "7", "9", "10")} <= nc, (ref, nc)
    assert nc == {"J1.14"} | {
        f"{ref}.{pad}" for ref in ("U2", "U3", "U4")
        for pad in ("6", "7", "9", "10")}, nc


def test_edid_wc_hardwired_to_cable_5v(c: Circuit):
    n7 = c.net_of(PinRef("U1", "7"))
    n8 = c.net_of(PinRef("U1", "8"))
    assert n7 is not None and n8 is not None
    assert n7.name == n8.name == CABLE_5V_NODE, (n7, n8)
    assert n7.net_class is NetClass.SIGNAL


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1


def test_eeprom_cable5v_has_a_local_bypass(c: Circuit):
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            nets = [c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))]
            names = {n.name for n in nets if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd(CABLE_5V_NODE) == ["100n"]


def test_presence_divider_and_cec_pullup(c: Circuit):
    def res_between(val, a, b):
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":R") or p.value != val:
                continue
            nets = {n.name for n in
                    (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))) if n}
            if {a, b} <= nets:
                return ref
        return None
    assert res_between("10k", CABLE_5V_NODE, "HDMI_5V_DET")
    assert res_between("15k", "HDMI_5V_DET", "GND")
    assert res_between("27k", "CEC", "+VDD_LOGIC")
    assert res_between("1k", CABLE_5V_NODE, "HDMI_RX_HPD")


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    worst = dict(RAIL_WORST_V)
    worst[CABLE_5V_NODE] = CABLE_5V_WORST_V
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = [c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))]
        rail_v = max((worst.get(n.name, 0.0) for n in nets if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V node "
            f"(<1.3x margin)")


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_passives(prefix: str) -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt hdmi_rx"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(rf"^{prefix}\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt hdmi_rx"))
    pins = header.split()[2:]
    assert pins == ["VDD_LOGIC", "HDMI_5V_DET", "CEC", "GND"], pins
    iface = {n.lstrip("+") for n in hdmi_rx.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives("C").values())
    assert cir == netlist, (cir, netlist)


def test_cir_resistors_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":R"))
    cir = sorted(_cir_passives("R").values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_hdmi_a_rx_faithful_dossier_symbol(c: Circuit):
    assert c.parts["J1"].lib_id == "HDMI-019S:HDMI-019S", c.parts["J1"].lib_id
    assert not c.parts["J1"].lib_id.startswith("schgen:")
    assert c.parts["J1"].footprint == "HDMI-019S:HDMI-019S"


def test_bind_renames_only_externals_byte_stable():
    base = hdmi_rx.circuit()
    bound = hdmi_rx.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {r: p.lib_id for r, p in bound.parts.items()} == \
           {r: p.lib_id for r, p in base.parts.items()}
    assert bound.parts["J1"].lib_id == "HDMI-019S:HDMI-019S"
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert _PRIVATE_SIGNAL <= set(bound.nets)
    assert bound.port_type_of("HDMI_RX_D2_P").kind == "tmds_pair"
    assert bound.port_type_of("HDMI_RX_D2_P").pair_with == "HDMI_RX_D2_N"
    assert "+3V3_HDMI_RX" in bound.loads and "+VDD_LOGIC" not in bound.loads


def test_bind_identity_is_noop():
    base = hdmi_rx.circuit()
    ident = hdmi_rx.circuit({"bind": {n: n for n in hdmi_rx.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    base = hdmi_rx.circuit()
    m = hdmi_rx.circuit({"notes": {"draws": "custom draw note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VDD_LOGIC"][0][1] == "custom draw note"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        hdmi_rx.circuit({"note": {"draws": "X"}})


def test_bind_rejects_unknown_name():
    c = hdmi_rx.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    c = hdmi_rx.circuit()
    assert c.nets["HDMI_RX_SDA"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"HDMI_RX_SDA": "SOMETHING"})


def test_bind_rejects_collision():
    c = hdmi_rx.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"TMDS_RX_D2_P": "SHARED", "TMDS_RX_D2_N": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = hdmi_rx.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
