"""LOCAL electrical-correctness test for the pmod reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). Co-located with the
package so a future migration of any other subsystem follows the same shape
(see subsystems/usb_pd/test_usb_pd.py for the worked exemplar).

pmod is a PURE CONNECTOR sheet (two DS1024 Pmod sockets) plus inline passives —
no active IC — so the LOCAL checks it can prove about ITSELF are:
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every connector pin netted-or-NC (model completeness), the 16 host signals
    typed as PORTs carrying their linker-deferral payload (when bound).
  * protection + bypass network   — the Digilent-standard 200R series resistor on
    every one of the 16 IOs (host signal -> 200R -> private socket-IO net), and
    each port's VCC pins carry a 100n + 10u local bypass to GND.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and each bypass cap is voltage-derated for +VCC_PMOD.
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
full power-tree headroom, the link/port-driver graph, board ERC, and the board
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

import subsystems.pmod.pmod as pmod

HERE = Path(__file__).resolve().parent
CIR = HERE / "pmod.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/pmod.py.
_CARRIER_PORT_NETS = {
    "PMOD0": ["IO_L2_P_13", "IO_L2_N_13", "IO_L3_P_13", "IO_L3_N_13",
              "IO_L4_P_13", "IO_L4_N_13", "IO_L5P_13", "IO_L5_N_13"],
    "PMOD1": ["IO_L7_P_13", "IO_L7_N_13", "IO_L8_P_13", "IO_L8_N_13",
              "IO_L9_DQS_P_13", "IO_L9_DQS_N_13", "IO_L10_P_13", "IO_L10_N_13"],
}
_CARRIER_BIND = {"+VCC_PMOD": "+3V3_PMOD", "GND": "GND",
                 **{f"{port}_SIG{io}": net
                    for port, nets in _CARRIER_PORT_NETS.items()
                    for io, net in enumerate(nets, start=1)}}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return pmod.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(pmod.INTERFACE), externals
    # the abstract names must not be carrier SoM bank-13 net names
    assert not any(n.endswith("_13") or n == "+3V3_PMOD" for n in externals), \
        externals


def test_interface_shape(c: Circuit):
    """The interface is exactly the two rails + 16 host signals (8 per port)."""
    assert pmod.RAILS == ("+VCC_PMOD", "GND")
    assert len(pmod.PORTS) == 16
    assert pmod.PORTS[:8] == tuple(f"PMOD0_SIG{i}" for i in range(1, 9))
    assert pmod.PORTS[8:] == tuple(f"PMOD1_SIG{i}" for i in range(1, 9))


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in pmod.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in pmod.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_internal_io_nets_stay_private_signal(c: Circuit):
    """The 200R -> socket-pin span (PMOD{n}_IO{m}) is a PRIVATE SIGNAL net — it
    is never an external and is never exposed for binding."""
    signal = {n.name for n in c.nets.values()
              if n.net_class is NetClass.SIGNAL}
    assert signal == {f"PMOD{p}_IO{io}"
                      for p in (0, 1) for io in range(1, 9)}, signal
    assert not (signal & set(pmod.INTERFACE))


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part (both 12-pad sockets,
    every R and C) is netted or NC — the same hard check the board build runs
    (LAW 0: no silent floats). A plain connector has NO intentional no-connect."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert not c.nc_pins, {str(p) for p in c.nc_pins}


# ---- protection + bypass network ------------------------------------------------

def test_200r_series_on_every_io(c: Circuit):
    """Digilent-standard protection: every one of the 16 host signals enters
    through a 200R series resistor onto a private socket-IO net."""
    res = [(ref, p) for ref, p in c.parts.items() if p.lib_id.endswith(":R")]
    assert len(res) == 16, [r for r, _ in res]
    assert {p.value for _, p in res} == {"200R"}
    for port in ("PMOD0", "PMOD1"):
        for io in range(1, 9):
            sig = f"{port}_SIG{io}"
            iol = f"{port}_IO{io}"
            # exactly one resistor straddles the host signal and the socket-IO net
            bridging = [ref for ref, _ in res
                        if {n.name for n in (c.net_of(PinRef(ref, "1")),
                                             c.net_of(PinRef(ref, "2"))) if n}
                        == {sig, iol}]
            assert len(bridging) == 1, (sig, iol, bridging)


def test_each_port_has_a_local_vcc_bypass(c: Circuit):
    """Each of the two ports carries a 100n + 10u local bypass on +VCC_PMOD ->
    GND (4 caps total, two 100n + two 10u)."""
    bypass = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if nets == {"+VCC_PMOD", "GND"}:
            bypass.append(p.value)
    assert sorted(bypass) == ["100n", "100n", "10u", "10u"], sorted(bypass)


def test_design_rules_slice_runs_clean(c: Circuit, lib: Library):
    """The board's design-rule engine raises no DECAP/EP/STRAP finding (a plain
    connector has no IC supply pin, no exposed pad, no config strap)."""
    r = design_rules.check([_sheet(c)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog (a part_rules.run on abstract rails reports caps as 'rail
    unresolved', so we assert the catalog coverage directly here)."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_bypass_caps_voltage_derated_for_rail(c: Circuit):
    """Each VCC bypass cap is voltage-rated for +VCC_PMOD (3.3 V class) with a
    >=1.3x ceramic margin."""
    rail_v = pmod.RAIL_NOM_V["+VCC_PMOD"]
    seen = 0
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                 c.net_of(PinRef(ref, "2"))) if n}
        if "+VCC_PMOD" not in nets:
            continue
        rat = RATINGS_BY_LCSC[p.fields["LCSC"]]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail (<1.3x)")
        seen += 1
    assert seen == 4, seen


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (caps read as 'rail unresolved' on abstract rails — fail-soft —
    which is acceptable for a standalone subsystem)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt <-> netlist passives ------------------------------------------

def _cir_passives() -> dict[str, float]:
    """Parse the .cir R/C lines inside the pmod subckt into {refdes: value}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt pmod"):
            in_subckt = True
            continue
        if in_subckt and s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_interface():
    """The .cir subckt declares the abstract ports as its pins (a project wires
    them to real nets, exactly as the netlist bind does)."""
    text = CIR.read_text()
    # the subckt header may use line continuations ('+'), so stitch them first
    lines = text.splitlines()
    hdr = []
    started = False
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith(".subckt pmod"):
            hdr.append(s)
            started = True
            continue
        if started and s.startswith("+"):
            hdr.append(s[1:].strip())
            continue
        if started:
            break
    pins = " ".join(hdr).split()[2:]
    want = ["VCC_PMOD"] + [f"PMOD{p}_SIG{io}"
                           for p in (0, 1) for io in range(1, 9)] + ["GND"]
    assert pins == want, pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in pmod.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's passive network equals the netlist's R+C, value-for-value
    (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":R") or p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem (it has none — series protection + bypass only) and no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, internal SIGNAL nets and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = pmod.circuit()
    bound = pmod.circuit({"bind": _CARRIER_BIND})
    # same parts/refs
    assert set(bound.parts) == set(base.parts)
    # externals renamed exactly per the map; internal SIGNAL nets untouched; order
    # preserved across the whole nets dict
    expect = [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert list(bound.nets) == expect
    # the internal IO SIGNAL nets are NOT in the bind map and survive verbatim
    assert "PMOD0_IO1" in bound.nets and "PMOD1_IO8" in bound.nets
    # the draw budget followed the renamed rail
    assert "+3V3_PMOD" in bound.loads and "+VCC_PMOD" not in bound.loads


def test_bind_carries_port_deferral_payload():
    """When the adapter supplies expects=, the bound host-signal ports carry the
    linker-deferral string (the carrier defers all 16 to its J2 sheet)."""
    bound = pmod.circuit({
        "bind": _CARRIER_BIND,
        "expects": {f"{port}_SIG{io}": "som_j2_connector"
                    for port in ("PMOD0", "PMOD1") for io in range(1, 9)},
    })
    assert bound.port_type_of("IO_L2_P_13").expect == "som_j2_connector"
    assert bound.port_type_of("IO_L10_N_13").expect == "som_j2_connector"


def test_bind_identity_is_noop():
    base = pmod.circuit()
    ident = pmod.circuit({"bind": {n: n for n in pmod.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    """notes["draws"] overrides the power-tree note without changing the netlist
    topology (a project restores its own house-style metadata)."""
    base = pmod.circuit()
    m = pmod.circuit({"notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VCC_PMOD"][0][1] == "custom note"   # (amps, note)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        pmod.circuit({"note": {"draws": "X"}})           # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = pmod.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_PMOD"})


def test_bind_rejects_signal_net():
    """An internal SIGNAL net is private wiring — binding one is a hard error."""
    c = pmod.circuit()
    assert c.nets["PMOD0_IO1"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"PMOD0_IO1": "SOMETHING"})


def test_bind_rejects_collision():
    c = pmod.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"PMOD0_SIG1": "SHARED", "PMOD0_SIG2": "SHARED"})
