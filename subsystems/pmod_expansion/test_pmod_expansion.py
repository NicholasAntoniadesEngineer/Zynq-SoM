"""LOCAL electrical-correctness test for the pmod_expansion reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Mirrors subsystems/usb_pd/
test_usb_pd.py and subsystems/usbc_otg/test_usbc_otg.py so every migrated
subsystem follows the same shape.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), port types as declared (the
    eight PMOD_IO* are single-ended GPIO).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: no IC
    supply pin floats, no floating config strap (the SY6280 load-switch IN/OUT
    are switch pins, not decap-rule supply pins, so the bypass network is
    asserted directly by test_load_switch_bypass_present instead).
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for that rail
    (the subsystem's own RAIL_WORST_V, since a board power tree is not present
    locally).
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, is order-preserving, and a carrier-style bind
    keeps the internal SIGNAL wiring + the testpoint/draw budgets intact.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
PMOD_IO* link/port-driver graph (they bind on the generated SoM connector
sheet), the full power-tree headroom, board ERC and the board netlist merge.
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

import subsystems.pmod_expansion.pmod_expansion as pmod_expansion

HERE = Path(__file__).resolve().parent
CIR = HERE / "pmod_expansion.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/pmod_expansion.py.
_CARRIER_BIND = {
    "+VDD_PMOD": "+3V3",
    "+VSW_PMOD": "+3V3_PMODX",
    "GND": "GND",
    "PMOD_IO1": "PMODX_IO1", "PMOD_IO2": "PMODX_IO2",
    "PMOD_IO3": "PMODX_IO3", "PMOD_IO4": "PMODX_IO4",
    "PMOD_IO5": "PMODX_IO5", "PMOD_IO6": "PMODX_IO6",
    "PMOD_IO7": "PMODX_IO7", "PMOD_IO8": "PMODX_IO8",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return pmod_expansion.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(pmod_expansion.INTERFACE), externals
    # the abstract names must not be carrier net names
    carrier = {"+3V3", "+3V3_PMODX"} | {f"PMODX_IO{i}" for i in range(1, 9)}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in pmod_expansion.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in pmod_expansion.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    # the eight Pmod IO are single-ended GPIO (no diff/bus typing).
    for port in pmod_expansion.PORTS:
        assert c.port_type_of(port).kind == "single", port


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the only intentional no-connects: the three spare DSHP04 switch positions
    # (even pins NC) and pin 5 of each 4-channel TPD4E1U06 array.
    assert {str(p) for p in c.nc_pins} == {
        "SW1.2", "SW1.4", "SW1.6", "U2.5", "U3.5"}


def test_internal_signal_nets_present(c: Circuit):
    """The subsystem keeps its private wiring as SIGNAL nets (never bindable):
    the manual-enable net, the SY6280 ILIM-set node, and the status-LED node."""
    sigs = {n.name for n in c.nets.values()
            if n.net_class is NetClass.SIGNAL}
    assert sigs == {"EN_PMODX", "BS_ISET_PMODX", "BS_PG_PMODX"}, sigs


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: no IC supply pin floats and no config strap floats. (The
    SY6280 IN/OUT are switch pins, not decap-rule supply pins, so the rule
    examines 0 supply pins here — the bypass network is asserted by
    test_load_switch_bypass_present instead.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_load_switch_bypass_present(c: Circuit):
    """The datasheet network is present: the SY6280 IN carries 100n + 10u and
    the switched output rail carries 100n + 100n + 10u — all to GND on the
    sheet (the OUT bypass + the Pmod power-pin bypass/bulk share +VSW_PMOD)."""
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
    assert caps_to_gnd("+VDD_PMOD") == ["100n", "10u"]           # IN bypass+bulk
    assert caps_to_gnd("+VSW_PMOD") == ["100n", "100n", "10u"]   # OUT + Pmod pins


def test_two_esd_arrays_clamp_all_eight_io(c: Circuit):
    """Each of the eight Pmod IO is GND-clamped: two TPD4E1U06 (4 channels each)
    cover the 8 IO, and each clamp is a pure GND-referenced shunt (a PMOD_IO net
    touches an ESD-array channel pin, never in series)."""
    esd_refs = {ref for ref, p in c.parts.items()
                if p.value == "TPD4E1U06"}
    assert esd_refs == {"U2", "U3"}, esd_refs
    # both arrays grounded on pin 2
    for ref in esd_refs:
        assert c.net_of(PinRef(ref, "2")).name == "GND"
    # every PMOD_IO* port reaches an ESD-array channel pin
    for port in pmod_expansion.PORTS:
        pins = c.nets[port].pins
        assert any(p.ref in esd_refs for p in pins), (port, pins)


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
    margin (both rails are 3.3 V-class LVCMOS33)."""
    worst = pmod_expansion.RAIL_WORST_V
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
        if s.lower().startswith(".subckt pmod_expansion"):
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
                  if l.strip().lower().startswith(".subckt pmod_expansion"))
    pins = header.split()[2:]
    assert pins == ["VDD_PMOD", "VSW_PMOD", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in pmod_expansion.INTERFACE}
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
    subsystem (pure bypass network) and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, the internal SIGNAL nets keep their names, and the nets dict keeps
    insertion order (byte-identical emit)."""
    base = pmod_expansion.circuit()
    bound = pmod_expansion.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; internal SIGNAL nets keep their
    # name; net insertion order preserved (byte-identical emit).
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the internal SIGNAL nets are untouched by the bind
    for sig in ("EN_PMODX", "BS_ISET_PMODX", "BS_PG_PMODX"):
        assert sig in bound.nets
    # the draw budget followed the renamed switched rail
    assert "+3V3_PMODX" in bound.loads and "+VSW_PMOD" not in bound.loads


def test_bind_repoints_testpoint_value():
    """The testpoint on the gated rail carries the probed net NAME as its value;
    a carrier bind re-points it so the render is byte-identical (LAW 0)."""
    bound = pmod_expansion.circuit({"bind": _CARRIER_BIND})
    tp = next(p for p in bound.parts.values()
              if p.lib_id == Circuit.TP_LIB_ID)
    assert tp.value == "+3V3_PMODX"


def test_bind_identity_is_noop():
    base = pmod_expansion.circuit()
    ident = pmod_expansion.circuit(
        {"bind": {n: n for n in pmod_expansion.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    """The standard meta contract: notes["draws_pmod"] overrides the power-tree
    note without changing the netlist topology (a project restores its own
    wording)."""
    base = pmod_expansion.circuit()
    m = pmod_expansion.circuit({"notes": {"draws_pmod": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VSW_PMOD"][0][1] == "custom note"   # (amps, note)


def test_meta_expects_attaches_port_deferral():
    """The standard meta contract: expects[PMOD_IOx] attaches an explicit linker
    deferral to that port (forwarded into c.port(..., expect=...))."""
    m = pmod_expansion.circuit({"expects": {"PMOD_IO1": "my_connector"}})
    assert m.port_type_of("PMOD_IO1").expect == "my_connector"
    # an unlisted port carries no deferral
    assert m.port_type_of("PMOD_IO2").expect is None


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        pmod_expansion.circuit({"note": {"draws_pmod": "X"}})  # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = pmod_expansion.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error.
    pmod_expansion has real internal SIGNAL nets (the manual-enable + ILIM-set +
    LED stubs)."""
    c = pmod_expansion.circuit()
    sig = next(n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL)
    assert sig in ("EN_PMODX", "BS_ISET_PMODX", "BS_PG_PMODX")
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({sig: "SOMETHING"})


def test_bind_rejects_collision():
    c = pmod_expansion.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"PMOD_IO1": "SHARED", "PMOD_IO2": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = pmod_expansion.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
