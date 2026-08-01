from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.rj45_connector.rj45_connector as rj45_connector
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "rj45_connector.cir"

_CARRIER_BIND = {
    "+VLED": "+3V3",
    "GND": "GND",
    "CHASSIS_GND": "CHASSIS_GND",
    "RJ45_MDI0_P": "ETH_LINE_MDI_0_P", "RJ45_MDI0_N": "ETH_LINE_MDI_0_N",
    "RJ45_MDI1_P": "ETH_LINE_MDI_1_P", "RJ45_MDI1_N": "ETH_LINE_MDI_1_N",
    "RJ45_MDI2_P": "ETH_LINE_MDI_2_P", "RJ45_MDI2_N": "ETH_LINE_MDI_2_N",
    "RJ45_MDI3_P": "ETH_LINE_MDI_3_P", "RJ45_MDI3_N": "ETH_LINE_MDI_3_N",
}

_MAGNETICS_DEFER = "ethernet (magnetics media side)"
_CARRIER_EXPECTS = {f"RJ45_MDI{n}_P": _MAGNETICS_DEFER for n in range(4)}

_CONTACTS = {
    1: "RJ45_MDI0_P", 2: "RJ45_MDI0_N",
    3: "RJ45_MDI1_P", 6: "RJ45_MDI1_N",
    4: "RJ45_MDI2_P", 5: "RJ45_MDI2_N",
    7: "RJ45_MDI3_P", 8: "RJ45_MDI3_N",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return rj45_connector.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(rj45_connector.INTERFACE), externals
    assert not any(n.startswith("ETH_LINE") or n == "+3V3" for n in externals), \
        externals
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert {"RJ45_LED_L", "RJ45_LED_R"} == signals, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+VLED"] is NetClass.POWER, cls["+VLED"]
    assert cls["GND"] is NetClass.GROUND, cls["GND"]
    assert cls["CHASSIS_GND"] is NetClass.GROUND, cls["CHASSIS_GND"]
    for port in rj45_connector.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_mdi_pairs_typed(c: Circuit):
    for n in range(4):
        pp, pn = f"RJ45_MDI{n}_P", f"RJ45_MDI{n}_N"
        tp, tn = c.port_type_of(pp), c.port_type_of(pn)
        assert tp.kind == "diff_pair" and tn.kind == "diff_pair", (pp, pn)
        assert tp.impedance == 100 and tn.impedance == 100, (pp, pn)
        assert tp.pair_with == pn and tn.pair_with == pp, (pp, pn)


def test_t568_contact_mapping_faithful(c: Circuit):
    for pin, net in _CONTACTS.items():
        assert PinRef("J1", str(pin)) in c.nets[net].pins, (pin, net)
    assert "KH-5224-8P8C-D" in c.parts["J1"].lib_id


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == set(), c.nc_pins


def test_housing_leds_are_330r_indicators(c: Circuit):
    for ref, anode_node, anode_pin, cath_pin in (
            ("R1", "RJ45_LED_L", "9", "10"),
            ("R2", "RJ45_LED_R", "11", "12")):
        assert c.parts[ref].value == "330R", ref
        assert PinRef(ref, "1") in c.nets["+VLED"].pins, ref
        anode = {str(p) for p in c.nets[anode_node].pins}
        assert f"{ref}.2" in anode and f"J1.{anode_pin}" in anode, (ref, anode)
        assert PinRef("J1", cath_pin) in c.nets["GND"].pins, cath_pin
    assert not any(p.lib_id.endswith(":LED") for p in c.parts.values())


def test_shield_on_chassis_no_mounting_holes_here(c: Circuit):
    ch = c.nets["CHASSIS_GND"].pins
    assert PinRef("J1", "13") in ch, ch
    assert ch == [PinRef("J1", "13")], ch
    holes = sorted(ref for ref in c.parts if ref.startswith("H"))
    assert holes == [], holes


def test_design_rules_slice_clean(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings


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


def _cir_resistors() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt rj45_connector"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^R\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    lines = CIR.read_text().splitlines()
    hdr_idx = next(i for i, line in enumerate(lines)
                   if line.strip().lower().startswith(".subckt rj45_connector"))
    header = lines[hdr_idx].split()[2:]
    j = hdr_idx + 1
    while j < len(lines) and lines[j].lstrip().startswith("+"):
        header += lines[j].lstrip()[1:].split()
        j += 1
    assert header == [
        "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N", "MDI2_P", "MDI2_N",
        "MDI3_P", "MDI3_N", "VLED", "GND", "CHASSIS_GND"], header
    iface = {n.lstrip("+").removeprefix("RJ45_") for n in rj45_connector.INTERFACE}
    assert all(p in iface for p in header), header


def test_cir_resistors_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":R"))
    cir = sorted(_cir_resistors().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = rj45_connector.circuit()
    bound = rj45_connector.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert bound.port_type_of("ETH_LINE_MDI_0_P").pair_with == "ETH_LINE_MDI_0_N"
    assert bound.port_type_of("ETH_LINE_MDI_0_N").pair_with == "ETH_LINE_MDI_0_P"
    assert bound.port_type_of("ETH_LINE_MDI_2_P").impedance == 100
    assert "+3V3" in bound.loads and "+VLED" not in bound.loads


def test_bind_with_expects_threads_pair_deferral():
    bound = rj45_connector.circuit({"bind": _CARRIER_BIND,
                                    "expects": _CARRIER_EXPECTS})
    for n in range(4):
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_P").expect == _MAGNETICS_DEFER
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_N").expect == _MAGNETICS_DEFER


def test_meta_notes_override_draws(c: Circuit):
    base = rj45_connector.circuit()
    m = rj45_connector.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VLED"][0][1] == "custom note"


def test_bind_identity_is_noop():
    base = rj45_connector.circuit()
    ident = rj45_connector.circuit(
        {"bind": {n: n for n in rj45_connector.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        rj45_connector.circuit({"bus": {"x": "Y"}})


def test_bind_rejects_unknown_name():
    c = rj45_connector.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    c = rj45_connector.circuit()
    assert c.nets["RJ45_LED_L"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"RJ45_LED_L": "SOMETHING"})


def test_bind_rejects_collision():
    c = rj45_connector.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"RJ45_MDI0_P": "SHARED", "RJ45_MDI0_N": "SHARED"})
