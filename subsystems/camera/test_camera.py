"""LOCAL electrical-correctness test for the camera reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so
every migrated subsystem follows the same shape as subsystems/usb_pd/.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every connector pin netted-or-NC (model completeness), the three CSI lanes
    typed as reciprocal diff pairs @100R, the control I2C typed scl/sda.
  * decoupling / I2C completeness — design_rules DECAP/EP/STRAP/I2C slice: the
    gated-rail bypass is present and the in-subsystem camera I2C pull-ups satisfy
    the I2C-pull-up rule (UNLIKE usb_pd, the camera pull-ups DO live here — to
    the gated rail — so the local slice exercises that rule).
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on the gated rail is voltage-derated for it (the
    subsystem's own RAIL_WORST_V, since a board power tree is not present here).
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph (which sheet binds each CSI lane / control line), the full
power-tree headroom, board ERC and the board netlist merge. Those are aggregated
by `schgen board`.
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

import subsystems.camera.camera as camera

HERE = Path(__file__).resolve().parent
CIR = HERE / "camera.cir"

# The camera's own electrical contract: the gated module rail is 3.3 V class.
# (NOT a board value — a project may run +VDD_CAM at any 3.3 V-class gated rail.)
RAIL_WORST_V = {"+VDD_CAM": 3.3, "GND": 0.0}

# The CSI differential lanes (P, N, termination ref) — the diff-pair contract.
CSI_PAIRS = (("CSI_D0_P", "CSI_D0_N", "R1"),
             ("CSI_D1_P", "CSI_D1_N", "R2"),
             ("CSI_CLK_P", "CSI_CLK_N", "R3"))

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/camera.py.
_CARRIER_BIND = {
    "+VDD_CAM": "+3V3_CAM", "GND": "GND",
    "CSI_D0_P": "CAM_D0_P", "CSI_D0_N": "CAM_D0_N",
    "CSI_D1_P": "CAM_D1_P", "CSI_D1_N": "CAM_D1_N",
    "CSI_CLK_P": "CAM_CLK_P", "CSI_CLK_N": "CAM_CLK_N",
    "CAM_SCL": "CAM_SCL", "CAM_SDA": "CAM_SDA",
    "CAM_EN": "CAM_EN", "CAM_LED": "CAM_LED",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return camera.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(camera.INTERFACE), externals
    # the abstract names must not be carrier net names (the carrier names its
    # CSI lanes CAM_D*/CAM_CLK* and its gated rail +3V3_CAM)
    assert not any(n.startswith("CAM_D") or n.startswith("CAM_CLK")
                   or n == "+3V3_CAM" for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in camera.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in camera.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_csi_lanes_are_reciprocal_diff_pairs(c: Circuit):
    """Each CSI lane is a diff_pair @100R, reciprocally typed P<->N (D-PHY pairs
    are NOT polarity-swappable — the pairing must be authored both ways)."""
    for p, n, _ in CSI_PAIRS:
        tp_p, tp_n = c.port_type_of(p), c.port_type_of(n)
        assert tp_p.kind == "diff_pair" and tp_n.kind == "diff_pair", (p, n)
        assert tp_p.impedance == 100 and tp_n.impedance == 100, (p, n)
        assert tp_p.pair_with == n and tp_n.pair_with == p, (p, n)


def test_control_i2c_typed(c: Circuit):
    assert c.port_type_of("CAM_SCL").kind == "i2c"
    assert c.port_type_of("CAM_SCL").role == "scl"
    assert c.port_type_of("CAM_SDA").role == "sda"
    assert c.port_type_of("CAM_SCL").bus == c.port_type_of("CAM_SDA").bus
    assert c.port_type_of("CAM_SCL").bus == camera.I2C_BUS


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats). The only
    intentional no-connects are the spare ESD-array pads: each TPD4E02B04 has four
    USON-10 NC pads (6/7/9/10). U2's IO3 (pad 4) + IO4 (pad 5) now clamp the
    CAM_SCL/CAM_SDA control lines (audit 2026-06-20), so they are NO LONGER NC."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    nc = {str(p) for p in c.nc_pins}
    expected = {"U1.6", "U1.7", "U1.9", "U1.10",
                "U2.6", "U2.7", "U2.9", "U2.10"}
    assert nc == expected, nc


# ---- decoupling / I2C completeness (design_rules LOCAL slice) -------------------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """DECAP/EP/STRAP/I2C: no design-rule finding. UNLIKE usb_pd, the camera's
    I2C pull-ups live HERE (to the gated rail), so the I2C-pull-up rule is
    actually exercised and satisfied on this sheet."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert not r.i2c, r.i2c
    # the camera I2C bus (SCL+SDA) is actually exercised (not a no-op)
    assert r.checked.get("i2c", 0) >= 2


def test_gated_rail_has_local_bypass_and_pullups(c: Circuit):
    """The reference network at the FFC: +VDD_CAM 100n+10u bypass, and the two
    4k7 camera-control pull-ups land on the GATED rail (a powered-down camera is
    not back-fed through its bus pull-ups)."""
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                      c.net_of(PinRef(ref, "2"))) if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VDD_CAM") == ["100n", "10u"]
    # the I2C pull-ups (R4/R5, 4k7) have one leg on the GATED +VDD_CAM rail
    pullup_rails = []
    for ref in ("R4", "R5"):
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        assert c.parts[ref].value == "4k7", ref
        assert "+VDD_CAM" in names, (ref, names)
        pullup_rails.append("+VDD_CAM")
    assert pullup_rails == ["+VDD_CAM", "+VDD_CAM"]


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog (a part_rules.run on abstract rails reports caps as 'rail
    unresolved', so we assert catalog coverage directly here)."""
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
    margin (the +VDD_CAM gated rail is 3.3 V class)."""
    worst = RAIL_WORST_V
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

def _cir_passives() -> dict[str, float]:
    """Parse the .cir R/C lines into {refdes: value_in_si}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt camera"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[-1])
    return out


def test_cir_subckt_pins_are_abstract_interface():
    """The .cir subckt declares the abstract ports as its pins (a project wires
    them to real nets, exactly as the netlist bind does). CAM_EN/CAM_LED carry no
    subsystem-local passive, so they are not subckt pins."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt camera"))
    pins = header.split()[2:]
    assert pins == ["VDD_CAM", "CSI_D0_P", "CSI_D0_N", "CSI_D1_P", "CSI_D1_N",
                    "CSI_CLK_P", "CSI_CLK_N", "CAM_SCL", "CAM_SDA", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in camera.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's passive network equals the netlist's R+C, value-for-value
    (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C") or p.lib_id.endswith(":R"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem (it has none — terminations + pull-ups + bypass) and no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = camera.circuit()
    bound = camera.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; order preserved
    assert list(bound.nets) == [_CARRIER_BIND[n] for n in base.nets]
    # diff-pair payloads survive the rename (the reciprocal pairing is rewritten)
    assert bound.port_type_of("CAM_D0_P").pair_with == "CAM_D0_N"
    assert bound.port_type_of("CAM_D0_N").pair_with == "CAM_D0_P"
    assert bound.port_type_of("CAM_D0_P").impedance == 100
    # the draw budget followed the renamed rail
    assert "+3V3_CAM" in bound.loads and "+VDD_CAM" not in bound.loads


def test_bind_rewrites_diff_pair_complement():
    """A diff_pair's ``pair_with`` is a net-NAME reference: after bind it must
    point at the REAL complement, not the abstract one (else the derived board
    artifacts — layout_constraints.csv pair_with / length-match group, the XDC
    pair — would carry an abstract name and drift from a hand-written sheet)."""
    bound = camera.circuit({"bind": _CARRIER_BIND})
    for p, n, _ in CSI_PAIRS:
        rp, rn = _CARRIER_BIND[p], _CARRIER_BIND[n]
        assert bound.port_type_of(rp).pair_with == rn, (p, rp)
        assert bound.port_type_of(rn).pair_with == rp, (n, rn)
        # no abstract complement name survives anywhere in the payload
        assert bound.port_type_of(rp).pair_with not in (p, n)


def test_bind_identity_is_noop():
    base = camera.circuit()
    ident = camera.circuit({"bind": {n: n for n in camera.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    """The standard meta contract: buses["i2c"] renames the bus group and
    notes["draws"] overrides the power-tree note — without changing the netlist
    topology (a project restores its own house-style metadata)."""
    base = camera.circuit()
    m = camera.circuit({"buses": {"i2c": "MY_CAM_I2C"},
                        "notes": {"draws": "custom note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("CAM_SCL").bus == "MY_CAM_I2C"
    assert m.port_type_of("CAM_SDA").bus == "MY_CAM_I2C"
    assert m.loads["+VDD_CAM"][0][1] == "custom note"   # (amps, note)


def test_meta_expects_attaches_port_deferral():
    """meta["expects"] attaches an explicit linker deferral to a port without
    changing the netlist topology (a project declares which sheet binds it)."""
    m = camera.circuit({"expects": {"CSI_D0_P": "som_j3 (bank 35)",
                                    "CAM_EN": "som_j3 (bank 33)"}})
    assert m.port_type_of("CSI_D0_P").expect == "som_j3 (bank 35)"
    assert m.port_type_of("CAM_EN").expect == "som_j3 (bank 33)"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        camera.circuit({"bus": {"i2c": "X"}})        # 'bus' != 'buses'


def test_bind_rejects_unknown_name():
    c = camera.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_CAM"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. (camera has
    no SIGNAL net of its own, so synthesize a real 2-pin internal net.)"""
    c2 = Circuit("t", "t")
    c2.part("R1", "Device:R", "1k", "")
    c2.part("R2", "Device:R", "1k", "")
    c2.net("MID", "R1.2", "R2.1")
    assert c2.nets["MID"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c2.bind({"MID": "SOMETHING"})


def test_bind_rejects_collision():
    c = camera.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"CSI_D0_P": "SHARED", "CSI_D0_N": "SHARED"})


def test_bound_circuit_passes_local_design_rules(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local design-rules
    slice (binding is a pure rename; electrical completeness is unchanged)."""
    bound = camera.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap or r.i2c), r.findings
