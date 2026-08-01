from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.uart_bridge.uart_bridge as uart_bridge
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "uart_bridge.cir"

_CARRIER_BIND = {
    "+VDD_IO": "+3V3", "GND": "GND",
    "USB_VBUS": "USB_UART_VBUS",
    "USB_DP": "USB_UART_DP", "USB_DM": "USB_UART_DM",
    "UART_TXD": "ZYNQ_PS_UART0_RXD", "UART_RXD": "ZYNQ_PS_UART0_TXD",
    "UART_RTS_N": "ZYNQ_PS_UART0_CTS_N", "UART_CTS_N": "ZYNQ_PS_UART0_RTS_N",
}

RAIL_WORST_V = {"+VDD_IO": 3.3, "GND": 0.0}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return uart_bridge.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(uart_bridge.INTERFACE), externals
    assert not any(n.startswith("ZYNQ_PS") or n.startswith("USB_UART")
                   or n == "+3V3" for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in uart_bridge.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in uart_bridge.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    dp = c.port_type_of("USB_DP")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "USB_DM"
    assert dp.impedance == 90
    assert c.port_type_of("USB_DM").pair_with == "USB_DP"
    for p in ("UART_TXD", "UART_RXD", "UART_RTS_N", "UART_CTS_N"):
        assert c.port_type_of(p).kind == "single"


def test_internal_signal_nets_stay_private(c: Circuit):
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == {"CP2102N_RST_N", "CP2102N_VBUS_SNS"}, signals
    assert not (signals & set(uart_bridge.INTERFACE))


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {
        "U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15",
        "U1.16", "U1.17", "U1.22", "U1.23", "U1.24"}


def test_qfn_exposed_pad_is_the_second_gnd(c: Circuit):
    gnd = c.net_of(PinRef("U1", "25"))
    assert gnd is not None and gnd.name == "GND"
    assert c.net_of(PinRef("U1", "2")).name == "GND"


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1


def test_self_powered_rail_has_full_bypass(c: Circuit):
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = {n.name for n in
                     (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2")))
                     if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VDD_IO") == ["100n", "100n", "100n", "10u"]


def test_vbus_sense_divider(c: Circuit):
    top = next(p for ref, p in c.parts.items() if p.value == "22k1")
    bot = next(p for ref, p in c.parts.items() if p.value == "47k5")
    top_nets = {n.name for n in (c.net_of(PinRef(top.ref, "1")),
                                 c.net_of(PinRef(top.ref, "2"))) if n}
    bot_nets = {n.name for n in (c.net_of(PinRef(bot.ref, "1")),
                                 c.net_of(PinRef(bot.ref, "2"))) if n}
    assert top_nets == {"USB_VBUS", "CP2102N_VBUS_SNS"}, top_nets
    assert bot_nets == {"CP2102N_VBUS_SNS", "GND"}, bot_nets
    assert c.net_of(PinRef("U1", "8")).name == "CP2102N_VBUS_SNS"


def test_reset_waiver_declared(c: Circuit):
    assert "CP2102N_RST_N" in c.reset_waivers
    r1 = next(p for ref, p in c.parts.items() if p.value == "1k")
    nets = {n.name for n in (c.net_of(PinRef(r1.ref, "1")),
                             c.net_of(PinRef(r1.ref, "2"))) if n}
    assert nets == {"+VDD_IO", "CP2102N_RST_N"}, nets


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id not in ("Device:C", "Device:R"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    worst = RAIL_WORST_V
    n_checked = 0
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        rail_v = max((worst.get(n.name, 0.0) for n in
                      (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2")))
                      if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail (<1.3x)")
        n_checked += 1
    assert n_checked == 4


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt uart_bridge"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_abstract_interface():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt uart_bridge"))
    pins = header.split()[2:]
    assert pins == ["VDD_IO", "USB_VBUS", "GND"], pins
    iface = {n.lstrip("+") for n in uart_bridge.INTERFACE}
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
    base = uart_bridge.circuit()
    bound = uart_bridge.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert "+3V3" in bound.loads and "+VDD_IO" not in bound.loads
    assert "CP2102N_RST_N" in bound.reset_waivers


def test_bind_rewrites_the_usb_pair_payload():
    bound = uart_bridge.circuit({"bind": _CARRIER_BIND})
    dp = bound.port_type_of("USB_UART_DP")
    dm = bound.port_type_of("USB_UART_DM")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "USB_UART_DM"
    assert dm.pair_with == "USB_UART_DP"
    assert "USB_DP" not in (dp.pair_with, dm.pair_with)
    assert "USB_DM" not in (dp.pair_with, dm.pair_with)


def test_bind_identity_is_noop():
    base = uart_bridge.circuit()
    ident = uart_bridge.circuit({"bind": {n: n for n in uart_bridge.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_notes_override_house_style():
    base = uart_bridge.circuit()
    m = uart_bridge.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VDD_IO"][0][1] == "custom note"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        uart_bridge.circuit({"note": {"draws": "X"}})


def test_bind_rejects_unknown_name():
    c = uart_bridge.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3"})


def test_bind_rejects_signal_net():
    c = uart_bridge.circuit()
    assert c.nets["CP2102N_RST_N"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"CP2102N_RST_N": "SOMETHING"})


def test_bind_rejects_collision():
    c = uart_bridge.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|merge"):
        c.bind({"UART_TXD": "SHARED", "UART_RXD": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = uart_bridge.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
