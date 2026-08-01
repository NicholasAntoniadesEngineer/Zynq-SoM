from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.usb_pd.usb_pd as usb_pd
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_pd.cir"

_CARRIER_BIND = {
    "+VDD_LOGIC": "+3V3_SC", "+VBUS_SENSE": "+VBUS_IN", "GND": "GND",
    "CC1": "STM32_USB_CC1", "CC2": "STM32_USB_CC2",
    "I2C_SDA": "STM32_I2C2_SDA", "I2C_SCL": "STM32_I2C2_SCL",
    "INT_N": "SC_INT_N",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return usb_pd.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usb_pd.INTERFACE), externals
    assert not any(n.startswith("STM32") or n.endswith("_SC") or n == "+VBUS_IN"
                   for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in usb_pd.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in usb_pd.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    assert c.port_type_of("I2C_SDA").kind == "i2c"
    assert c.port_type_of("I2C_SCL").role == "scl"
    assert c.port_type_of("I2C_SDA").bus == c.port_type_of("I2C_SCL").bus


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"U1.12", "U1.13"}


def test_vconn_unused_by_design(c: Circuit):
    for pin in ("12", "13"):
        assert c.net_of(PinRef("U1", pin)) is None
        assert PinRef("U1", pin) in c.nc_pins


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1


def test_vdd_and_vbus_each_have_a_local_bypass(c: Circuit):
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
    assert caps_to_gnd("+VDD_LOGIC") == ["100n", "10u"]
    assert caps_to_gnd("+VBUS_SENSE") == ["100n"]
    assert caps_to_gnd("CC1") == ["200p"]
    assert caps_to_gnd("CC2") == ["200p"]


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"caps with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    worst = usb_pd.RAIL_WORST_V
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
    vbus_cap = next(
        p for ref, p in c.parts.items()
        if p.lib_id.endswith(":C")
        and "+VBUS_SENSE" in {n.name for n in
                              (c.net_of(PinRef(ref, "1")),
                               c.net_of(PinRef(ref, "2"))) if n})
    assert RATINGS_BY_LCSC[vbus_cap.fields["LCSC"]].v_max >= worst["+VBUS_SENSE"]


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt usb_pd"):
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
                  if line.strip().lower().startswith(".subckt usb_pd"))
    pins = header.split()[2:]
    assert pins == ["VDD_LOGIC", "VBUS_SENSE", "CC1", "CC2", "GND"], pins
    iface = {n.lstrip("+") for n in usb_pd.INTERFACE}
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
    base = usb_pd.circuit()
    bound = usb_pd.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND[n] for n in base.nets]
    assert bound.port_type_of("STM32_I2C2_SCL").role == "scl"
    assert bound.port_type_of("STM32_I2C2_SDA").bus == usb_pd.I2C_BUS
    assert "+3V3_SC" in bound.loads and "+VDD_LOGIC" not in bound.loads


def test_bind_identity_is_noop():
    base = usb_pd.circuit()
    ident = usb_pd.circuit({"bind": {n: n for n in usb_pd.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    base = usb_pd.circuit()
    m = usb_pd.circuit({"buses": {"i2c": "MY_I2C"},
                        "notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("I2C_SDA").bus == "MY_I2C"
    assert m.port_type_of("I2C_SCL").bus == "MY_I2C"
    assert m.loads["+VDD_LOGIC"][0][1] == "custom note"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usb_pd.circuit({"bus": {"i2c": "X"}})


def test_bind_rejects_unknown_name():
    c = usb_pd.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_SC"})


def test_bind_rejects_signal_net():
    c2 = Circuit("t", "t")
    c2.part("R1", "Device:R", "1k", "")
    c2.part("R2", "Device:R", "1k", "")
    c2.net("MID", "R1.2", "R2.1")
    assert c2.nets["MID"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c2.bind({"MID": "SOMETHING"})


def test_bind_rejects_collision():
    c = usb_pd.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"CC1": "SHARED", "CC2": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = usb_pd.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
