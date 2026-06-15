"""LOCAL electrical-correctness test for the lcd reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Co-located with the package so
every migrated subsystem follows the same shape as subsystems/usb_pd/.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every connector/IC pin netted-or-NC (model completeness), the touch I2C typed
    scl/sda on the named bus, the internal SIGNAL boost nodes kept verbatim.
  * decoupling / I2C / reset slice — design_rules DECAP/EP/STRAP/I2C/RESET: the
    in-subsystem touch I2C pull-ups satisfy the I2C-pull-up rule and the GPIO-
    driven TP_RST reset waiver is honoured (no RC-reset finding).
  * backlight boost topology       — the SY7201 boost network is present and on
    the expected nodes: 10u input bulk, 2.2u/50V output cap on the OVP-sense
    node, the 1.5R ISET current-sense to GND, the catch diode + inductor.
  * part ratings                   — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for it (the
    subsystem's own RAIL_WORST_V, since a board power tree is not present here);
    the boost output cap clears the 30 V open-LED OVP clamp.
  * SPICE passives                 — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract              — abstract -> real renames only externals,
    rejects SIGNAL (the boost switch node)/typo/collision, identity is a no-op,
    and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
link/port-driver graph (which sheet binds each RGB/sync/touch line), the full
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

import subsystems.lcd.lcd as lcd

HERE = Path(__file__).resolve().parent
CIR = HERE / "lcd.cir"

# The lcd's own electrical contract — NOT board values. The gated panel/touch
# rail is 3.3 V class; the boost input is 5 V class; the touch-clamp rail is the
# always-on 3.3 V class; the boost OUTPUT node rides to the 30 V open-LED OVP
# clamp (the binding cap-derate case).
RAIL_WORST_V = {"+VBOOST_IN": 5.0, "+VDD_LCD": 3.3, "+VDD_TP_CLAMP": 3.3,
                "GND": 0.0}
VLED_OVP_CLAMP_V = 30.0   # SY7201 open-LED OVP clamp (datasheet typ)

# The internal SIGNAL nodes kept VERBATIM from the hand-written sheet (private
# boost wiring; NEVER bindable).
SIGNAL_NODES = ("LCD_BL_SW", "LCD_VLED_P", "LCD_VLED_N", "LCD_PCLK_PANEL",
                "CTP_SDA_FFC", "CTP_SCL_FFC")

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/lcd.py.
_PANEL_PORTS = (
    [f"LCD_R{i}" for i in range(8)] + [f"LCD_G{i}" for i in range(8)]
    + [f"LCD_B{i}" for i in range(8)]
    + ["LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE", "LCD_PCLK"])
_CARRIER_BIND = {
    "+VBOOST_IN": "+5V_LCD", "+VDD_LCD": "+3V3_LCD",
    "+VDD_TP_CLAMP": "+3V3", "GND": "GND",
    **{p: p for p in _PANEL_PORTS},
    "BL_PWM": "LCD_BL_PWM",
    "TP_SDA": "LCD_CTP_SDA", "TP_SCL": "LCD_CTP_SCL",
    "TP_RST": "LCD_CTP_RST", "TP_INT": "LCD_CTP_INT",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return lcd.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _caps_to_gnd(c: Circuit, rail: str) -> list[str]:
    out = []
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C"):
            continue
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        if rail in names and "GND" in names:
            out.append(p.value)
    return sorted(out)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(lcd.INTERFACE), externals
    # the abstract names must not be the carrier's real net names (the carrier
    # gates the rails +5V_LCD / +3V3_LCD and names its touch group LCD_CTP_*);
    # a standalone build must carry NONE of those.
    carrier_real = set(_CARRIER_BIND.values()) - {"GND"} | {"LCD_CTP_INT"}
    leaked = externals & {r for r in carrier_real
                          if r not in lcd.INTERFACE}
    assert not leaked, leaked
    assert "LCD_CTP_SDA" not in externals and "+5V_LCD" not in externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in lcd.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in lcd.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_internal_signal_nodes_kept_verbatim(c: Circuit):
    """The private boost / FFC-side wiring stays SIGNAL-class with its verbatim
    names (NOT exposed as part of the abstract interface)."""
    cls = {n.name: n.net_class for n in c.nets.values()}
    for node in SIGNAL_NODES:
        assert cls.get(node) is NetClass.SIGNAL, (node, cls.get(node))
        assert node not in lcd.INTERFACE, node


def test_touch_i2c_typed(c: Circuit):
    assert c.port_type_of("TP_SDA").kind == "i2c"
    assert c.port_type_of("TP_SDA").role == "sda"
    assert c.port_type_of("TP_SCL").role == "scl"
    assert c.port_type_of("TP_SDA").bus == c.port_type_of("TP_SCL").bus
    assert c.port_type_of("TP_SDA").bus == lcd.I2C_BUS


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats). The only
    intentional no-connects are FFC pin 35 (panel NC) + the shell tabs 41/42."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert {str(p) for p in c.nc_pins} == {"J1.35", "J1.41", "J1.42"}


# ---- decoupling / I2C / reset completeness (design_rules LOCAL slice) -----------

def test_design_rules_slice_clean(c: Circuit, lib: Library):
    """DECAP/EP/STRAP/I2C/RESET: no design-rule finding. The touch I2C pull-ups
    live HERE (to the gated rail), so the I2C-pull-up rule is exercised and
    satisfied; TP_RST is a GPIO-driven reset (waived), so the reset slice runs
    without an RC-reset finding."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert not r.i2c, r.i2c
    # the touch I2C bus (SCL+SDA) is actually exercised (not a no-op)
    assert r.checked.get("i2c", 0) >= 2
    # the TP_RST reset waiver is exercised (a driven reset, not RC)
    assert r.checked.get("reset", 0) >= 1


def test_touch_i2c_pullups_on_gated_rail(c: Circuit):
    """The two 4k7 touch-I2C pull-ups (R2/R3) land on the GATED +VDD_LCD rail so
    a powered-down panel is not back-fed through them; the DISP 10k pull-up (R6)
    sits on the same rail (default-ON when gated up)."""
    for ref, val, leg in (("R2", "4k7", "TP_SDA"), ("R3", "4k7", "TP_SCL"),
                          ("R6", "10k", "LCD_DISP")):
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        assert c.parts[ref].value == val, ref
        assert names == {"+VDD_LCD", leg}, (ref, names)


def test_default_state_pulls(c: Circuit):
    """Safe-default pulls: TP_RST 100k pull-down (held in reset) and BL_PWM 100k
    pull-down (backlight off) — both to GND."""
    for ref, leg in (("R5", "TP_RST"), ("R4", "BL_PWM")):
        names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                  c.net_of(PinRef(ref, "2"))) if n}
        assert c.parts[ref].value == "100k", ref
        assert names == {"GND", leg}, (ref, names)


# ---- backlight boost topology ---------------------------------------------------

def test_boost_topology(c: Circuit):
    """The SY7201 boost network is on the expected (internal SIGNAL) nodes:
      * 10u input bulk on +VBOOST_IN, 2.2u output cap on the OVP-sense node,
      * the 1.5R ISET current-sense from the LED-return node to GND,
      * the inductor +VBOOST_IN -> LX node and the catch diode LX -> output."""
    # input bulk + output cap
    assert "10u" in _caps_to_gnd(c, "+VBOOST_IN")
    assert _caps_to_gnd(c, "LCD_VLED_P") == ["2.2u"]   # 50V boost-output cap
    # ISET sense: 1.5R from the LED-string return to GND
    r1 = {n.name for n in (c.net_of(PinRef("R1", "1")),
                           c.net_of(PinRef("R1", "2"))) if n}
    assert c.parts["R1"].value == "1.5R" and r1 == {"LCD_VLED_N", "GND"}, r1
    # inductor across the boost input -> switch node; catch diode switch -> out
    l1 = {n.name for n in (c.net_of(PinRef("L1", "1")),
                           c.net_of(PinRef("L1", "2"))) if n}
    assert l1 == {"+VBOOST_IN", "LCD_BL_SW"}, l1
    d1 = {n.name for n in (c.net_of(PinRef("D1", "1")),
                           c.net_of(PinRef("D1", "2"))) if n}
    assert d1 == {"LCD_BL_SW", "LCD_VLED_P"}, d1


def test_pclk_source_series_damping(c: Circuit):
    """PCLK is brought through a 22R source-series damping resistor (R7) from the
    port to the FFC-side internal node — not a bare connection."""
    r7 = {n.name for n in (c.net_of(PinRef("R7", "1")),
                           c.net_of(PinRef("R7", "2"))) if n}
    assert c.parts["R7"].value == "22R" and r7 == {"LCD_PCLK", "LCD_PCLK_PANEL"}


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


def test_rail_caps_voltage_derated(c: Circuit):
    """Each bypass cap on a rail is voltage-rated for the worst-case voltage of
    that rail (the subsystem's own RAIL_WORST_V) with a >=1.3x ceramic margin."""
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


def test_boost_output_cap_clears_ovp_clamp(c: Circuit):
    """The boost output cap (C2 on LCD_VLED_P) is 50 V-rated and clears the 30 V
    open-LED OVP clamp transient (LCD-1: a fault clamp, not continuous bias —
    the continuous string is ~9.6 V; the 2x-DC-bias derate is waived)."""
    c2 = next(p for ref, p in c.parts.items()
              if p.lib_id.endswith(":C")
              and "LCD_VLED_P" in {n.name for n in
                                   (c.net_of(PinRef(ref, "1")),
                                    c.net_of(PinRef(ref, "2"))) if n})
    assert RATINGS_BY_LCSC[c2.fields["LCSC"]].v_max >= VLED_OVP_CLAMP_V
    assert "C2" in c.part_rule_waivers   # the CAP_VOLTAGE derate is waived


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    """The board's per-part rating engine raises NO hard finding on this
    subsystem (caps read as 'rail unresolved' on abstract rails — fail-soft —
    which is acceptable for a standalone subsystem; the waived C2 stays clean)."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt ↔ netlist passives --------------------------------------------

def _cir_passives() -> dict[str, float]:
    """Parse the .cir R/C lines into {refdes: value_in_si}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt lcd"):
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
    """The .cir subckt declares abstract ports as its pins (a project wires them
    to real nets, exactly as the netlist bind does). The bare RGB/sync data lines
    and TP_INT carry no subsystem-local passive, so they are not subckt pins."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt lcd"))
    pins = header.split()[2:]
    assert pins == ["VBOOST_IN", "VDD_LCD", "VDD_TP_CLAMP", "LCD_DISP",
                    "TP_SDA", "TP_SCL", "TP_RST", "LCD_PCLK", "BL_PWM",
                    "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in lcd.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's passive network equals the netlist's R+C, value-for-value
    (the .cir cannot silently drift from the circuit). The inductor + diode are
    not R/C lines and so are matched by topology in test_boost_topology."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C") or p.lib_id.endswith(":R"))
    cir = sorted(_cir_passives().values())
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
    base = lcd.circuit()
    bound = lcd.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; SIGNAL nets keep their verbatim
    # names; insertion order preserved (byte-identical emit)
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the internal SIGNAL boost nodes were NOT renamed
    for node in SIGNAL_NODES:
        assert node in bound.nets, node
    # the touch I2C bus typing survives the rename
    assert bound.port_type_of("LCD_CTP_SDA").role == "sda"
    assert bound.port_type_of("LCD_CTP_SCL").bus == lcd.I2C_BUS
    # the draw budgets followed the renamed rails
    assert "+3V3_LCD" in bound.loads and "+VDD_LCD" not in bound.loads
    assert "+5V_LCD" in bound.loads and "+VBOOST_IN" not in bound.loads
    # the testpoint VALUE text follows the rename (probes a renamed external)
    tp_vals = {p.value for r, p in bound.parts.items()
               if p.lib_id == bound.TP_LIB_ID}
    assert "+5V_LCD" in tp_vals and "LCD_CTP_SDA" in tp_vals


def test_bind_identity_is_noop():
    base = lcd.circuit()
    ident = lcd.circuit({"bind": {n: n for n in lcd.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    """The standard meta contract: buses["i2c"] renames the bus group and
    notes["draws_*"] override the power-tree notes — without changing the netlist
    topology (a project restores its own house-style metadata)."""
    base = lcd.circuit()
    m = lcd.circuit({"buses": {"i2c": "MY_TOUCH_I2C"},
                     "notes": {"draws_lcd": "lcd note",
                               "draws_boost": "boost note"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("TP_SDA").bus == "MY_TOUCH_I2C"
    assert m.port_type_of("TP_SCL").bus == "MY_TOUCH_I2C"
    assert m.loads["+VDD_LCD"][0][1] == "lcd note"      # (amps, note)
    assert m.loads["+VBOOST_IN"][0][1] == "boost note"


def test_meta_expects_attaches_port_deferral():
    """meta["expects"] attaches an explicit linker deferral to a port without
    changing the netlist topology (a project declares which sheet binds it)."""
    m = lcd.circuit({"expects": {"LCD_R0": "som_j3 (bank 34)",
                                 "TP_SDA": "som_j2 (bank 13)"}})
    assert m.port_type_of("LCD_R0").expect == "som_j3 (bank 34)"
    assert m.port_type_of("TP_SDA").expect == "som_j2 (bank 13)"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        lcd.circuit({"bus": {"i2c": "X"}})        # 'bus' != 'buses'


def test_bind_rejects_unknown_name():
    c = lcd.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_LCD"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. lcd HAS its
    own SIGNAL nets (the boost switch node), so bind one of them directly."""
    c = lcd.circuit()
    assert c.nets["LCD_BL_SW"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"LCD_BL_SW": "SOMETHING"})


def test_bind_rejects_collision():
    c = lcd.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"TP_SDA": "SHARED", "TP_SCL": "SHARED"})


def test_bound_circuit_passes_local_design_rules(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local design-rules
    slice (binding is a pure rename; electrical completeness is unchanged)."""
    bound = lcd.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap or r.i2c), r.findings
