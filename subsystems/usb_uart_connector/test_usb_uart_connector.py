"""LOCAL electrical-correctness test for the usb_uart_connector reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Mirrors subsystems/usb_pd/
test_usb_pd.py + subsystems/usbc_otg/test_usbc_otg.py so every migrated subsystem
follows the same shape.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC/connector pin netted-or-NC (model completeness), port types as
    declared (the USB 2.0 HS data pair typed usb_hs_pair).
  * device-role wiring            — two 5.1k Rd pulldowns to GND (UFP/device CC
    role, NOT a host's 56k Rp), the Type-C flip pairs shorted for USB 2.0, the
    VBUS bulk on the receptacle VBUS, the SBU pins author no-connects.
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: no
    floating config strap / dangling EP.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on the VBUS port is voltage-derated for it (the
    subsystem's own RAIL_WORST_V, since a board power tree is not present
    locally).
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, is order-preserving, AND re-points the diff-
    pair complement so the SI gate sees the project pair.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
peer-bridge linker graph (VBUS/USB_DP/USB_DM deferred onto the bridge sheet), the
full power-tree headroom, the SI spec join, board ERC and the board netlist
merge. Those are aggregated by `schgen board`.
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

import subsystems.usb_uart_connector.usb_uart_connector as usb_uart_connector

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_uart_connector.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/usb_uart_connector.py.
# The PORT values are the EXACT carrier net names the uart_bridge peer binds.
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
    """The standalone subsystem (abstract names)."""
    return usb_uart_connector.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library's INTERFACE."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usb_uart_connector.INTERFACE), externals
    # the abstract names must not be the carrier PORT net names
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
    # the USB 2.0 HS data pair is typed as a 90 ohm diff pair, mutually paired.
    dp = c.port_type_of("USB_DP")
    dm = c.port_type_of("USB_DM")
    assert dp.kind == "usb_hs_pair" and dm.kind == "usb_hs_pair"
    assert dp.pair_with == "USB_DM" and dm.pair_with == "USB_DP"
    assert dp.impedance == 90 and dm.impedance == 90


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the receptacle SBU pins are the only intentional no-connects (USB2 port).
    assert len(c.nc_pins) == 2
    # they resolve to physical pads on the receptacle, not floating ports.
    assert all(p.ref == "J1" for p in c.nc_pins)


def test_sbu_unused_by_design(c: Circuit):
    """SBU1/SBU2 are unused on a USB-2.0-only console (author no-connects)."""
    ncs = {str(p) for p in c.nc_pins}
    assert len(ncs) == 2 and all(n.startswith("J1.") for n in ncs)


# ---- device-role wiring ---------------------------------------------------------

def test_device_role_rd_pulldowns(c: Circuit):
    """UFP/device role: two 5.1k Rd from a CC line to GND (NOT a host's 56k Rp).
    Each Rd's free end is a private CC SIGNAL net; the other goes to GND."""
    rd = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":R"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if "GND" in nets and p.value == "5.1k":
            rd.append(ref)
    assert sorted(rd) == ["R1", "R2"], rd
    # the CC stubs are private SIGNAL nets (not exposed ports)
    cc_nets = {c.net_of(PinRef("R1", "1")).name, c.net_of(PinRef("R2", "1")).name}
    assert all(n.startswith("USB_UART_") for n in cc_nets), cc_nets
    assert all(c.nets[n].net_class is NetClass.SIGNAL for n in cc_nets)
    # NO host-side Rp anywhere (no resistor pulls a CC line up to VBUS)
    assert not any(p.value == "56k" for p in c.parts.values())


def test_data_pair_flip_shorted_through_esd(c: Circuit):
    """USB 2.0 on a Type-C device shorts the flip-orientation contacts (DP1=DP2,
    DN1=DN2) and routes each through the USBLC6-2SC6 (1<->6, 3<->4 passthrough);
    the protected pair is the exposed USB_DP/USB_DM ports. (The receptacle's
    named DP1/DP2 contacts expand to physical pads, both carried on one CONN
    net.)"""
    # the connector-side flip pairs are private SIGNAL nets, each merging both
    # flip pads of a line + one ESD passthrough pin.
    dp_conn = c.nets["USB_UART_DP_CONN"]
    assert dp_conn.net_class is NetClass.SIGNAL
    assert dp_conn is c.net_of(PinRef("U1", "1"))     # into ESD pin 1
    assert c.net_of(PinRef("U1", "6")).name == "USB_DP"   # protected pair out
    dm_conn = c.nets["USB_UART_DM_CONN"]
    assert dm_conn.net_class is NetClass.SIGNAL
    assert dm_conn is c.net_of(PinRef("U1", "3"))     # into ESD pin 3
    assert c.net_of(PinRef("U1", "4")).name == "USB_DM"   # protected pair out


def test_vbus_has_bulk_to_gnd(c: Circuit):
    """The receptacle VBUS carries a 10u bulk/bypass to GND (USB-C UFP Cbus),
    and the ESD array VBUS clamp ref + both receptacle VBUS pads are on it."""
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
    # VBUS spans the receptacle pad(s), the ESD VBUS clamp ref and the cap; the
    # receptacle's named VBUS contact expands to physical pads on the VBUS net.
    vbus_refs = {p.ref for p in c.nets["VBUS"].pins}
    assert {"J1", "U1", "C1"} <= vbus_refs, vbus_refs
    assert c.net_of(PinRef("U1", "5")).name == "VBUS"   # ESD VBUS clamp ref
    # ESD array GND ref on GND
    assert c.net_of(PinRef("U1", "2")).name == "GND"


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: no config strap floats and no dangling EP. (The receptacle
    + ESD array carry no decap-rule supply pin, so the rule examines 0 supply
    pins here — the VBUS bulk is asserted by test_vbus_has_bulk_to_gnd instead.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    """The VBUS bulk cap is voltage-rated for the worst-case VBUS voltage (the
    subsystem's own RAIL_WORST_V), with a >=1.3x ceramic margin. The 10u 0805
    25V cap on the ~5.25 V VBUS is the binding case."""
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
    """The .cir subckt declares the abstract ports as its pins (a project wires
    them to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt usb_uart_connector"))
    pins = header.split()[2:]
    assert pins == ["VBUS", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in usb_uart_connector.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's passive network equals the netlist's caps, value-for-value
    (the .cir cannot silently drift from the circuit)."""
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
    nothing else: part set, refs, NCs, port-type payloads are preserved, and the
    nets dict keeps insertion order (byte-identical emit)."""
    base = usb_uart_connector.circuit()
    bound = usb_uart_connector.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; internal SIGNAL nets keep their
    # name; net insertion order preserved (byte-identical emit).
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the internal CC/data SIGNAL nets are untouched by the bind (they keep the
    # verbatim USB_UART_*_CONN / USB_UART_R*_CC names the hand sheet used)
    assert all(n in bound.nets for n in base.nets if n.endswith("_CONN"))
    assert all(n in bound.nets for n in base.nets if n.endswith("_CC"))


def test_bind_repoints_diff_pair_complement():
    """The diff-pair complement (pair_with) is re-pointed through the bind map so
    the SI gate harvests the PROJECT pair {USB_UART_DP, USB_UART_DM}, not the
    stale abstract {USB_DP, USB_DM}."""
    bound = usb_uart_connector.circuit({"bind": _CARRIER_BIND})
    assert bound.port_type_of("USB_UART_DP").pair_with == "USB_UART_DM"
    assert bound.port_type_of("USB_UART_DM").pair_with == "USB_UART_DP"
    # standalone keeps the abstract complement
    base = usb_uart_connector.circuit()
    assert base.port_type_of("USB_DP").pair_with == "USB_DM"


def test_bind_identity_is_noop():
    base = usb_uart_connector.circuit()
    ident = usb_uart_connector.circuit(
        {"bind": {n: n for n in usb_uart_connector.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usb_uart_connector.circuit({"bnid": _CARRIER_BIND})   # 'bnid' != 'bind'


def test_bind_rejects_unknown_name():
    c = usb_uart_connector.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error.
    usb_uart_connector has real internal SIGNAL nets (the connector-side data +
    CC stubs, kept VERBATIM from the carrier sheet)."""
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
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = usb_uart_connector.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
