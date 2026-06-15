"""LOCAL electrical-correctness test for the hdmi_rx reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). Co-located with the
package so a future migration of any other subsystem follows the same shape.
See subsystems/hdmi_tx/test_hdmi_tx.py (the source-side sibling) + usb_pd for
the worked exemplars.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC/connector pin netted-or-NC (model completeness), port types as
    declared (the 4 TMDS RX pairs). The DDC I2C, HPD assert and cable-5V quasi-
    rail are PRIVATE SIGNAL wiring (connector<->EEPROM<->ESD on this sheet).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: the EEPROM
    cable-5V supply has its local bypass to GND, no floating config strap.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap is voltage-derated for the rail it sits on.
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.
  * the schgen:HDMI_A_RX override — J1's hand-built symbol override is preserved
    VERBATIM (a tracked PENDING_MIGRATION; the deep-engine task migrates it).

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
DDC pull-up completeness (DDC is SOURCE-mastered, off-board), the TMDS sink
termination (placed at the receiver bank, off-sheet — SI-HDMIRX-TERM), the
link/port-driver graph, the full power-tree headroom, board ERC and the board
netlist merge. Those are aggregated by `schgen board`.
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

import subsystems.hdmi_rx.hdmi_rx as hdmi_rx

HERE = Path(__file__).resolve().parent
CIR = HERE / "hdmi_rx.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/hdmi_rx.py.
_CARRIER_BIND = {
    "+VDD_LOGIC": "+3V3_HDMI_RX",
    "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
    "TMDS_RX_D2_P": "HDMI_RX_D2_P", "TMDS_RX_D2_N": "HDMI_RX_D2_N",
    "TMDS_RX_D1_P": "HDMI_RX_D1_P", "TMDS_RX_D1_N": "HDMI_RX_D1_N",
    "TMDS_RX_D0_P": "HDMI_RX_D0_P", "TMDS_RX_D0_N": "HDMI_RX_D0_N",
    "TMDS_RX_CLK_P": "HDMI_RX_CLK_P", "TMDS_RX_CLK_N": "HDMI_RX_CLK_N",
    "HDMI_5V_DET": "HDMI_RX_5V_DET",
    "CEC": "HDMI_RX_CEC",
}

# The four PRIVATE SIGNAL nets the library keeps verbatim (DDC bus is source-
# mastered, HPD is 5-V-domain, cable-5V is a quasi-rail) — never part of the
# bind contract.
_PRIVATE_SIGNAL = {"HDMI_RX_SDA", "HDMI_RX_SCL", "HDMI_RX_5V", "HDMI_RX_HPD"}

# Worst-case voltage of each abstract RAIL + the cable-5V node — the subsystem's
# own electrical contract. Used by the local test to derate the bypass cap
# without depending on a board power tree.
RAIL_WORST_V = {"+VDD_LOGIC": 3.3, "GND": 0.0, "CHASSIS_GND": 0.0}
CABLE_5V_NODE = "HDMI_RX_5V"     # the cable's +5V quasi-rail (5.25 V max)
CABLE_5V_WORST_V = 5.25


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return hdmi_rx.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(hdmi_rx.INTERFACE), externals
    # the abstract port names must not be carrier net names (the carrier ports
    # are +3V3_HDMI_RX / HDMI_RX_* — none of the abstract externals carry those)
    assert not any(n.startswith("+3V3_HDMI_RX") or n.startswith("HDMI_RX_")
                   for n in externals), externals
    # the DDC bus, HPD assert and cable-5V quasi-rail stay PRIVATE SIGNAL wiring
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == _PRIVATE_SIGNAL, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in hdmi_rx.RAILS:
        want = NetClass.GROUND if rail in ("GND", "CHASSIS_GND") \
            else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in hdmi_rx.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_tmds_pairs_typed(c: Circuit):
    """The 4 TMDS RX lanes are 100 ohm tmds_pairs (P<->N reciprocal). There is no
    on-sheet DDC i2c typing — DDC is source-mastered and stays private SIGNAL."""
    for p_pos, p_neg in hdmi_rx.TMDS_PAIRS:
        tp, tn = c.port_type_of(p_pos), c.port_type_of(p_neg)
        assert tp.kind == "tmds_pair" and tn.kind == "tmds_pair"
        assert tp.impedance == 100 and tn.impedance == 100
        assert tp.pair_with == p_neg and tn.pair_with == p_pos
    # the slow control ports are plain single-ended
    assert c.port_type_of("CEC").kind == "single"
    assert c.port_type_of("HDMI_5V_DET").kind == "single"


def test_tmds_lane_is_one_dc_coupled_net(c: Circuit, lib: Library):
    """LAW 0: each TMDS RX lane is exactly TWO pins — the receptacle (J1) and the
    low-cap ESD shunt pad (U2/U3): connector -> ESD tap -> receiver, no series
    split (the lane stays DC-coupled, a shunt TAP not a series break). The ESD
    IO pin names resolve to the array's pad numbers via the symbol pin table."""
    for net, jpin, esd_ref, esd_io in hdmi_rx.TMDS_LANES:
        pins = {str(p) for p in c.nets[net].pins}
        assert len(pins) == 2, (net, pins)
        assert f"J1.{jpin}" in pins, (net, pins)
        # the other pin is on the ESD array (a real pad of that ref)
        other = (pins - {f"J1.{jpin}"}).pop()
        ref, _, pad = other.partition(".")
        assert ref == esd_ref, (net, pins)
        assert pad in lib.pin_numbers(c.parts[esd_ref].lib_id), (net, other)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the intentional no-connects: HDMI pin 14 (HEC/Utility reserved) + the spare
    # USON-10 pads of the three ESD arrays (the '.NC' alias resolves to pads
    # 6/7/9/10 on each TPD4Exx array; datasheet: float/GND OK).
    nc = {str(p) for p in c.nc_pins}
    assert "J1.14" in nc, nc
    for ref in ("U2", "U3", "U4"):
        assert {f"{ref}.{pad}" for pad in ("6", "7", "9", "10")} <= nc, (ref, nc)
    # exactly those: HDMI pin 14 + 4 spare pads on each of the 3 ESD arrays
    assert nc == {"J1.14"} | {
        f"{ref}.{pad}" for ref in ("U2", "U3", "U4")
        for pad in ("6", "7", "9", "10")}, nc


def test_edid_wc_hardwired_to_cable_5v(c: Circuit):
    """COMP-1 (LAW 0): the EDID WC# (U1.7) is HARDWIRED to the EEPROM's own
    cable-5 V VCC node (U1.8) — write-protect tracks VCC, not a gated 3.3 V rail.
    Both pins must land on the SAME private cable-5V net, with no resistor."""
    n7 = c.net_of(PinRef("U1", "7"))
    n8 = c.net_of(PinRef("U1", "8"))
    assert n7 is not None and n8 is not None
    assert n7.name == n8.name == CABLE_5V_NODE, (n7, n8)
    assert n7.net_class is NetClass.SIGNAL          # private quasi-rail


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: the EEPROM cable-5V supply pin has a local cap-to-GND, no
    config strap floats. (DDC I2C-pull-ups are board-level — SOURCE-mastered, off
    this sheet — so that rule is not asserted here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the supply rail is actually exercised (not a no-op)
    assert r.checked.get("decap", 0) >= 1


def test_eeprom_cable5v_has_a_local_bypass(c: Circuit):
    """The EEPROM cable-5 V VCC node carries its 100n bypass to GND on-sheet."""
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
    assert caps_to_gnd(CABLE_5V_NODE) == ["100n"]


def test_presence_divider_and_cec_pullup(c: Circuit):
    """The cable-5V presence divider (10k top / 15k bottom -> HDMI_5V_DET) and
    the CEC 27k pull-up to the gated module rail are present as netted."""
    # 10k from the cable-5V node to the detect port, 15k from the port to GND
    def res_between(val, a, b):
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":R") or p.value != val:
                continue
            nets = {n.name for n in
                    (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))) if n}
            if {a, b} <= nets:
                return ref
        return None
    assert res_between("10k", CABLE_5V_NODE, "HDMI_5V_DET")
    assert res_between("15k", "HDMI_5V_DET", "GND")
    assert res_between("27k", "CEC", "+VDD_LOGIC")
    # the HPD passive assert: 1k from the cable-5V node to the (private) HPD net
    assert res_between("1k", CABLE_5V_NODE, "HDMI_RX_HPD")


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
    """Each bypass cap is voltage-rated for the worst-case voltage of the node it
    sits on (RAIL_WORST_V + the 5.25 V cable-5V node), with a >=1.3x ceramic
    margin. The lone bypass C1 rides the cable's +5 V quasi-rail."""
    worst = dict(RAIL_WORST_V)
    worst[CABLE_5V_NODE] = CABLE_5V_WORST_V
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = [c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2"))]
        rail_v = max((worst.get(n.name, 0.0) for n in nets if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V node "
            f"(<1.3x margin)")


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (caps read as 'rail unresolved' on abstract rails — fail-soft —
    which is acceptable for a standalone subsystem)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt <-> netlist passives ------------------------------------------

def _cir_passives(prefix: str) -> dict[str, float]:
    """Parse the .cir C/R lines (by refdes prefix) into {refdes: value}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt hdmi_rx"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(rf"^{prefix}\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    """The .cir subckt declares the abstract externals (that carry passives) as
    its pins (a project wires them to real nets, exactly as the netlist bind
    does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt hdmi_rx"))
    pins = header.split()[2:]
    assert pins == ["VDD_LOGIC", "HDMI_5V_DET", "CEC", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in hdmi_rx.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    """The subckt's capacitor network equals the netlist's caps, value-for-value
    (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives("C").values())
    assert cir == netlist, (cir, netlist)


def test_cir_resistors_match_netlist(c: Circuit):
    """The subckt's resistor network equals the netlist's resistors, value-for-
    value (the divider/pull-up/assert R's cannot silently drift)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":R"))
    cir = sorted(_cir_passives("R").values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the schgen:HDMI_A_RX symbol override (PENDING_MIGRATION) --------------------

def test_hdmi_a_rx_lib_id_override_preserved(c: Circuit):
    """The HDMI receptacle J1 keeps its hand-built schgen:HDMI_A_RX symbol
    override VERBATIM — a tracked PENDING_MIGRATION (symbol_law). The deep-engine
    task migrates it later; this package must NOT change it."""
    assert c.parts["J1"].lib_id == "schgen:HDMI_A_RX"
    assert hdmi_rx.J_LIB == "schgen:HDMI_A_RX"


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, lib_ids, NCs, port-type payloads and draw
    budgets are preserved, and the nets dict keeps insertion order (byte-identical
    emit). The PRIVATE SIGNAL nets keep their library names."""
    base = hdmi_rx.circuit()
    bound = hdmi_rx.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs/lib_ids (incl. the schgen:HDMI_A_RX override)
    assert set(bound.parts) == set(base.parts)
    assert {r: p.lib_id for r, p in bound.parts.items()} == \
           {r: p.lib_id for r, p in base.parts.items()}
    assert bound.parts["J1"].lib_id == "schgen:HDMI_A_RX"
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; order preserved (SIGNAL nets are
    # private and keep their name — only the externals in the bind map move)
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the private SIGNAL nets survive untouched
    assert _PRIVATE_SIGNAL <= set(bound.nets)
    # the TMDS pair typing survives the rename
    assert bound.port_type_of("HDMI_RX_D2_P").kind == "tmds_pair"
    assert bound.port_type_of("HDMI_RX_D2_P").pair_with == "HDMI_RX_D2_N"
    # the draw budget followed the renamed rail
    assert "+3V3_HDMI_RX" in bound.loads and "+VDD_LOGIC" not in bound.loads


def test_bind_identity_is_noop():
    base = hdmi_rx.circuit()
    ident = hdmi_rx.circuit({"bind": {n: n for n in hdmi_rx.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    """The standard meta contract: notes["draws"] overrides the power-tree note
    without changing the netlist topology (a project restores its own house-style
    metadata)."""
    base = hdmi_rx.circuit()
    m = hdmi_rx.circuit({"notes": {"draws": "custom draw note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VDD_LOGIC"][0][1] == "custom draw note"   # (amps, note)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        hdmi_rx.circuit({"note": {"draws": "X"}})        # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = hdmi_rx.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. hdmi_rx's
    DDC/HPD/cable-5V lines are SIGNAL, so try to bind one."""
    c = hdmi_rx.circuit()
    assert c.nets["HDMI_RX_SDA"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"HDMI_RX_SDA": "SOMETHING"})


def test_bind_rejects_collision():
    c = hdmi_rx.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"TMDS_RX_D2_P": "SHARED", "TMDS_RX_D2_N": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = hdmi_rx.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
