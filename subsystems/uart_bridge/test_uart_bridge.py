"""LOCAL electrical-correctness test for the uart_bridge reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so a
migration of any other subsystem follows the same shape (mirrors
subsystems/usb_pd/test_usb_pd.py).

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    the USB HS pair typed, every IC pin netted-or-NC (model completeness).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap to GND, the QFN exposed pad is on GND, the
    open-drain ~RST waiver is honoured (no spurious reset finding).
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and each cap on the logic rail is voltage-derated for it.
  * SPICE passives                — the .cir subckt's passive caps match the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, is order-preserving, and the USB HS pair's
    pair_with payload follows the bind (so the SI pair gate stays covered).

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

import subsystems.uart_bridge.uart_bridge as uart_bridge

HERE = Path(__file__).resolve().parent
CIR = HERE / "uart_bridge.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map (incl the TXD<->RXD / RTS<->CTS crossover) lives in
# carrier/subsystems/uart_bridge.py.
_CARRIER_BIND = {
    "+VDD_IO": "+3V3", "GND": "GND",
    "USB_VBUS": "USB_UART_VBUS",
    "USB_DP": "USB_UART_DP", "USB_DM": "USB_UART_DM",
    "UART_TXD": "ZYNQ_PS_UART0_RXD", "UART_RXD": "ZYNQ_PS_UART0_TXD",
    "UART_RTS_N": "ZYNQ_PS_UART0_CTS_N", "UART_CTS_N": "ZYNQ_PS_UART0_RTS_N",
}

# The subsystem's own electrical contract: the logic rail is 3.3 V class (a
# project may run +VDD_IO at any 3.3 V-class rail). Used by the local test to
# derate the bypass caps without depending on a board power tree.
RAIL_WORST_V = {"+VDD_IO": 3.3, "GND": 0.0}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return uart_bridge.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(uart_bridge.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert not any(n.startswith("ZYNQ_PS") or n.startswith("USB_UART")
                   or n == "+3V3" for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in uart_bridge.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in uart_bridge.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    # the USB data lines form a 90R USB 2.0 HS differential pair
    dp = c.port_type_of("USB_DP")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "USB_DM"
    assert dp.impedance == 90
    assert c.port_type_of("USB_DM").pair_with == "USB_DP"
    # the UART signals are plain single-ended ports
    for p in ("UART_TXD", "UART_RXD", "UART_RTS_N", "UART_CTS_N"):
        assert c.port_type_of(p).kind == "single"


def test_internal_signal_nets_stay_private(c: Circuit):
    """The ~RST node and the VBUS-divider mid node are PRIVATE SIGNAL nets (not
    externals): verbatim CP2102N_* names, never part of the abstract interface."""
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == {"CP2102N_RST_N", "CP2102N_VBUS_SNS"}, signals
    assert not (signals & set(uart_bridge.INTERFACE))


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the unused GPIO / modem-control / suspend pins + the two physical NCs
    assert {str(p) for p in c.nc_pins} == {
        "U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15",
        "U1.16", "U1.17", "U1.22", "U1.23", "U1.24"}


def test_qfn_exposed_pad_is_the_second_gnd(c: Circuit):
    """The faithful dossier symbol exposes the QFN pad as pin 25 = the second
    GND pad; it must be netted to GND alongside its twin pin 2 (a LAW-0 open the
    board gates would otherwise miss)."""
    gnd = c.net_of(PinRef("U1", "25"))
    assert gnd is not None and gnd.name == "GND"
    assert c.net_of(PinRef("U1", "2")).name == "GND"


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND, the exposed
    pad is on GND, the open-drain ~RST waiver is honoured (no spurious reset
    finding) and no config strap floats."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the supply rail is actually exercised (not a no-op)
    assert r.checked.get("decap", 0) >= 1


def test_self_powered_rail_has_full_bypass(c: Circuit):
    """The datasheet self-powered bypass network is present: VREGIN 100n+10u,
    VDD 100n, VIO 100n — all to GND, all on the +VDD_IO rail (tied together)."""
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
    assert caps_to_gnd("+VDD_IO") == ["100n", "100n", "100n", "10u"]


def test_vbus_sense_divider(c: Circuit):
    """The self-powered VBUS-sense divider: 22k1 top (USB_VBUS -> mid) + 47k5
    bottom (mid -> GND), with the mid on the CP2102N VBUS pin. Senses the USB
    connector's OWN 5 V VBUS — not a board input rail (the 2026-06-11 spice-gate
    fix)."""
    top = next(p for ref, p in c.parts.items() if p.value == "22k1")
    bot = next(p for ref, p in c.parts.items() if p.value == "47k5")
    top_nets = {n.name for n in (c.net_of(PinRef(top.ref, "1")),
                                 c.net_of(PinRef(top.ref, "2"))) if n}
    bot_nets = {n.name for n in (c.net_of(PinRef(bot.ref, "1")),
                                 c.net_of(PinRef(bot.ref, "2"))) if n}
    assert top_nets == {"USB_VBUS", "CP2102N_VBUS_SNS"}, top_nets
    assert bot_nets == {"CP2102N_VBUS_SNS", "GND"}, bot_nets
    # the divider mid is on the bridge VBUS pin (pin 8)
    assert c.net_of(PinRef("U1", "8")).name == "CP2102N_VBUS_SNS"


def test_reset_waiver_declared(c: Circuit):
    """~RST is an open-drain reset with the 1k external pull-up only (internal
    POR; no RC cap) — the design-rule reset waiver must be declared so the local
    decoupling slice does NOT flag CP2102N_RST_N."""
    assert "CP2102N_RST_N" in c.reset_waivers
    # and a 1k pull-up to the logic rail actually exists on that node
    r1 = next(p for ref, p in c.parts.items() if p.value == "1k")
    nets = {n.name for n in (c.net_of(PinRef(r1.ref, "1")),
                             c.net_of(PinRef(r1.ref, "2"))) if n}
    assert nets == {"+VDD_IO", "CP2102N_RST_N"}, nets


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC (caps AND the divider/pull-up
    resistors) resolves in the ratings catalog."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id not in ("Device:C", "Device:R"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    """Each bypass cap on the logic rail is voltage-rated for its worst-case
    voltage (the subsystem's own RAIL_WORST_V) with a >=1.3x ceramic margin."""
    worst = RAIL_WORST_V
    n_checked = 0
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        rail_v = max((worst.get(n.name, 0.0) for n in
                      (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2")))
                      if n), default=0.0)
        if rail_v <= 0:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail (<1.3x)")
        n_checked += 1
    assert n_checked == 4   # all four bypass caps sit on +VDD_IO


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (passives read as 'rail unresolved' on abstract rails — fail-soft —
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
        if s.lower().startswith(".subckt uart_bridge"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_abstract_interface():
    """The .cir subckt declares abstract ports as its pins (a project wires them
    to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt uart_bridge"))
    pins = header.split()[2:]
    assert pins == ["VDD_IO", "USB_VBUS", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in uart_bridge.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_caps_match_netlist(c: Circuit):
    """The subckt's bypass caps equal the netlist's caps, value-for-value (the
    .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem (the VBUS divider is benign) and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = uart_bridge.circuit()
    bound = uart_bridge.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the draw budget followed the renamed rail
    assert "+3V3" in bound.loads and "+VDD_IO" not in bound.loads
    # the reset waiver followed the (internal, unrenamed) signal net
    assert "CP2102N_RST_N" in bound.reset_waivers


def test_bind_rewrites_the_usb_pair_payload():
    """The USB HS pair's pair_with payload follows the bind to the REAL
    complement (Circuit.bind rebinds the PortType's nested pair_with through the
    rename map, so the board's SI pair gate stays covered, not split across
    abstract/real endpoints)."""
    bound = uart_bridge.circuit({"bind": _CARRIER_BIND})
    dp = bound.port_type_of("USB_UART_DP")
    dm = bound.port_type_of("USB_UART_DM")
    assert dp.kind == "usb_hs_pair" and dp.pair_with == "USB_UART_DM"
    assert dm.pair_with == "USB_UART_DP"
    # no abstract name leaks into the payload
    assert "USB_DP" not in (dp.pair_with, dm.pair_with)
    assert "USB_DM" not in (dp.pair_with, dm.pair_with)


def test_bind_identity_is_noop():
    base = uart_bridge.circuit()
    ident = uart_bridge.circuit({"bind": {n: n for n in uart_bridge.INTERFACE}})
    assert list(ident.nets) == list(base.nets)
    assert ident.port_type_of("USB_DP").pair_with == "USB_DM"


def test_meta_notes_override_house_style():
    """notes["draws"] overrides the power-tree note without changing topology."""
    base = uart_bridge.circuit()
    m = uart_bridge.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VDD_IO"][0][1] == "custom note"   # (amps, note)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        uart_bridge.circuit({"note": {"draws": "X"}})   # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = uart_bridge.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. uart_bridge
    has real internal SIGNAL nets, so this is a live case."""
    c = uart_bridge.circuit()
    assert c.nets["CP2102N_RST_N"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"CP2102N_RST_N": "SOMETHING"})


def test_bind_rejects_collision():
    c = uart_bridge.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|merge"):
        c.bind({"UART_TXD": "SHARED", "UART_RXD": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = uart_bridge.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
