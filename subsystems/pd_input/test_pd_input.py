"""LOCAL electrical-correctness test for the pd_input reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). Co-located with the
package, the same shape as ``subsystems/usb_pd/test_usb_pd.py``.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), the usb_hs_pair typed.
  * design-rule completeness      — design_rules DECAP/EP/STRAP slice: the eFuse
    exposed pad is on GND, no floating config strap.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for that rail
    (the subsystem's own RAIL_WORST_V, since a board power tree is not present
    locally). The inlet/output caps ride the live 20 V+5% VBUS.
  * SPICE passives                — the .cir subckt's cap network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving
    (incl. the usb_hs_pair pair_with payload + testpoint VALUES).

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph (the CC lines cross to the usb_pd PHY, FLT_N to a host
expander), the full power-tree headroom, board ERC and the board netlist merge.
Those are aggregated by `schgen board`.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

import subsystems.pd_input.pd_input as pd_input

HERE = Path(__file__).resolve().parent
CIR = HERE / "pd_input.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/pd_input.py.
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
    """The standalone subsystem (abstract names)."""
    return pd_input.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(pd_input.INTERFACE), externals
    # the abstract names must not be carrier net names
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
    """The FS data pair is typed usb_hs_pair (90R), reciprocally paired — so a
    board's SI/layout gate sees a routed differential pair, not two singles."""
    dp = c.port_type_of("USB_D_P")
    dn = c.port_type_of("USB_D_N")
    assert dp.kind == "usb_hs_pair" and dn.kind == "usb_hs_pair"
    assert dp.pair_with == "USB_D_N" and dn.pair_with == "USB_D_P"
    assert dp.impedance == 90 and dn.impedance == 90
    # the CC lines are single-ended (not a pair)
    assert c.port_type_of("CC1").kind == "single"
    assert c.port_type_of("CC2").kind == "single"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the intentional no-connects: eFuse unused pins + the receptacle SBU pads
    assert {str(p) for p in c.nc_pins} == {
        "U1.4", "U1.5", "U1.13", "U1.14", "U1.17",   # B_GATE/DRV/SHDN#/IMON/PGOOD
        "J1.A8", "J1.B8",                            # SBU1 / SBU2
    }


def test_no_reverse_blocking_fet(c: Circuit):
    """A USB-C inlet cannot be reverse-wired, so the eFuse B_GATE/DRV (the
    blocking-FET drive, pins 4/5) are explicit author no-connects (DS Fig 8-8)."""
    for pin in ("4", "5"):
        assert c.net_of(PinRef("U1", pin)) is None
        assert PinRef("U1", pin) in c.nc_pins


# ---- decoupling / design-rule completeness (design_rules LOCAL slice) -----------

def test_design_rules_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: the eFuse exposed pad is on GND, no config strap floats.
    (The inlet's bypass network is a power-path detail, not a logic-supply
    decap, so the decap rule has nothing to enforce here — but EP does.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the eFuse exposed pad rule is actually exercised (not a no-op)
    assert r.checked.get("ep", 0) >= 1


def test_inlet_and_output_each_have_a_local_bypass(c: Circuit):
    """The inlet bypass network is present: +VBUS_CONN 100n (DS-minimum on IN),
    +VBUS_OUT 10u (dVdT-charged board bulk) — both to GND on this sheet."""
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
    """The SMBJ22A TVS sits across the RAW inlet VBUS (+VBUS_CONN -> GND), ahead
    of the eFuse — the hot-plug/surge clamp the eFuse's 67 V abs-max rides out."""
    d1 = c.parts["D1"]
    assert d1.value == "SMBJ22A"
    nets = {c.net_of(PinRef("D1", "1")).name, c.net_of(PinRef("D1", "2")).name}
    assert nets == {"+VBUS_CONN", "GND"}


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog (a part_rules.run on abstract rails reports caps as 'rail
    unresolved', so we assert the catalog coverage directly here)."""
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
    """The inlet/output bypass caps ride the live 20 V+5% = 21 V VBUS, so each
    must be voltage-rated for that rail (the subsystem's own RAIL_WORST_V) with
    a >=1.3x ceramic margin — the binding case is the 50 V X7R bulk."""
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
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (caps read as 'rail unresolved' on abstract rails — fail-soft —
    which is acceptable for a standalone subsystem)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt ↔ netlist passives --------------------------------------------

def _cir_caps() -> dict[str, float]:
    """Parse the .cir capacitor lines into {refdes: farads}."""
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
    """The .cir subckt declares the abstract ports as its pins (a project wires
    them to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt pd_input"))
    pins = header.split()[2:]
    assert pins == ["VBUS_CONN", "VBUS_OUT", "VDD_LOGIC", "CC1", "CC2",
                    "USB_D_P", "USB_D_N", "FLT_N", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in pd_input.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    """The subckt's cap network equals the netlist's caps, value-for-value (the
    .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and testpoint VALUES
    are preserved, and the nets dict keeps insertion order (byte-identical
    emit)."""
    base = pd_input.circuit()
    bound = pd_input.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; SIGNAL nets (the eFuse straps)
    # untouched; net insertion order preserved (byte-identical emit)
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the usb_hs_pair pair_with PAYLOAD followed the rename (no half-bound pair)
    assert bound.port_type_of("STM32_USB_D_P").pair_with == "STM32_USB_D_N"
    assert bound.port_type_of("STM32_USB_D_N").pair_with == "STM32_USB_D_P"
    # testpoint VALUES rebound to the real net names
    tp_values = {p.value for ref, p in bound.parts.items()
                 if p.lib_id == Circuit.TP_LIB_ID}
    assert tp_values == {"+VBUS_IN", "+VIN"}


def test_bind_identity_is_noop():
    base = pd_input.circuit()
    ident = pd_input.circuit({"bind": {n: n for n in pd_input.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    """notes["draws"] overrides the house-style prose without changing the
    netlist topology (a project restores its own derived-artifact wording)."""
    base = pd_input.circuit()
    m = pd_input.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)


def test_meta_expects_attaches_flt_deferral():
    """expects["FLT_N"] attaches an EXPLICIT linker deferral to the eFuse fault
    port (a project declares which of its sheets binds it)."""
    m = pd_input.circuit({"expects": {"FLT_N": "my_expander (port P15)"}})
    assert m.port_type_of("FLT_N").expect == "my_expander (port P15)"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        pd_input.circuit({"bus": {"i2c": "X"}})        # 'bus' is not a legal key


def test_bind_rejects_unknown_name():
    c = pd_input.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_SC"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. pd_input has
    real SIGNAL nets (the eFuse straps): binding one must be rejected."""
    c = pd_input.circuit()
    assert c.nets["PD_OVP_SET"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"PD_OVP_SET": "SOMETHING"})


def test_bind_rejects_collision():
    c = pd_input.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"CC1": "SHARED", "CC2": "SHARED"})


def test_bound_circuit_passes_local_design_rules(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local design-rule
    slice (binding is a pure rename; electrical completeness is unchanged)."""
    bound = pd_input.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
