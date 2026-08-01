from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.pd_input.pd_input as pd_input
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "pd_input.cir"

_CARRIER_BIND = {
    "+VBUS_CONN": "+VBUS_IN", "+VBUS_OUT": "+VIN", "+VDD_LOGIC": "+3V3_SC",
    "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
    "CC1": "STM32_USB_CC1", "CC2": "STM32_USB_CC2",
    "USB_D_P": "STM32_USB_D_P", "USB_D_N": "STM32_USB_D_N",
    "FLT_N": "PD_FLT_N",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return pd_input.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(pd_input.INTERFACE), externals
    assert not any(n.startswith("STM32") or n.endswith("_SC")
                   or n in ("+VBUS_IN", "+VIN", "PD_FLT_N")
                   for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    grounds = {"GND", "CHASSIS_GND"}
    for rail in pd_input.RAILS:
        want = NetClass.GROUND if rail in grounds else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in pd_input.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_usb_data_pair_is_typed(c: Circuit):
    dp = c.port_type_of("USB_D_P")
    dn = c.port_type_of("USB_D_N")
    assert dp.kind == "usb_hs_pair" and dn.kind == "usb_hs_pair"
    assert dp.pair_with == "USB_D_N" and dn.pair_with == "USB_D_P"
    assert dp.impedance == 90 and dn.impedance == 90
    assert c.port_type_of("CC1").kind == "single"
    assert c.port_type_of("CC2").kind == "single"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {
        "U1.4", "U1.5", "U1.13", "U1.14", "U1.17",
        "J1.A8", "J1.B8",
    }


def test_no_reverse_blocking_fet(c: Circuit):
    for pin in ("4", "5"):
        assert c.net_of(PinRef("U1", pin)) is None
        assert PinRef("U1", pin) in c.nc_pins


def test_design_rules_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("ep", 0) >= 1


def test_inlet_and_output_each_have_a_local_bypass(c: Circuit):
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
    assert caps_to_gnd("+VBUS_CONN") == ["100n"]
    assert caps_to_gnd("+VBUS_OUT") == ["10u"]


def test_inlet_tvs_clamps_vbus_conn(c: Circuit):
    d1 = c.parts["D1"]
    assert d1.value == "SMBJ22A"
    nets = {c.net_of(PinRef("D1", "1")).name, c.net_of(PinRef("D1", "2")).name}
    assert nets == {"+VBUS_CONN", "GND"}


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")
                or p.lib_id.endswith(":D_Zener")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_vbus_caps_voltage_derated_for_the_rail(c: Circuit):
    worst = pd_input.RAIL_WORST_V
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
        if s.lower().startswith(".subckt pd_input"):
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
                  if line.strip().lower().startswith(".subckt pd_input"))
    pins = header.split()[2:]
    assert pins == ["VBUS_CONN", "VBUS_OUT", "VDD_LOGIC", "CC1", "CC2",
                    "USB_D_P", "USB_D_N", "FLT_N", "GND"], pins
    iface = {n.lstrip("+") for n in pd_input.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = pd_input.circuit()
    bound = pd_input.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert bound.port_type_of("STM32_USB_D_P").pair_with == "STM32_USB_D_N"
    assert bound.port_type_of("STM32_USB_D_N").pair_with == "STM32_USB_D_P"
    tp_values = {p.value for ref, p in bound.parts.items()
                 if p.lib_id == Circuit.TP_LIB_ID}
    assert tp_values == {"+VBUS_IN", "+VIN"}


def test_bind_identity_is_noop():
    base = pd_input.circuit()
    ident = pd_input.circuit({"bind": {n: n for n in pd_input.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    base = pd_input.circuit()
    m = pd_input.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)


def test_meta_expects_attaches_flt_deferral():
    m = pd_input.circuit({"expects": {"FLT_N": "my_expander (port P15)"}})
    assert m.port_type_of("FLT_N").expect == "my_expander (port P15)"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        pd_input.circuit({"bus": {"i2c": "X"}})


def test_bind_rejects_unknown_name():
    c = pd_input.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_SC"})


def test_bind_rejects_signal_net():
    c = pd_input.circuit()
    assert c.nets["PD_OVP_SET"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"PD_OVP_SET": "SOMETHING"})


def test_bind_rejects_collision():
    c = pd_input.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"CC1": "SHARED", "CC2": "SHARED"})


def test_bound_circuit_passes_local_design_rules(lib: Library):
    bound = pd_input.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
