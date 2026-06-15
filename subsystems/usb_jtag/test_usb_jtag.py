"""LOCAL electrical-correctness test for the usb_jtag reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so a
migration of any other subsystem follows the same shape (mirrors
subsystems/usb_pd/test_usb_pd.py and subsystems/uart_bridge/test_uart_bridge.py).

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    the USB HS pair typed, every IC pin netted-or-NC (model completeness).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap to GND, no config strap floats, the CH347 RST#
    waiver is honoured (no spurious reset finding).
  * part ratings                  — every BOM passive (except the documented
    crystal-load caps, which the board itself treats as a soft no-ratings note)
    resolves in the ratings catalog and each island-rail cap is voltage-derated.
  * SPICE passives                — the .cir subckt's passive caps match the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, is order-preserving, the USB HS pair's
    pair_with payload follows the bind, and the testpoint VALUES follow the bind.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph, the full power-tree headroom, the SI length-match
emission, board ERC and the board netlist merge — all aggregated by `schgen
board`.
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

import subsystems.usb_jtag.usb_jtag as usb_jtag

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_jtag.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/usb_jtag.py.
_CARRIER_BIND = {
    "+VBUS_USB": "+5V_DBG", "+3V3_ISLAND": "+3V3_DBG", "GND": "GND",
    "USB_DP": "DBG_USB_DP", "USB_DM": "DBG_USB_DM",
    "JTAG_TCK": "ZYNQ_TCK", "JTAG_TDI": "ZYNQ_TDI",
    "JTAG_TMS": "ZYNQ_TMS", "JTAG_TDO": "ZYNQ_TDO",
    "UART_RXD": "DBG_UART_RXD", "UART_TXD": "DBG_UART_TXD",
}

# The subsystem's own electrical contract: the island rail is 3.3 V class (a
# project may name it whatever its local LDO-output net is) and the VBUS input
# is the debug cable's own 5 V. Used by the local test to derate the bypass caps
# without depending on a board power tree.
RAIL_WORST_V = {"+VBUS_USB": 5.5, "+3V3_ISLAND": 3.6, "GND": 0.0}

# The 16 pF crystal-load caps (LCSC C162205) are NOT in the ratings catalog;
# the board's own part_rules emits a SOFT "no ratings row" note for them (not a
# hard finding — see carrier/reports/part_rules.txt). The local test mirrors
# that: it does NOT require these to resolve (LAW 4 — not softening a gate, just
# matching the board's existing soft treatment of this exact LCSC).
_CRYSTAL_CAP_LCSC = "C162205"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return usb_jtag.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usb_jtag.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert not any(n.startswith("ZYNQ") or n.startswith("DBG_")
                   or n.endswith("_DBG") for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in usb_jtag.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in usb_jtag.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    # the USB data lines form a USB 2.0 HS differential pair
    dp = c.port_type_of("USB_DP")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "USB_DM"
    assert c.port_type_of("USB_DM").pair_with == "USB_DP"
    # the JTAG + UART signals are plain single-ended ports
    for p in ("JTAG_TCK", "JTAG_TDI", "JTAG_TMS", "JTAG_TDO",
              "UART_RXD", "UART_TXD"):
        assert c.port_type_of(p).kind == "single", p


def test_internal_signal_nets_stay_private(c: Circuit):
    """The CH347 channel-A JTAG taps, the crystal nodes, the RST# / MODE-strap /
    OE nodes are PRIVATE SIGNAL nets (not externals): verbatim DBG_* names, never
    part of the abstract interface."""
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == {
        "DBG_FT_TCK", "DBG_FT_TDI", "DBG_FT_TMS", "DBG_FT_TDO",
        "DBG_JTAG_OE_N", "DBG_MODE_DTR1", "DBG_MODE_RTS1", "DBG_RST_N",
        "DBG_XI", "DBG_XO"}, signals
    assert not (signals & set(usb_jtag.INTERFACE))


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the unused CH347 pins, the LDO NC, and the six unused DSHP04 positions
    assert {str(p) for p in c.nc_pins} == {
        "U1.2", "U1.9", "U1.11", "U1.12", "U1.15", "U4.4",
        "SW1.2", "SW1.3", "SW1.4", "SW1.5", "SW1.6", "SW1.7"}


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND, no config
    strap floats, and the CH347 RST# waiver is honoured (no spurious reset
    finding)."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the supply rails are actually exercised (CH347 VCC, buffer VCC, LDO out)
    assert r.checked.get("decap", 0) >= 3


def test_island_rail_has_full_bypass(c: Circuit):
    """The 3.3 V island rail carries the LDO Cout (10u) + bulk/decoupling caps:
    10u + 100n (LDO out) + 100n (CH347 VCC) + 100n (buffer VCC) — all to GND."""
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
    assert caps_to_gnd("+VBUS_USB") == ["1u"]          # LDO Cin on the 5 V VBUS


def test_mode_strap_and_oe_pulls(c: Circuit):
    """The MODE-3 strap (DTR1/RTS1 each 10k -> GND) and the OE# default-HIGH
    100k pull-up to the island rail are present (the contention guard + the
    JTAG+UART enumeration strap)."""
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
    """CH347 RST# is a defined-high reset with the 10k external pull-up only
    (internal POR; no RC cap) — the design-rule reset waiver must be declared so
    the local decoupling slice does NOT flag DBG_RST_N."""
    assert "DBG_RST_N" in c.reset_waivers
    # and a 10k pull-up to the island rail actually exists on that node
    pulls = [p for ref, p in c.parts.items()
             if p.lib_id == "Device:R" and p.value == "10k"
             and {"+3V3_ISLAND", "DBG_RST_N"} == {
                 n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}]
    assert len(pulls) == 1, pulls


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog — EXCEPT the 16 pF crystal-load caps (LCSC C162205), which the board
    itself reports as a soft 'no ratings row' note (carrier part_rules.txt), not
    a hard finding. We mirror that exact soft treatment here."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id not in ("Device:C", "Device:R"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc == _CRYSTAL_CAP_LCSC:
            continue                          # board-documented soft exception
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    """Each rail-bypass cap (whose LCSC resolves) is voltage-rated for its
    worst-case rail voltage (the subsystem's own RAIL_WORST_V) with a >=1.3x
    ceramic margin. The island rail (3.6 V max) + the 5.5 V VBUS Cin are the
    cases; the crystal caps sit on internal nodes (no rail) and are skipped."""
    worst = RAIL_WORST_V
    n_checked = 0
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        if p.fields.get("LCSC") not in RATINGS_BY_LCSC:
            continue                          # crystal caps: no ratings row
        rail_v = max((worst.get(n.name, 0.0) for n in
                      (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2")))
                      if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail (<1.3x)")
        n_checked += 1
    assert n_checked == 5   # 10u + 100n + 100n + 100n on the island, 1u on VBUS


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (passives read as 'rail unresolved' on abstract rails, and the
    crystal caps as a soft 'no ratings row' note — both fail-soft, acceptable
    for a standalone subsystem)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt ↔ netlist passives --------------------------------------------

def _cir_caps() -> dict[str, float]:
    """Parse the .cir capacitor lines into {refdes: farads}."""
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
    """Parse the .cir resistor lines into {refdes: ohms}."""
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
    """The .cir subckt declares abstract ports as its pins (a project wires them
    to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt usb_jtag"))
    pins = header.split()[2:]
    assert pins == ["VBUS_USB", "3V3_ISLAND", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in usb_jtag.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    """The subckt's caps equal the netlist's caps, value-for-value (the .cir
    cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_cir_resistors_match_netlist(c: Circuit):
    """The subckt's pull/strap resistors equal the netlist's resistors,
    value-for-value (the RST# 10k + OE 100k + two MODE 10k pulldowns)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id == "Device:R")
    cir = sorted(_cir_resistors().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem (pure bypass + pulls) and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = usb_jtag.circuit()
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the draw budget followed the renamed island rail
    assert "+3V3_DBG" in bound.loads and "+3V3_ISLAND" not in bound.loads
    # the reset waiver followed the (internal, unrenamed) signal net
    assert "DBG_RST_N" in bound.reset_waivers


def test_bind_rewrites_the_usb_pair_payload():
    """The USB HS pair's pair_with payload follows the bind to the REAL
    complement (Circuit.bind rebinds the PortType's nested pair_with through the
    rename map, so the board's SI pair gate stays covered, not split across
    abstract/real endpoints) — NO post-finish fixup in the library."""
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    dp = bound.port_type_of("DBG_USB_DP")
    dm = bound.port_type_of("DBG_USB_DM")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "DBG_USB_DM"
    assert dm.pair_with == "DBG_USB_DP"
    # no abstract name leaks into the payload
    assert "USB_DP" not in (dp.pair_with, dm.pair_with)
    assert "USB_DM" not in (dp.pair_with, dm.pair_with)


def test_bind_rewrites_testpoint_values():
    """Testpoints are declared in ABSTRACT names; Circuit.bind rebinds their
    VALUE to the real net (the placer's TP1/TP2/TP3 order stays stable)."""
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
    """notes["draws"] overrides the power-tree note without changing topology."""
    base = usb_jtag.circuit()
    m = usb_jtag.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+3V3_ISLAND"][0][1] == "custom note"   # (amps, note)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usb_jtag.circuit({"note": {"draws": "X"}})   # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = usb_jtag.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_DBG"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. usb_jtag has
    real internal SIGNAL nets, so this is a live case."""
    c = usb_jtag.circuit()
    assert c.nets["DBG_RST_N"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"DBG_RST_N": "SOMETHING"})


def test_bind_rejects_collision():
    c = usb_jtag.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|merge"):
        c.bind({"JTAG_TCK": "SHARED", "JTAG_TMS": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = usb_jtag.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
