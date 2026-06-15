"""LOCAL electrical-correctness test for the ethernet reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). Co-located with the
package so a future migration of any other subsystem follows the same shape.
See subsystems/usb_pd/test_usb_pd.py for the worked exemplar and
subsystems/hdmi_tx/test_hdmi_tx.py for the diff-pair sibling.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every part pin netted-or-NC (model completeness), the pin-FAITHFUL HX5008NL
    mapping (chip pair / media pair / centre tap / NC per channel), the 8
    differential MDI pairs typed as declared.
  * Bob-Smith termination         — each of the 4 media centre taps has a
    75R || 1n into the shared BS_COMMON trunk, and ONE 1n isolation cap bridges
    that trunk to CHASSIS_GND (the safety barrier).
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the 1n caps carry the 2 kV hi-pot rating.
  * SPICE passives                — the .cir subckt's caps match the netlist
    one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph (the chip pairs face the PHY sheet, the media pairs the
RJ45-connector sheet), the full SI 37-pair set, board ERC and the board netlist
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

import subsystems.ethernet.ethernet as ethernet

HERE = Path(__file__).resolve().parent
CIR = HERE / "ethernet.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/ethernet.py. The CHIP
# pairs (MDIn) face the SoM PHY (ETH_PHY_MDIn); the MEDIA pairs (MXn) face the
# RJ45 jack (ETH_LINE_MDI_n); the chassis island is an identity bind.
_CARRIER_BIND = {
    "CHASSIS_GND": "CHASSIS_GND",
    "MDI0_P": "ETH_PHY_MDI0_P", "MDI0_N": "ETH_PHY_MDI0_N",
    "MDI1_P": "ETH_PHY_MDI1_P", "MDI1_N": "ETH_PHY_MDI1_N",
    "MDI2_P": "ETH_PHY_MDI2_P", "MDI2_N": "ETH_PHY_MDI2_N",
    "MDI3_P": "ETH_PHY_MDI3_P", "MDI3_N": "ETH_PHY_MDI3_N",
    "MX0_P": "ETH_LINE_MDI_0_P", "MX0_N": "ETH_LINE_MDI_0_N",
    "MX1_P": "ETH_LINE_MDI_1_P", "MX1_N": "ETH_LINE_MDI_1_N",
    "MX2_P": "ETH_LINE_MDI_2_P", "MX2_N": "ETH_LINE_MDI_2_N",
    "MX3_P": "ETH_LINE_MDI_3_P", "MX3_N": "ETH_LINE_MDI_3_N",
}

# The carrier's media-side linker deferral (the RJ45 connector binds these on a
# later wave). Used only to exercise meta.expect_kw threading.
_RJ45_DEFER = "rj45_connector (wave 2)"
_CARRIER_EXPECTS = {f"MX{n}_P": _RJ45_DEFER for n in range(4)}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return ethernet.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(ethernet.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert not any(n.startswith("ETH_PHY") or n.startswith("ETH_LINE")
                   for n in externals), externals
    # the Bob-Smith centre taps + trunk stay PRIVATE SIGNAL wiring
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert {"MCT1", "MCT2", "MCT3", "MCT4", "BS_COMMON"} == signals, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    # the only rail is the chassis-ground island (a GROUND, kept separate from
    # any signal GND — there is no signal GND on this passive-magnetics sheet)
    assert cls["CHASSIS_GND"] is NetClass.GROUND, cls["CHASSIS_GND"]
    for port in ethernet.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_mdi_and_mx_pairs_typed(c: Circuit):
    """All 8 MDI pairs (4 chip-side + 4 media-side) are 100 Ω diff_pairs with the
    P<->N reciprocal type registered automatically."""
    for n in range(4):
        for pp, pn in ((f"MDI{n}_P", f"MDI{n}_N"), (f"MX{n}_P", f"MX{n}_N")):
            tp, tn = c.port_type_of(pp), c.port_type_of(pn)
            assert tp.kind == "diff_pair" and tn.kind == "diff_pair", (pp, pn)
            assert tp.impedance == 100 and tn.impedance == 100, (pp, pn)
            assert tp.pair_with == pn and tn.pair_with == pp, (pp, pn)


def test_hx5008nl_pin_faithful_mapping(c: Circuit):
    """LAW 0 — the FAITHFUL HX5008NL (C962544) pinout, pad-for-pad: each channel
    has its CHIP pair (TDn) on the abstract MDIn, its MEDIA pair (MXn) on the
    abstract MXn, its media centre tap (MCTn) on the Bob-Smith trunk, and its
    chip centre tap (TCTn) a no-connect.

       ch  td_p td_n  mx_p mx_n  mct  tct
        0   2    3     23   22   24   1
        1   5    6     20   19   21   4
        2   8    9     17   16   18   7
        3  11   12     14   13   15  10
    """
    expect = [(0, 2, 3, 23, 22, 24, 1),
              (1, 5, 6, 20, 19, 21, 4),
              (2, 8, 9, 17, 16, 18, 7),
              (3, 11, 12, 14, 13, 15, 10)]
    for ch, td_p, td_n, mx_p, mx_n, mct, tct in expect:
        assert {str(p) for p in c.nets[f"MDI{ch}_P"].pins} == {f"T1.{td_p}"}
        assert {str(p) for p in c.nets[f"MDI{ch}_N"].pins} == {f"T1.{td_n}"}
        assert {str(p) for p in c.nets[f"MX{ch}_P"].pins} == {f"T1.{mx_p}"}
        assert {str(p) for p in c.nets[f"MX{ch}_N"].pins} == {f"T1.{mx_n}"}
        # the media centre tap is the Bob-Smith node MCT{ch+1}
        assert PinRef("T1", str(mct)) in c.nets[f"MCT{ch + 1}"].pins
        # the chip centre tap is a no-connect (PHY self-biases)
        assert PinRef("T1", str(tct)) in c.nc_pins
    # the magnetics is the single, genuine Pulse HX5008NLT
    assert c.parts["T1"].lib_id.endswith("HX5008NLT") or \
        "HX5008NLT" in c.parts["T1"].lib_id


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the four CHIP-side centre taps are the only intentional no-connects
    assert {str(p) for p in c.nc_pins} == {"T1.1", "T1.4", "T1.7", "T1.10"}


# ---- Bob-Smith termination ------------------------------------------------------

def test_bob_smith_per_centre_tap(c: Circuit):
    """Each of the four media centre taps carries a 75R || 1n into the shared
    BS_COMMON trunk (IEEE 802.3 §40.7.1 HF termination)."""
    for ch in range(4):
        mct = f"MCT{ch + 1}"
        names = {str(p) for p in c.nets[mct].pins}
        # T1 centre-tap pad + the R and C local pin
        assert f"R{ch + 1}.1" in names and f"C{ch + 1}.1" in names, (mct, names)
        # the R/C other ends land on the shared trunk
        bs = {str(p) for p in c.nets["BS_COMMON"].pins}
        assert f"R{ch + 1}.2" in bs and f"C{ch + 1}.2" in bs, bs
        assert c.parts[f"R{ch + 1}"].value == "75R"
        assert c.parts[f"C{ch + 1}"].value == "1n"


def test_isolation_barrier_cap_to_chassis(c: Circuit):
    """The single shared 1n/2kV cap (C5) bridges the BS_COMMON trunk to the
    chassis island — THE isolation barrier element."""
    bs = {str(p) for p in c.nets["BS_COMMON"].pins}
    ch = {str(p) for p in c.nets["CHASSIS_GND"].pins}
    assert "C5.1" in bs, bs
    assert "C5.2" in ch, ch
    assert c.parts["C5"].value == "1n"
    # all five 1n caps carry the 2 kV hi-pot rating (the barrier part)
    for ref in ("C1", "C2", "C3", "C4", "C5"):
        lcsc = c.parts[ref].fields["LCSC"]
        assert RATINGS_BY_LCSC[lcsc].v_max >= 2000, (ref, lcsc)


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


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (the safety caps are rated 2 kV; resistors carry their value)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt ↔ netlist passives --------------------------------------------

def _cir_caps() -> dict[str, float]:
    """Parse the .cir capacitor lines into {refdes: farads}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt ethernet"):
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
    them to real nets, exactly as the netlist bind does). The header spans a
    continuation line ('+')."""
    lines = CIR.read_text().splitlines()
    hdr_idx = next(i for i, l in enumerate(lines)
                   if l.strip().lower().startswith(".subckt ethernet"))
    header = lines[hdr_idx].split()[2:]
    # fold any continuation lines into the pin list
    j = hdr_idx + 1
    while j < len(lines) and lines[j].lstrip().startswith("+"):
        header += lines[j].lstrip()[1:].split()
        j += 1
    assert header == [
        "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N", "MDI2_P", "MDI2_N",
        "MDI3_P", "MDI3_N", "MX0_P", "MX0_N", "MX1_P", "MX1_N",
        "MX2_P", "MX2_N", "MX3_P", "MX3_N", "CHASSIS_GND"], header
    # every subckt pin is a real abstract interface net
    assert set(header) == set(ethernet.INTERFACE), header


def test_cir_passives_match_netlist(c: Circuit):
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
    nothing else: part set, refs, NCs, port-type pair_with payloads are
    preserved, and the nets dict keeps insertion order (byte-identical emit).
    SIGNAL nets (MCT1..4, BS_COMMON) are private and keep their names."""
    base = ethernet.circuit()
    bound = ethernet.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; order preserved (SIGNAL nets keep
    # their name — only the externals in the bind map move)
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the diff-pair typing + reciprocal survive the rename (pair_with rebound)
    assert bound.port_type_of("ETH_PHY_MDI0_P").pair_with == "ETH_PHY_MDI0_N"
    assert bound.port_type_of("ETH_PHY_MDI0_N").pair_with == "ETH_PHY_MDI0_P"
    assert bound.port_type_of("ETH_LINE_MDI_2_P").pair_with == "ETH_LINE_MDI_2_N"
    assert bound.port_type_of("ETH_LINE_MDI_2_P").impedance == 100


def test_bind_with_expects_threads_media_deferral():
    """The carrier media-side linker deferral threads via meta.expect_kw: only
    the P net of each media pair is named, and the reciprocal N inherits it; the
    chip-side pairs carry no deferral."""
    bound = ethernet.circuit({"bind": _CARRIER_BIND,
                              "expects": _CARRIER_EXPECTS})
    for n in range(4):
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_P").expect == _RJ45_DEFER
        assert bound.port_type_of(f"ETH_LINE_MDI_{n}_N").expect == _RJ45_DEFER
        assert bound.port_type_of(f"ETH_PHY_MDI{n}_P").expect is None
        assert bound.port_type_of(f"ETH_PHY_MDI{n}_N").expect is None


def test_bind_identity_is_noop():
    base = ethernet.circuit()
    ident = ethernet.circuit({"bind": {n: n for n in ethernet.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        ethernet.circuit({"bus": {"x": "Y"}})        # no such key


def test_bind_rejects_unknown_name():
    c = ethernet.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. ethernet's
    Bob-Smith centre taps + trunk are SIGNAL, so try to bind one."""
    c = ethernet.circuit()
    assert c.nets["BS_COMMON"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"BS_COMMON": "SOMETHING"})


def test_bind_rejects_collision():
    c = ethernet.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"MDI0_P": "SHARED", "MDI0_N": "SHARED"})
