from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import subsystems.usbc_otg.usbc_otg as usbc_otg
from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

HERE = Path(__file__).resolve().parent
CIR = HERE / "usbc_otg.cir"

_CARRIER_BIND = {
    "+VBUS_SUPPLY": "+5V_USB",
    "+VDD_LOGIC": "+3V3_SC",
    "GND": "GND",
    "CHASSIS_GND": "CHASSIS_GND",
    "USB_DP": "USB_D+",
    "USB_DM": "USB_D-",
    "VBUS": "USB_VBUS",
    "VBUS_EN": "VBUS_OUT_EN",
    "FLT_N": "USBOTG_FLT_N",
    "USB_ID": "USB_ID",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return usbc_otg.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def test_interface_is_abstract_and_carrier_free(c: Circuit):
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usbc_otg.INTERFACE), externals
    carrier = {"+5V_USB", "+3V3_SC", "USB_VBUS", "VBUS_OUT_EN", "USBOTG_FLT_N",
               "USB_D+", "USB_D-"}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    grounds = {"GND", "CHASSIS_GND"}
    for rail in usbc_otg.RAILS:
        want = NetClass.GROUND if rail in grounds else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in usbc_otg.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    dp = c.port_type_of("USB_DP")
    dm = c.port_type_of("USB_DM")
    assert dp.kind == "usb_hs_pair" and dm.kind == "usb_hs_pair"
    assert dp.pair_with == "USB_DM" and dm.pair_with == "USB_DP"
    assert dp.impedance == 90 and dm.impedance == 90


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert len(c.nc_pins) == 2
    assert all(p.ref == "J2" for p in c.nc_pins)


def test_sbu_unused_by_design(c: Circuit):
    ncs = {str(p) for p in c.nc_pins}
    assert len(ncs) == 2 and all(n.startswith("J2.") for n in ncs)


def test_decoupling_complete(c: Circuit, lib: Library):
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_power_switch_has_input_bypass_and_vbus_bulk(c: Circuit):
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
    assert caps_to_gnd("+VBUS_SUPPLY") == ["100n"]
    assert caps_to_gnd("VBUS") == ["22u"]


def test_host_advertising_and_id_strap(c: Circuit):
    def res_between(a: str, b: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":R"):
                continue
            nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                     c.net_of(PinRef(ref, "2"))) if n}
            if {a, b} <= nets or (a in nets and b is None):
                out.append(p.value)
        return sorted(out)
    rp = [p.value for ref, p in c.parts.items()
          if p.lib_id.endswith(":R") and "VBUS" in
          {n.name for n in (c.net_of(PinRef(ref, "1")),
                            c.net_of(PinRef(ref, "2"))) if n}
          and p.value == "56k"]
    assert sorted(rp) == ["56k", "56k"]
    id_strap = [p.value for ref, p in c.parts.items()
                if p.lib_id.endswith(":R") and p.value == "1k" and "GND" in
                {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}]
    assert id_strap == ["1k"]


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
    worst = usbc_otg.RAIL_WORST_V
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
        if s.lower().startswith(".subckt usbc_otg"):
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
                  if line.strip().lower().startswith(".subckt usbc_otg"))
    pins = header.split()[2:]
    assert pins == ["VBUS_SUPPLY", "VBUS", "VDD_LOGIC", "GND"], pins
    iface = {n.lstrip("+") for n in usbc_otg.INTERFACE}
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
    base = usbc_otg.circuit()
    bound = usbc_otg.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert all(n in bound.nets for n in base.nets if n.startswith("USBC_"))
    assert "+5V_USB" in bound.loads and "+VBUS_SUPPLY" not in bound.loads
    assert "+3V3_SC" in bound.loads and "+VDD_LOGIC" not in bound.loads


def test_bind_repoints_diff_pair_complement():
    bound = usbc_otg.circuit({"bind": _CARRIER_BIND})
    assert bound.port_type_of("USB_D+").pair_with == "USB_D-"
    assert bound.port_type_of("USB_D-").pair_with == "USB_D+"
    base = usbc_otg.circuit()
    assert base.port_type_of("USB_DP").pair_with == "USB_DM"


def test_bind_identity_is_noop():
    base = usbc_otg.circuit()
    ident = usbc_otg.circuit({"bind": {n: n for n in usbc_otg.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_notes_override_house_style():
    base = usbc_otg.circuit()
    m = usbc_otg.circuit({"notes": {"draws_vbus": "custom vbus",
                                    "draws_flt": "custom flt"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VBUS_SUPPLY"][0][1] == "custom vbus"
    assert m.loads["+VDD_LOGIC"][0][1] == "custom flt"


def test_meta_rejects_unknown_key():
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usbc_otg.circuit({"note": {"draws_vbus": "X"}})


def test_bind_rejects_unknown_name():
    c = usbc_otg.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+5V_USB"})


def test_bind_rejects_signal_net():
    c = usbc_otg.circuit()
    sig = next(n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL)
    assert sig.startswith("USBC_")
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({sig: "SOMETHING"})


def test_bind_rejects_collision():
    c = usbc_otg.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"USB_DP": "SHARED", "USB_DM": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    bound = usbc_otg.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
