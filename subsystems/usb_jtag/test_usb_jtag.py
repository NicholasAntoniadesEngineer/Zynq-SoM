from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.usb_jtag.usb_jtag as usb_jtag
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_jtag.cir"

_CARRIER_BIND = {
    "+VBUS_USB": "+5V_DBG", "+3V3_ISLAND": "+3V3_DBG", "GND": "GND",
    "USB_DP": "DBG_USB_DP", "USB_DM": "DBG_USB_DM",
    "JTAG_TCK": "ZYNQ_TCK", "JTAG_TDI": "ZYNQ_TDI",
    "JTAG_TMS": "ZYNQ_TMS", "JTAG_TDO": "ZYNQ_TDO",
    "UART_RXD": "DBG_UART_RXD", "UART_TXD": "DBG_UART_TXD",
}

RAIL_WORST_V = {"+VBUS_USB": 5.5, "+3V3_ISLAND": 3.6, "GND": 0.0}

_CRYSTAL_CAP_LCSC = "C162205"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return usb_jtag.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usb_jtag.INTERFACE), externals
    assert not any(n.startswith("ZYNQ") or n.startswith("DBG_")
                   or n.endswith("_DBG") for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in usb_jtag.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in usb_jtag.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    dp = c.port_type_of("USB_DP")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "USB_DM"
    assert c.port_type_of("USB_DM").pair_with == "USB_DP"
    for p in ("JTAG_TCK", "JTAG_TDI", "JTAG_TMS", "JTAG_TDO",
              "UART_RXD", "UART_TXD"):
        assert c.port_type_of(p).kind == "single", p


def test_internal_signal_nets_stay_private(c: Circuit):
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == {
        "DBG_FT_TCK", "DBG_FT_TDI", "DBG_FT_TMS", "DBG_FT_TDO",
        "DBG_JTAG_OE_N", "DBG_MODE_DTR1", "DBG_MODE_RTS1", "DBG_RST_N",
        "DBG_XI", "DBG_XO"}, signals
    assert not (signals & set(usb_jtag.INTERFACE))


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {
        "U1.2", "U1.9", "U1.11", "U1.12", "U1.15", "U4.4",
        "SW1.2", "SW1.3", "SW1.4", "SW1.5", "SW1.6", "SW1.7"}


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 3


def test_island_rail_has_full_bypass(c: Circuit):
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
    assert caps_to_gnd("+3V3_ISLAND") == ["100n", "100n", "100n", "10u"]
    assert caps_to_gnd("+VBUS_USB") == ["1u"]


def test_mode_strap_and_oe_pulls(c: Circuit):
    def res_nets(value: str) -> list[set]:
        out = []
        for ref, p in c.parts.items():
            if p.lib_id == "Device:R" and p.value == value:
                out.append({n.name for n in (c.net_of(PinRef(ref, "1")),
                                             c.net_of(PinRef(ref, "2"))) if n})
        return out
    pulldowns = [s for s in res_nets("10k")
                 if s in ({"DBG_MODE_DTR1", "GND"}, {"DBG_MODE_RTS1", "GND"})]
    assert len(pulldowns) == 2, res_nets("10k")
    assert res_nets("100k") == [{"+3V3_ISLAND", "DBG_JTAG_OE_N"}], res_nets("100k")


def test_reset_waiver_declared(c: Circuit):
    assert "DBG_RST_N" in c.reset_waivers
    pulls = [p for ref, p in c.parts.items()
             if p.lib_id == "Device:R" and p.value == "10k"
             and {"+3V3_ISLAND", "DBG_RST_N"} == {
                 n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}]
    assert len(pulls) == 1, pulls


def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id not in ("Device:C", "Device:R"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc == _CRYSTAL_CAP_LCSC:
            continue
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    worst = RAIL_WORST_V
    n_checked = 0
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        if p.fields.get("LCSC") not in RATINGS_BY_LCSC:
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
    assert n_checked == 5


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt usb_jtag"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def _cir_resistors() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt usb_jtag"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^R\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_abstract_interface():
    header = next(line for line in CIR.read_text().splitlines()
                  if line.strip().lower().startswith(".subckt usb_jtag"))
    pins = header.split()[2:]
    assert pins == ["VBUS_USB", "3V3_ISLAND", "GND"], pins
    iface = {n.lstrip("+") for n in usb_jtag.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_cir_resistors_match_netlist(c: Circuit):
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id == "Device:R")
    cir = sorted(_cir_resistors().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


def test_bind_renames_only_externals_byte_stable():
    base = usb_jtag.circuit()
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert "+3V3_DBG" in bound.loads and "+3V3_ISLAND" not in bound.loads
    assert "DBG_RST_N" in bound.reset_waivers


def test_bind_rewrites_the_usb_pair_payload():
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    dp = bound.port_type_of("DBG_USB_DP")
    dm = bound.port_type_of("DBG_USB_DM")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "DBG_USB_DM"
    assert dm.pair_with == "DBG_USB_DP"
    assert "USB_DP" not in (dp.pair_with, dm.pair_with)
    assert "USB_DM" not in (dp.pair_with, dm.pair_with)


def test_bind_rewrites_testpoint_values():
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    tp_values = [p.value for ref, p in sorted(bound.parts.items())
                 if ref.startswith("TP")]
    assert tp_values == ["+3V3_DBG", "DBG_UART_TXD", "DBG_UART_RXD"], tp_values


def test_bind_identity_is_noop():
    base = usb_jtag.circuit()
    ident = usb_jtag.circuit({"bind": {n: n for n in usb_jtag.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_notes_override_house_style():
    base = usb_jtag.circuit()
    m = usb_jtag.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+3V3_ISLAND"][0][1] == "custom note"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usb_jtag.circuit({"note": {"draws": "X"}})


def test_bind_rejects_unknown_name():
    c = usb_jtag.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_DBG"})


def test_bind_rejects_signal_net():
    c = usb_jtag.circuit()
    assert c.nets["DBG_RST_N"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"DBG_RST_N": "SOMETHING"})


def test_bind_rejects_collision():
    c = usb_jtag.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|merge"):
        c.bind({"JTAG_TCK": "SHARED", "JTAG_TMS": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
