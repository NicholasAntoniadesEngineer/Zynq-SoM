from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.hdmi_tx.hdmi_tx as hdmi_tx
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "hdmi_tx.cir"

_CARRIER_BIND = {
    "+VDD_IO": "+3V3_HDMI_TX", "+5V": "+5V_HDMI_TX",
    "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
    "TMDS_D2_P": "ZYNQ_HDMI_TX_TMDS_2_P", "TMDS_D2_N": "ZYNQ_HDMI_TX_TMDS_2_N",
    "TMDS_D1_P": "ZYNQ_HDMI_TX_TMDS_1_P", "TMDS_D1_N": "ZYNQ_HDMI_TX_TMDS_1_N",
    "TMDS_D0_P": "ZYNQ_HDMI_TX_TMDS_0_P", "TMDS_D0_N": "ZYNQ_HDMI_TX_TMDS_0_N",
    "TMDS_CLK_P": "ZYNQ_HDMI_TX_TMDS_CLK_P",
    "TMDS_CLK_N": "ZYNQ_HDMI_TX_TMDS_CLK_N",
    "CEC": "ZYNQ_HDMI_TX_CEC",
    "DDC_SCL": "ZYNQ_HDMI_TX_SCL", "DDC_SDA": "ZYNQ_HDMI_TX_SDA",
    "HPD": "ZYNQ_HDMI_TX_HPD",
}

RAIL_WORST_V = {"+VDD_IO": 3.3, "+5V": 5.0, "GND": 0.0, "CHASSIS_GND": 0.0}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return hdmi_tx.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(hdmi_tx.INTERFACE), externals
    assert not any(n.startswith("ZYNQ") or n.endswith("_HDMI_TX")
                   for n in externals), externals
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert {"HDMI_TX_CON_5V0", "HDMI_TX_CON_CEC", "HDMI_TX_CON_SCL",
            "HDMI_TX_CON_SDA", "HDMI_TX_CON_HPD",
            "HDMI_TX_LS_OE", "HDMI_TX_CT_HPD"} == signals, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in hdmi_tx.RAILS:
        want = NetClass.GROUND if rail in ("GND", "CHASSIS_GND") \
            else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in hdmi_tx.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_tmds_pairs_and_ddc_bus_typed(c: Circuit):
    for p_pos, p_neg in hdmi_tx.TMDS_PAIRS:
        tp, tn = c.port_type_of(p_pos), c.port_type_of(p_neg)
        assert tp.kind == "tmds_pair" and tn.kind == "tmds_pair"
        assert tp.impedance == 100 and tn.impedance == 100
        assert tp.pair_with == p_neg and tn.pair_with == p_pos
    assert c.port_type_of("DDC_SCL").kind == "i2c"
    assert c.port_type_of("DDC_SCL").role == "scl"
    assert c.port_type_of("DDC_SDA").role == "sda"
    assert c.port_type_of("DDC_SCL").bus == c.port_type_of("DDC_SDA").bus
    assert c.port_type_of("DDC_SCL").bus == hdmi_tx.DDC_BUS


def test_tmds_lane_is_one_flow_through_net(c: Circuit):
    for port, upin, jpin in hdmi_tx.TMDS_LANES:
        pins = {str(p) for p in c.nets[port].pins}
        assert pins == {f"U1.{upin}", f"J1.{jpin}"}, (port, pins)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"J1.14"}


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1


def test_each_rail_has_a_local_bypass(c: Circuit):
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
    assert caps_to_gnd("+VDD_IO") == ["100n", "10u"]
    assert caps_to_gnd("+5V") == ["100n"]
    assert caps_to_gnd("HDMI_TX_CON_5V0") == ["100n", "1u"]


def test_always_on_straps_pulled_to_vcca(c: Circuit):
    for strap in ("HDMI_TX_LS_OE", "HDMI_TX_CT_HPD"):
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":R"):
                continue
            nets = {n.name for n in
                    (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2")))
                    if n}
            if strap in nets:
                assert "+VDD_IO" in nets and p.value == "10k", (strap, nets)
                break
        else:
            pytest.fail(f"no 10k strap on {strap}")


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
    worst["HDMI_TX_CON_5V0"] = 5.0
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


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt hdmi_tx"):
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
                  if line.strip().lower().startswith(".subckt hdmi_tx"))
    pins = header.split()[2:]
    assert pins == ["VDD_IO", "5V", "GND"], pins
    iface = {n.lstrip("+") for n in hdmi_tx.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = hdmi_tx.circuit()
    bound = hdmi_tx.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert bound.port_type_of("ZYNQ_HDMI_TX_SCL").role == "scl"
    assert bound.port_type_of("ZYNQ_HDMI_TX_TMDS_2_P").kind == "tmds_pair"
    assert "+3V3_HDMI_TX" in bound.loads and "+VDD_IO" not in bound.loads
    assert "+5V_HDMI_TX" in bound.loads and "+5V" not in bound.loads
    assert "ZYNQ_HDMI_TX_SCL" in bound.pull_waivers
    assert "ZYNQ_HDMI_TX_SDA" in bound.pull_waivers


def test_bind_identity_is_noop():
    base = hdmi_tx.circuit()
    ident = hdmi_tx.circuit({"bind": {n: n for n in hdmi_tx.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    base = hdmi_tx.circuit()
    m = hdmi_tx.circuit({"buses": {"ddc": "MY_DDC"},
                         "notes": {"draws_vcca": "custom vcca",
                                   "draws_5v": "custom 5v"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("DDC_SCL").bus == "MY_DDC"
    assert m.port_type_of("DDC_SDA").bus == "MY_DDC"
    assert m.loads["+VDD_IO"][0][1] == "custom vcca"
    assert m.loads["+5V"][0][1] == "custom 5v"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        hdmi_tx.circuit({"bus": {"ddc": "X"}})


def test_bind_rejects_unknown_name():
    c = hdmi_tx.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    c = hdmi_tx.circuit()
    assert c.nets["HDMI_TX_CON_5V0"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"HDMI_TX_CON_5V0": "SOMETHING"})


def test_bind_rejects_collision():
    c = hdmi_tx.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"TMDS_D2_P": "SHARED", "TMDS_D2_N": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = hdmi_tx.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
