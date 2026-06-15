"""LOCAL electrical-correctness test for the microsd reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). It is co-located with the
package so a future migration of any other subsystem follows the same shape. See
subsystems/usb_pd/test_usb_pd.py for the worked exemplar.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), port types as declared, the
    card-side twins stay PRIVATE internal SIGNAL nets.
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap to GND on the sheet, exposed pad on GND, no
    floating config strap.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for that rail
    (the subsystem's own RAIL_WORST_V, since a board power tree is not present
    locally).
  * SPICE passives                — the .cir subckt's passive (cap) network
    matches the netlist one-for-one (parse_si), and the analytic spice slice
    runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph (CD_N binds on the J1 sheet), the full power-tree
headroom, board ERC and the board netlist merge. Those are aggregated by
`schgen board`.
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

import subsystems.microsd.microsd as microsd

HERE = Path(__file__).resolve().parent
CIR = HERE / "microsd.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/microsd.py.
_CARRIER_BIND = {
    "+VDD_HOST": "+1V8", "+VDD_CARD": "+3V3_SD", "GND": "GND",
    "SD_CLK": "SDIO_CLK", "SD_CMD": "SDIO_CMD",
    "SD_D0": "SDIO_D0", "SD_D1": "SDIO_D1",
    "SD_D2": "SDIO_D2", "SD_D3": "SDIO_D3",
    "CD_N": "SD_CARD_DETECT",
}

# The card-side twins are PRIVATE internal SIGNAL nets — never bound externally.
_CARD_SIGNALS = {"SD_CARD_CLK", "SD_CARD_CMD", "SD_CARD_D0", "SD_CARD_D1",
                 "SD_CARD_D2", "SD_CARD_D3"}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return microsd.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(microsd.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert "+1V8" not in externals and "+3V3_SD" not in externals
    assert not any(n.startswith("SDIO_") or n == "SD_CARD_DETECT"
                   for n in externals), externals


def test_card_side_nets_are_private_signal(c: Circuit):
    """The translator's B0 card-side twins are PRIVATE internal SIGNAL nets, not
    part of the bound interface (only the host A-side ports are external)."""
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert signals == _CARD_SIGNALS, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in microsd.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in microsd.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    # the SD bus ports carry their sd_bus typing at the host-side level
    for p in ("SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3"):
        pt = c.port_type_of(p)
        assert pt.kind == "sd_bus", (p, pt.kind)
        assert pt.level_v == microsd.HOST_LEVEL_V, (p, pt.level_v)


def test_two_distinct_supply_rails(c: Circuit):
    """The TXS02612 is a level translator with TWO distinct supply rails: VCCA
    (host) on +VDD_HOST and VCCB(0/1) (card) on +VDD_CARD — two separate POWER
    nets, each carrying a U1 supply pin (the translator's two domains)."""
    assert "+VDD_HOST" != "+VDD_CARD"
    host_u1 = {str(p) for p in c.nets["+VDD_HOST"].pins if p.ref == "U1"}
    card_u1 = {str(p) for p in c.nets["+VDD_CARD"].pins if p.ref == "U1"}
    # VCCA (one host supply pin) vs VCCB0/VCCB1 (two card supply pins)
    assert len(host_u1) == 1, host_u1
    assert len(card_u1) == 2, card_u1
    assert host_u1.isdisjoint(card_u1)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # unused TXS port B1 (6 lanes) + the two TPD6E001 NC pads are the only NCs
    nc = {str(p) for p in c.nc_pins}
    assert any(s.startswith("U1.") for s in nc) and len(nc) >= 6, nc


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND, the exposed
    pad is on GND, no config strap floats."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the supply rails are actually exercised (not a no-op)
    assert r.checked.get("decap", 0) >= 1
    assert r.checked.get("ep", 0) >= 1


def test_each_rail_has_a_local_bypass(c: Circuit):
    """The bypass network is present: VCCA host 100n, card rail 100n+22u bulk,
    ESD-array VCC 100n — all to GND on this sheet."""
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
    assert caps_to_gnd("+VDD_HOST") == ["100n"]
    # card rail: VCCB bypass 100n + 22u bulk + the TPD6E001 VCC 100n bypass
    assert caps_to_gnd("+VDD_CARD") == ["100n", "100n", "22u"]


def test_card_pulls_are_100k_and_card_detect_10k(c: Circuit):
    """SD-2: the five card-line anti-float pulls are 100k (in TI's >50k band);
    the card-detect pull (NOT on a TXS output) stays 10k."""
    pulls = sorted(p.value for ref, p in c.parts.items()
                   if p.lib_id.endswith(":R"))
    assert pulls == ["100k", "100k", "100k", "100k", "100k", "10k"], pulls


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog (caps + resistors)."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not (p.lib_id.endswith(":C") or p.lib_id.endswith(":R")):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    """Each bypass cap is voltage-rated for the worst-case voltage of the rail
    it sits on (the subsystem's own RAIL_WORST_V), with a >=1.3x ceramic
    margin."""
    worst = microsd.RAIL_WORST_V
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


# ---- SPICE subckt <-> netlist passives ------------------------------------------

def _cir_caps() -> dict[str, float]:
    """Parse the .cir capacitor lines into {refdes: farads}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt microsd"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_subckt_pins_are_the_abstract_rails():
    """The .cir subckt declares the abstract rails as its pins (a project wires
    them to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt microsd"))
    pins = header.split()[2:]
    assert pins == ["VDD_HOST", "VDD_CARD", "GND"], pins
    iface = {n.lstrip("+") for n in microsd.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's cap network equals the netlist's caps, value-for-value
    (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem (pure bypass + pull network) and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = microsd.circuit()
    bound = microsd.circuit({"bind": _CARRIER_BIND})
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; SIGNAL nets unchanged; order kept
    expect = [_CARRIER_BIND.get(n, n) for n in base.nets]
    assert list(bound.nets) == expect
    # the card-side SIGNAL twins are untouched by the bind
    assert _CARD_SIGNALS <= set(bound.nets)
    # port-type payloads survive the rename (sd_bus typing intact)
    assert bound.port_type_of("SDIO_CLK").kind == "sd_bus"
    assert bound.port_type_of("SDIO_CLK").level_v == microsd.HOST_LEVEL_V
    # the draw budgets followed the renamed rails
    assert "+3V3_SD" in bound.loads and "+VDD_CARD" not in bound.loads
    assert "+1V8" in bound.loads and "+VDD_HOST" not in bound.loads


def test_bind_identity_is_noop():
    base = microsd.circuit()
    ident = microsd.circuit({"bind": {n: n for n in microsd.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_notes_override_house_style():
    """The standard meta contract: notes["draws_card"/"draws_host"] override the
    power-tree notes without changing topology (a project restores its own
    house-style metadata)."""
    base = microsd.circuit()
    m = microsd.circuit({"notes": {"draws_card": "card note",
                                   "draws_host": "host note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.loads["+VDD_CARD"][0][1] == "card note"   # (amps, note)
    assert m.loads["+VDD_HOST"][0][1] == "host note"


def test_expects_attaches_card_detect_deferral():
    """meta["expects"] attaches a linker deferral to CD_N (a project declares
    which sheet binds the card-detect GPIO)."""
    m = microsd.circuit({"expects": {"CD_N": "my_connector"}})
    assert m.port_type_of("CD_N").expect == "my_connector"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        microsd.circuit({"bus": {"i2c": "X"}})        # not a legal key


def test_bind_rejects_unknown_name():
    c = microsd.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_SD"})


def test_bind_rejects_signal_net():
    """A card-side SIGNAL net is private wiring — binding one is a hard error."""
    c = microsd.circuit()
    assert c.nets["SD_CARD_CLK"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"SD_CARD_CLK": "SOMETHING"})


def test_bind_rejects_collision():
    c = microsd.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"SD_D0": "SHARED", "SD_D1": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = microsd.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
