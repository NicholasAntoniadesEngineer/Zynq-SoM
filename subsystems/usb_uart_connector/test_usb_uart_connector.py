from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.usb_uart_connector.usb_uart_connector as usb_uart_connector
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_uart_connector.cir"

_CARRIER_BIND = {
    "GND": "GND",
    "CHASSIS_GND": "CHASSIS_GND",
    "VBUS": "USB_UART_VBUS",
    "USB_DP": "USB_UART_DP",
    "USB_DM": "USB_UART_DM",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return usb_uart_connector.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usb_uart_connector.INTERFACE), externals
    carrier = {"USB_UART_VBUS", "USB_UART_DP", "USB_UART_DM"}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    grounds = {"GND", "CHASSIS_GND"}
    for rail in usb_uart_connector.RAILS:
        assert cls[rail] is NetClass.GROUND, (rail, cls[rail])
        assert rail in grounds
    for port in usb_uart_connector.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    dp = c.port_type_of("USB_DP")
    dm = c.port_type_of("USB_DM")
    assert dp.kind == "usb_hs_pair" and dm.kind == "usb_hs_pair"
    assert dp.pair_with == "USB_DM" and dm.pair_with == "USB_DP"
    assert dp.impedance == 90 and dm.impedance == 90


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert len(c.nc_pins) == 2
    assert all(p.ref == "J1" for p in c.nc_pins)


def test_sbu_unused_by_design(c: Circuit):
    ncs = {str(p) for p in c.nc_pins}
    assert len(ncs) == 2 and all(n.startswith("J1.") for n in ncs)


def test_device_role_rd_pulldowns(c: Circuit):
    rd = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":R"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if "GND" in nets and p.value == "5.1k":
            rd.append(ref)
    assert sorted(rd) == ["R1", "R2"], rd
    cc_nets = {c.net_of(PinRef("R1", "1")).name, c.net_of(PinRef("R2", "1")).name}
    assert all(n.startswith("USB_UART_") for n in cc_nets), cc_nets
    assert all(c.nets[n].net_class is NetClass.SIGNAL for n in cc_nets)
    assert not any(p.value == "56k" for p in c.parts.values())


def test_data_pair_flip_shorted_through_esd(c: Circuit):
    dp_conn = c.nets["USB_UART_DP_CONN"]
    assert dp_conn.net_class is NetClass.SIGNAL
    assert dp_conn is c.net_of(PinRef("U1", "1"))
    assert c.net_of(PinRef("U1", "6")).name == "USB_DP"
    dm_conn = c.nets["USB_UART_DM_CONN"]
    assert dm_conn.net_class is NetClass.SIGNAL
    assert dm_conn is c.net_of(PinRef("U1", "3"))
    assert c.net_of(PinRef("U1", "4")).name == "USB_DM"


def test_vbus_has_bulk_to_gnd(c: Circuit):
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                      c.net_of(PinRef(ref, "2"))) if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("VBUS") == ["10u"]
    vbus_refs = {p.ref for p in c.nets["VBUS"].pins}
    assert {"J1", "U1", "C1"} <= vbus_refs, vbus_refs
    assert c.net_of(PinRef("U1", "5")).name == "VBUS"
    assert c.net_of(PinRef("U1", "2")).name == "GND"


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


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
    worst = usb_uart_connector.RAIL_WORST_V
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
        if s.lower().startswith(".subckt usb_uart_connector"):
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
                  if line.strip().lower().startswith(".subckt usb_uart_connector"))
    pins = header.split()[2:]
    assert pins == ["VBUS", "GND"], pins
    iface = {n.lstrip("+") for n in usb_uart_connector.INTERFACE}
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
    base = usb_uart_connector.circuit()
    bound = usb_uart_connector.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert all(n in bound.nets for n in base.nets if n.endswith("_CONN"))
    assert all(n in bound.nets for n in base.nets if n.endswith("_CC"))


def test_bind_repoints_diff_pair_complement():
    bound = usb_uart_connector.circuit({"bind": _CARRIER_BIND})
    assert bound.port_type_of("USB_UART_DP").pair_with == "USB_UART_DM"
    assert bound.port_type_of("USB_UART_DM").pair_with == "USB_UART_DP"
    base = usb_uart_connector.circuit()
    assert base.port_type_of("USB_DP").pair_with == "USB_DM"


def test_bind_identity_is_noop():
    base = usb_uart_connector.circuit()
    ident = usb_uart_connector.circuit(
        {"bind": {n: n for n in usb_uart_connector.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usb_uart_connector.circuit({"bnid": _CARRIER_BIND})


def test_bind_rejects_unknown_name():
    c = usb_uart_connector.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    c = usb_uart_connector.circuit()
    sig = next(n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL)
    assert sig.startswith("USB_UART_")
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({sig: "SOMETHING"})


def test_bind_rejects_collision():
    c = usb_uart_connector.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"USB_DP": "SHARED", "USB_DM": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = usb_uart_connector.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
