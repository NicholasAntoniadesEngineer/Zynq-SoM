"""LOCAL electrical-correctness test for the rj45_connector reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so a
future migration of any other subsystem follows the same shape. See
subsystems/usb_pd/test_usb_pd.py for the worked exemplar and
subsystems/ethernet/test_ethernet.py for the diff-pair sibling.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every part pin netted-or-NC (model completeness), the pin-FAITHFUL T568
    contact -> MDI mapping, the 4 line-side differential MDI pairs typed as
    declared, the two housing-LED anode nodes kept PRIVATE SIGNAL.
  * LED port-present indicator     — each housing LED is a 330R from +VLED to its
    anode node and the cathode returns to GND (no discrete diode — it lives
    inside J1), and the four M3 mounting holes + the shell bond to CHASSIS_GND.
  * design-rule slice              — DECAP/EP/STRAP raise nothing (a passive
    connector + series resistors has no IC supply pin / exposed pad / config
    strap), and part_rules raises no hard finding.
  * part ratings                   — every BOM passive's LCSC resolves in the
    ratings catalog.
  * SPICE passives                 — the .cir subckt's resistor network matches
    the netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract              — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, threads the per-pair linker deferral, and a
    carrier-style bind is order-preserving (byte-identical emit).

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph (the line-side MDI pairs face the ethernet magnetics
sheet), the full SI pair set, the full power-tree headroom, board ERC and the
board netlist merge. Those are aggregated by `schgen board`.
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

import subsystems.rj45_connector.rj45_connector as rj45_connector

HERE = Path(__file__).resolve().parent
CIR = HERE / "rj45_connector.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/rj45_connector.py. The
# LED supply rides the carrier +3V3; the line-side pairs face the ethernet
# magnetics media side (ETH_LINE_MDI_n); GND/CHASSIS_GND are identity binds.
_CARRIER_BIND = {
    "+VLED": "+3V3",
    "GND": "GND",
    "CHASSIS_GND": "CHASSIS_GND",
    "RJ45_MDI0_P": "ETH_LINE_MDI_0_P", "RJ45_MDI0_N": "ETH_LINE_MDI_0_N",
    "RJ45_MDI1_P": "ETH_LINE_MDI_1_P", "RJ45_MDI1_N": "ETH_LINE_MDI_1_N",
    "RJ45_MDI2_P": "ETH_LINE_MDI_2_P", "RJ45_MDI2_N": "ETH_LINE_MDI_2_N",
    "RJ45_MDI3_P": "ETH_LINE_MDI_3_P", "RJ45_MDI3_N": "ETH_LINE_MDI_3_N",
}

# A linker deferral threaded through meta.expect_kw (only the P net of each pair
# is named; the reciprocal N inherits it). Used only to exercise the threading.
_MAGNETICS_DEFER = "ethernet (magnetics media side)"
_CARRIER_EXPECTS = {f"RJ45_MDI{n}_P": _MAGNETICS_DEFER for n in range(4)}

# faithful T568 / IEEE 802.3 1000BASE-T contact -> MDI pair mapping (the same
# table the netlist drives MDI_CONTACTS from).
_CONTACTS = {
    1: "RJ45_MDI0_P", 2: "RJ45_MDI0_N",
    3: "RJ45_MDI1_P", 6: "RJ45_MDI1_N",
    4: "RJ45_MDI2_P", 5: "RJ45_MDI2_N",
    7: "RJ45_MDI3_P", 8: "RJ45_MDI3_N",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return rj45_connector.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(rj45_connector.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert not any(n.startswith("ETH_LINE") or n == "+3V3" for n in externals), \
        externals
    # the two housing-LED anode nodes stay PRIVATE SIGNAL wiring
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert {"RJ45_LED_L", "RJ45_LED_R"} == signals, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    # +VLED is the LED supply (POWER); GND/CHASSIS_GND are both GROUND, with
    # CHASSIS_GND a SEPARATE net from signal GND (star-bonded by the board).
    assert cls["+VLED"] is NetClass.POWER, cls["+VLED"]
    assert cls["GND"] is NetClass.GROUND, cls["GND"]
    assert cls["CHASSIS_GND"] is NetClass.GROUND, cls["CHASSIS_GND"]
    for port in rj45_connector.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_mdi_pairs_typed(c: Circuit):
    """All 4 line-side MDI pairs are 100 Ω diff_pairs with the P<->N reciprocal
    type registered automatically."""
    for n in range(4):
        pp, pn = f"RJ45_MDI{n}_P", f"RJ45_MDI{n}_N"
        tp, tn = c.port_type_of(pp), c.port_type_of(pn)
        assert tp.kind == "diff_pair" and tn.kind == "diff_pair", (pp, pn)
        assert tp.impedance == 100 and tn.impedance == 100, (pp, pn)
        assert tp.pair_with == pn and tn.pair_with == pp, (pp, pn)


def test_t568_contact_mapping_faithful(c: Circuit):
    """LAW 0 — the FAITHFUL KH-5224-8P8C-D pinout: each of the eight T568
    contacts lands on its IEEE 802.3 1000BASE-T MDI net, and the jack is the
    single genuine Kinghelm part (no invented pins)."""
    for pin, net in _CONTACTS.items():
        assert PinRef("J1", str(pin)) in c.nets[net].pins, (pin, net)
    assert "KH-5224-8P8C-D" in c.parts["J1"].lib_id


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats). A plain
    jack has NO no-connect — all 13 pins (8 contacts + 4 LED + shell) are used."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == set(), c.nc_pins


# ---- LED port-present indicator + chassis bond ----------------------------------

def test_housing_leds_are_330r_indicators(c: Circuit):
    """Each integrated housing LED is driven steady from +VLED through a 330R
    into its anode node, cathode to GND — NO discrete diode (it lives inside
    J1). The two indicators are R1/R2 onto J1.9 / J1.11."""
    for ref, anode_node, anode_pin, cath_pin in (
            ("R1", "RJ45_LED_L", "9", "10"),
            ("R2", "RJ45_LED_R", "11", "12")):
        assert c.parts[ref].value == "330R", ref
        # 330R: +VLED -> internal anode node
        assert PinRef(ref, "1") in c.nets["+VLED"].pins, ref
        anode = {str(p) for p in c.nets[anode_node].pins}
        assert f"{ref}.2" in anode and f"J1.{anode_pin}" in anode, (ref, anode)
        # cathode returns to signal GND
        assert PinRef("J1", cath_pin) in c.nets["GND"].pins, cath_pin
    # no discrete LED part was added (the diode is inside the connector)
    assert not any(p.lib_id.endswith(":LED") for p in c.parts.values())


def test_shield_and_mounting_holes_on_chassis(c: Circuit):
    """The shell/shield (J1.13) and the four M3 corner mounting holes bond to
    the chassis island (CHASSIS_GND), kept separate from signal GND."""
    ch = c.nets["CHASSIS_GND"].pins
    assert PinRef("J1", "13") in ch, ch
    holes = sorted(ref for ref in c.parts if ref.startswith("H"))
    assert holes == ["H1", "H2", "H3", "H4"], holes
    for h in holes:
        assert PinRef(h, "1") in ch, h
        # mounting holes are BOM-excluded chassis-bond fab-art
        assert c.parts[h].fields.get("BOM") == "exclude", h


# ---- design-rule + part-rating slices -------------------------------------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """A passive connector + series resistors has no IC supply pin, no exposed
    pad and no config strap, so DECAP/EP/STRAP raise nothing."""
    r = design_rules.check([_sheet(c)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings


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


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (the only BOM passives are two 330R indicator resistors)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt ↔ netlist passives --------------------------------------------

def _cir_resistors() -> dict[str, float]:
    """Parse the .cir resistor lines (R1/R2 — the board-added passives) into
    {refdes: ohms}. (RSTAR / RSHIELD-style model elements are not BOM parts.)"""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt rj45_connector"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^R\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    """The .cir subckt declares the abstract ports as its pins (a project wires
    them to real nets, exactly as the netlist bind does). The header spans a
    continuation line ('+')."""
    lines = CIR.read_text().splitlines()
    hdr_idx = next(i for i, l in enumerate(lines)
                   if l.strip().lower().startswith(".subckt rj45_connector"))
    header = lines[hdr_idx].split()[2:]
    j = hdr_idx + 1
    while j < len(lines) and lines[j].lstrip().startswith("+"):
        header += lines[j].lstrip()[1:].split()
        j += 1
    assert header == [
        "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N", "MDI2_P", "MDI2_N",
        "MDI3_P", "MDI3_N", "VLED", "GND", "CHASSIS_GND"], header
    # every subckt pin is a real abstract interface net (sans the '+' rail mark
    # and the RJ45_ MDI prefix the netlist uses)
    iface = {n.lstrip("+").removeprefix("RJ45_") for n in rj45_connector.INTERFACE}
    assert all(p in iface for p in header), header


def test_cir_resistors_match_netlist(c: Circuit):
    """The subckt's series resistors equal the netlist's 330R indicators,
    value-for-value (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":R"))
    cir = sorted(_cir_resistors().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type pair_with payloads and draw
    budgets are preserved, and the nets dict keeps insertion order (byte-
    identical emit). SIGNAL nets (RJ45_LED_L/R) are private and keep their
    names."""
    base = rj45_connector.circuit()
    bound = rj45_connector.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; order preserved (SIGNAL nets keep
    # their name — only the externals in the bind map move)
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the diff-pair typing + reciprocal survive the rename (pair_with rebound)
    assert bound.port_type_of("ETH_LINE_MDI_0_P").pair_with == "ETH_LINE_MDI_0_N"
    assert bound.port_type_of("ETH_LINE_MDI_0_N").pair_with == "ETH_LINE_MDI_0_P"
    assert bound.port_type_of("ETH_LINE_MDI_2_P").impedance == 100
    # the draw budget followed the renamed rail
    assert "+3V3" in bound.loads and "+VLED" not in bound.loads


def test_bind_with_expects_threads_pair_deferral():
    """A linker deferral threads via meta.expect_kw: only the P net of each pair
    is named, and the reciprocal N inherits it."""
    bound = rj45_connector.circuit({"bind": _CARRIER_BIND,
                                    "expects": _CARRIER_EXPECTS})
    for n in range(4):
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_P").expect == _MAGNETICS_DEFER
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_N").expect == _MAGNETICS_DEFER


def test_meta_notes_override_draws(c: Circuit):
    """notes["draws"] overrides the power-tree note without changing topology."""
    base = rj45_connector.circuit()
    m = rj45_connector.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VLED"][0][1] == "custom note"   # (amps, note)


def test_bind_identity_is_noop():
    base = rj45_connector.circuit()
    ident = rj45_connector.circuit(
        {"bind": {n: n for n in rj45_connector.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        rj45_connector.circuit({"bus": {"x": "Y"}})        # no such key


def test_bind_rejects_unknown_name():
    c = rj45_connector.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. rj45's
    housing-LED anode nodes (RJ45_LED_L/R) are SIGNAL, so try to bind one."""
    c = rj45_connector.circuit()
    assert c.nets["RJ45_LED_L"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"RJ45_LED_L": "SOMETHING"})


def test_bind_rejects_collision():
    c = rj45_connector.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"RJ45_MDI0_P": "SHARED", "RJ45_MDI0_N": "SHARED"})
