"""LOCAL electrical-correctness test for the usbc_otg reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Mirrors subsystems/usb_pd/
test_usb_pd.py so every migrated subsystem follows the same shape.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), port types as declared (the
    USB 2.0 HS data pair typed usb_hs_pair).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap to GND on the sheet, no floating config strap.
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
fault-flag / EN linker graph, the full power-tree headroom, the SI spec join,
board ERC and the board netlist merge. Those are aggregated by `schgen board`.
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

import subsystems.usbc_otg.usbc_otg as usbc_otg

HERE = Path(__file__).resolve().parent
CIR = HERE / "usbc_otg.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/usbc_otg.py.
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
    """The standalone subsystem (abstract names)."""
    return usbc_otg.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usbc_otg.INTERFACE), externals
    # the abstract names must not be carrier net names
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
    assert all(p.ref == "J2" for p in c.nc_pins)


def test_sbu_unused_by_design(c: Circuit):
    """SBU1/SBU2 are unused on a USB-2.0-only port (author no-connects)."""
    ncs = {str(p) for p in c.nc_pins}
    assert len(ncs) == 2 and all(n.startswith("J2.") for n in ncs)


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND and no config
    strap floats. (Linker-level checks — EN/FLT pull rails, the SI spec join —
    are board-level and are NOT asserted here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # (the TPS2051C IN is a switch input, not a decap-rule supply pin, so the
    #  rule examines 0 supply pins here — the bypass/bulk caps are asserted by
    #  test_power_switch_has_input_bypass_and_vbus_bulk instead.)


def test_power_switch_has_input_bypass_and_vbus_bulk(c: Circuit):
    """The datasheet network is present: TPS2051 IN 100n bypass and a 22u VBUS
    bulk — both to GND on this sheet."""
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
    assert caps_to_gnd("+VBUS_SUPPLY") == ["100n"]   # IN bypass
    assert caps_to_gnd("VBUS") == ["22u"]            # OUT bulk


def test_host_advertising_and_id_strap(c: Circuit):
    """CC1/CC2 carry 56k Rp to the sourced VBUS (default-USB host power) and the
    OTG ID is strapped low through 1k = host role."""
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
    # two 56k Rp from VBUS to the CC lines (private CC nets)
    rp = [p.value for ref, p in c.parts.items()
          if p.lib_id.endswith(":R") and "VBUS" in
          {n.name for n in (c.net_of(PinRef(ref, "1")),
                            c.net_of(PinRef(ref, "2"))) if n}
          and p.value == "56k"]
    assert sorted(rp) == ["56k", "56k"]
    # a single 1k ID strap to GND
    id_strap = [p.value for ref, p in c.parts.items()
                if p.lib_id.endswith(":R") and p.value == "1k" and "GND" in
                {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}]
    assert id_strap == ["1k"]


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
    """Each bypass/bulk cap is voltage-rated for the worst-case voltage of the
    rail it sits on (the subsystem's own RAIL_WORST_V), with a >=1.3x ceramic
    margin. The 22u VBUS bulk on the 5 V VBUS is the binding case."""
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
    """The .cir subckt declares the abstract ports as its pins (a project wires
    them to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt usbc_otg"))
    pins = header.split()[2:]
    assert pins == ["VBUS_SUPPLY", "VBUS", "VDD_LOGIC", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in usbc_otg.INTERFACE}
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
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = usbc_otg.circuit()
    bound = usbc_otg.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; internal SIGNAL nets keep their
    # name; net insertion order preserved (byte-identical emit).
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the internal CC/data SIGNAL nets are untouched by the bind
    assert all(n in bound.nets for n in base.nets if n.startswith("USBC_"))
    # the draw budgets followed the renamed rails
    assert "+5V_USB" in bound.loads and "+VBUS_SUPPLY" not in bound.loads
    assert "+3V3_SC" in bound.loads and "+VDD_LOGIC" not in bound.loads


def test_bind_repoints_diff_pair_complement():
    """The diff-pair complement (pair_with) is re-pointed through the bind map so
    the SI gate harvests the PROJECT pair {USB_D+, USB_D-}, not the stale
    abstract {USB_D+, USB_DM} (a bind() payload gap this subsystem closes)."""
    bound = usbc_otg.circuit({"bind": _CARRIER_BIND})
    assert bound.port_type_of("USB_D+").pair_with == "USB_D-"
    assert bound.port_type_of("USB_D-").pair_with == "USB_D+"
    # standalone keeps the abstract complement
    base = usbc_otg.circuit()
    assert base.port_type_of("USB_DP").pair_with == "USB_DM"


def test_bind_identity_is_noop():
    base = usbc_otg.circuit()
    ident = usbc_otg.circuit({"bind": {n: n for n in usbc_otg.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_notes_override_house_style():
    """The standard meta contract: notes["draws_*"] overrides the power-tree note
    without changing the netlist topology (a project restores its own wording)."""
    base = usbc_otg.circuit()
    m = usbc_otg.circuit({"notes": {"draws_vbus": "custom vbus",
                                    "draws_flt": "custom flt"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VBUS_SUPPLY"][0][1] == "custom vbus"   # (amps, note)
    assert m.loads["+VDD_LOGIC"][0][1] == "custom flt"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usbc_otg.circuit({"note": {"draws_vbus": "X"}})      # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = usbc_otg.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+5V_USB"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. usbc_otg has
    real internal SIGNAL nets (the connector-side data + CC stubs)."""
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
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = usbc_otg.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
