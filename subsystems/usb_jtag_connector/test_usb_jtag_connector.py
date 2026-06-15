"""LOCAL electrical-correctness test for the usb_jtag_connector reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Mirrors subsystems/usb_pd/ and
subsystems/usbc_otg/ so every migrated subsystem follows the same shape.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), port types as declared (the
    USB 2.0 HS data pair typed usb_hs_pair).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: no IC
    supply pin floats and no config strap floats on the sheet.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for that rail
    (the subsystem's own RAIL_WORST_V, since a board power tree is not present
    locally).
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, is order-preserving, AND re-points the diff-
    pair complement so the SI gate sees the project pair.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
USB-pair linker graph (the pair binds on the consumer sheet), the full power-tree
headroom, the SI spec join, board ERC and the board netlist merge. Those are
aggregated by `schgen board`.
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

import subsystems.usb_jtag_connector.usb_jtag_connector as ujc

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_jtag_connector.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/usb_jtag_connector.py.
_CARRIER_BIND = {
    "+VBUS": "+5V_DBG",
    "GND": "GND",
    "CHASSIS_GND": "CHASSIS_GND",
    "USB_DP": "DBG_USB_DP",
    "USB_DM": "DBG_USB_DM",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return ujc.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(ujc.INTERFACE), externals
    # the abstract names must not be carrier net names
    carrier = {"+5V_DBG", "DBG_USB_DP", "DBG_USB_DM"}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    grounds = {"GND", "CHASSIS_GND"}
    for rail in ujc.RAILS:
        want = NetClass.GROUND if rail in grounds else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in ujc.PORTS:
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
    # the receptacle SBU pins are the only intentional no-connects (USB2 link).
    assert len(c.nc_pins) == 2
    # they resolve to physical pads on the receptacle, not floating ports.
    assert all(p.ref == "J1" for p in c.nc_pins)


def test_sbu_unused_by_design(c: Circuit):
    """SBU1/SBU2 are unused on a USB-2.0-only debug link (author no-connects)."""
    ncs = {str(p) for p in c.nc_pins}
    assert len(ncs) == 2 and all(n.startswith("J1.") for n in ncs)


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: no IC supply pin or config strap floats on the sheet. The
    receptacle + USBLC6 array carry no decap-rule supply pin, so the rule examines
    0 supply pins here — the VBUS bulk is asserted by
    test_receptacle_has_vbus_bulk instead. (Linker-level checks — the SI spec
    join — are board-level and are NOT asserted here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_receptacle_has_vbus_bulk(c: Circuit):
    """The receptacle VBUS carries a 10u bulk/bypass to GND on this sheet."""
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
    assert caps_to_gnd("+VBUS") == ["10u"]


def test_device_role_rd_pulldowns(c: Circuit):
    """DEVICE/UFP role: BOTH CC pins carry a 5.1k Rd pulldown to GND (not a
    host's 56k Rp) — this is what tells the host to apply VBUS."""
    rd = [p.value for ref, p in c.parts.items()
          if p.lib_id.endswith(":R") and p.value == "5.1k" and "GND" in
          {n.name for n in (c.net_of(PinRef(ref, "1")),
                            c.net_of(PinRef(ref, "2"))) if n}]
    assert sorted(rd) == ["5.1k", "5.1k"]


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
    """Each bulk/bypass cap is voltage-rated for the worst-case voltage of the
    rail it sits on (the subsystem's own RAIL_WORST_V), with a >=1.3x ceramic
    margin. The 10u VBUS bulk on the 5 V VBUS is the binding case."""
    worst = ujc.RAIL_WORST_V
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
        if s.lower().startswith(".subckt usb_jtag_connector"):
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
                  if l.strip().lower().startswith(".subckt usb_jtag_connector"))
    pins = header.split()[2:]
    assert pins == ["VBUS", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in ujc.INTERFACE}
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
    subsystem (it has none — pure bulk/ESD network) and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and net order are
    preserved (byte-identical emit)."""
    base = ujc.circuit()
    bound = ujc.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; internal SIGNAL nets keep their
    # name; net insertion order preserved (byte-identical emit).
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the internal CC/data SIGNAL nets are untouched by the bind
    assert all(n in bound.nets for n in base.nets if n.startswith("DBG_"))
    # the TestPoint value followed the renamed rail (it carries the probed net)
    assert bound.parts["TP1"].value == "+5V_DBG"


def test_bind_repoints_diff_pair_complement():
    """The diff-pair complement (pair_with) is re-pointed through the bind map so
    the SI gate harvests the PROJECT pair {DBG_USB_DP, DBG_USB_DM}, not the stale
    abstract {DBG_USB_DP, USB_DM}."""
    bound = ujc.circuit({"bind": _CARRIER_BIND})
    assert bound.port_type_of("DBG_USB_DP").pair_with == "DBG_USB_DM"
    assert bound.port_type_of("DBG_USB_DM").pair_with == "DBG_USB_DP"
    # standalone keeps the abstract complement
    base = ujc.circuit()
    assert base.port_type_of("USB_DP").pair_with == "USB_DM"


def test_bind_identity_is_noop():
    base = ujc.circuit()
    ident = ujc.circuit({"bind": {n: n for n in ujc.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_expects_sets_pair_deferral():
    """The standard meta contract: expects["USB_DP"] sets the linker deferral on
    the typed pair without changing the netlist topology (a project names its own
    consuming sheet); both ends of the pair carry it."""
    base = ujc.circuit()
    assert base.port_type_of("USB_DP").expect == ujc.CONSUMER     # default
    m = ujc.circuit({"expects": {"USB_DP": "my_consumer_sheet"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("USB_DP").expect == "my_consumer_sheet"
    assert m.port_type_of("USB_DM").expect == "my_consumer_sheet"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        ujc.circuit({"expect": {"USB_DP": "X"}})      # 'expect' != 'expects'


def test_bind_rejects_unknown_name():
    c = ujc.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+5V_DBG"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error.
    usb_jtag_connector has real internal SIGNAL nets (the connector-side data +
    CC stubs)."""
    c = ujc.circuit()
    sig = next(n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL)
    assert sig.startswith("DBG_")
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({sig: "SOMETHING"})


def test_bind_rejects_collision():
    c = ujc.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"USB_DP": "SHARED", "USB_DM": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = ujc.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
