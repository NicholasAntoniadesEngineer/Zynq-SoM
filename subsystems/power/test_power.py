"""LOCAL electrical-correctness test for the power reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog; no kicad-cli, no network, no board). Mirrors subsystems/usb_pd/
test_usb_pd.py + subsystems/usbc_otg/test_usbc_otg.py so every migrated subsystem
follows the same shape.

This subsystem is the carrier's largest — a +VIN -> +5V buck (LM61460) -> +3V3
buck (LM61460, re-spec'd from a no-EP TPS54302 by a thermal finding) -> +1V8 LDO
chain — so the local checks add the power-specific electrical invariants:

  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), the EN ports are PORTs.
  * the faithful U1 dossier symbol — U1 draws parts/LM61460AANRJRR/ (no
    lib_id= override; the "0 hand-built symbols" migration), netlist-neutral.
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap-to-GND, exposed pad on GND, no floating strap.
  * the LM61460 heat path         — PGND1/PGND2/AGND all on GND (the VQFN-HR has
    no center EP; its EP-equivalent is those power-ground pads on the GND pour).
  * FB-divider ratios             — each adjustable regulator's FB divider sets
    the documented output (Vout = Vref*(1+Rtop/Rbot)): +5V 40.2k/10k @ Vref 1.0,
    +3V3 23.2k/10k @ Vref 1.0 — proving the BOM-critical FB resistors.
  * reg-side vs rail-side split   — the FB sense + output bulk sit on the REG-
    side rail; the board RAIL the loads see is a SEPARATE external net (a
    project's series shunt bridges them) — the topology that lets a current
    monitor measure consumer draw without seeing the regulator's own caps.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for that rail
    (the subsystem's own RAIL_WORST_V; the +VIN 21 V input caps are the binding
    case).
  * SPICE passives                — the .cir subckt's interface-spanning passive
    network matches the netlist one-for-one (parse_si), analytic spice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, is order-preserving, the EN deferral +
    draw-note overrides survive.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
EN linker graph, the full power-tree headroom across the regulator tree, the
thermal join, board ERC and the board netlist merge. Those are aggregated by
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

import subsystems.power.power as power

HERE = Path(__file__).resolve().parent
CIR = HERE / "power.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/power.py.
_CARRIER_BIND = {
    "+VIN": "+VIN_SYS",
    "+VOUT_5V_REG": "+5V_REG",
    "+VOUT_5V": "+5V",
    "+VOUT_3V3_REG": "+3V3_REG",
    "+VOUT_3V3": "+3V3",
    "+VOUT_1V8_REG": "+1V8_REG",
    "+VOUT_1V8": "+1V8",
    "GND": "GND",
    "EN_VOUT_5V": "EN_5V0",
    "EN_VOUT_3V3": "EN_3V3",
    "EN_VOUT_1V8": "EN_1V8",
}

# The interface-spanning caps the .cir models (both pins on an external net).
# Caps that touch an internal SIGNAL node (BOOT/VCC/BIAS/FB feedforward) are
# private regulator wiring and are NOT subckt elements.
_CIR_REFS = {"C1", "C25", "C2", "C3", "C5", "C6", "C26",
             "C7", "C29", "C8", "C30", "C10", "C11", "C12", "C13"}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return power.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _cap_nets(c: Circuit, ref: str) -> set[str]:
    return {n.name for n in (c.net_of(PinRef(ref, "1")),
                             c.net_of(PinRef(ref, "2"))) if n}


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(power.INTERFACE), externals
    # the abstract names must not be carrier rail/enable net names
    carrier = {"+VIN_SYS", "+5V", "+5V_REG", "+3V3", "+3V3_REG", "+1V8",
               "+1V8_REG", "EN_5V0", "EN_3V3", "EN_1V8"}
    assert not (externals & carrier), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in power.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in power.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_lm61460_faithful_dossier_symbol(c: Circuit):
    """U1 now draws its FAITHFUL parts/LM61460AANRJRR/ dossier symbol (the
    "0 hand-built symbols" migration — schgen:LM61460 is gone from
    symbol_law.PENDING_MIGRATION and from schgen.kicad_sym). The swap is
    NETLIST-NEUTRAL: same lib_id namespace as the dossier + the SAME footprint,
    so connectivity is unchanged — only the schematic drawing changed."""
    u1 = c.parts["U1"]
    assert u1.lib_id == "LM61460AANRJRR:LM61460AANRJRR", u1.lib_id
    assert not u1.lib_id.startswith("schgen:"), u1.lib_id
    assert u1.footprint == "LM61460AANRJRR:LM61460AANRJRR", u1.footprint


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the only intentional no-connects: U1/U2 PGOOD (unused open-drain) + U3 NC
    assert {str(p) for p in c.nc_pins} == {"U1.5", "U2.5", "U3.4"}


def test_lm61460_heat_path_on_gnd(c: Circuit):
    """The VQFN-HR LM61460 has NO center EP — its die-attach heat path is the
    power-ground pads PGND1(9)/PGND2(11) plus AGND(3), all soldered to the GND
    pour (the EP-equivalent). All three must sit on GND (LAW 0: the exposed-pad-
    equivalent is a real GND net, not a prose layout note)."""
    for pin in ("3", "9", "11"):
        n = c.net_of(PinRef("U1", pin))
        assert n is not None and n.name == "GND", (pin, n)


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND on the sheet,
    the exposed pad is on GND, no config strap floats. (Linker-level checks — the
    EN driver graph, full power-tree headroom — are board-level, NOT here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap


def test_each_stage_input_and_output_has_caps(c: Circuit):
    """The datasheet bypass/bulk network is present on each stage, all to GND:
    +5V buck VIN 2x100n + 2x10u and output 3x22u; +3V3 buck (LM61460) VIN
    2x100n + 2x22u bulk and output 2x22u; LDO input 1u and output 1u."""
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = _cap_nets(c, ref)
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VIN") == ["100n", "100n", "10u", "10u"]
    assert caps_to_gnd("+VOUT_5V_REG") == ["22u", "22u", "22u"]
    # +3V3 buck (LM61460) input on the board +5V rail: 2x100n HF + 2x22u bulk
    assert caps_to_gnd("+VOUT_5V") == ["100n", "100n", "22u", "22u"]
    assert caps_to_gnd("+VOUT_3V3_REG") == ["22u", "22u"]
    assert caps_to_gnd("+VOUT_3V3") == ["1u"]            # LDO input cap
    assert caps_to_gnd("+VOUT_1V8_REG") == ["1u"]        # LDO output cap


# ---- FB-divider ratios (the BOM-critical regulator output set) ------------------

def _r_value(c: Circuit, ref: str) -> float:
    return parse_si(c.parts[ref].value)


def test_fb_divider_ratios_set_documented_outputs(c: Circuit):
    """Each adjustable regulator's FB divider sets the documented output,
    Vout = Vref*(1 + Rtop/Rbot). These are BOM-CRITICAL (a mis-keyed FB-top
    resistor would set a destructive rail) so the ratio is asserted directly."""
    # +5V buck (LM61460): Vref 1.0 V, R1/R2 = 40.2k/10k -> 5.02 V
    vout_5v = 1.0 * (1 + _r_value(c, "R1") / _r_value(c, "R2"))
    assert abs(vout_5v - 5.02) < 0.05, vout_5v
    # the FB-top resistor really is 40.2k (NOT a 120k mis-key -> ~13 V, fatal)
    assert _r_value(c, "R1") == 40.2e3
    # +3V3 buck (LM61460): Vref 1.0 V, R4/R5 = 23.2k/10k -> 3.32 V, CENTRED in the
    # +3V3 +/-3% window [3.201, 3.399] (audit 2026-06-20 re-centred from 22.1k/3.21V,
    # whose worst-case low touched the -5% floor; C23346 0603WAF2322T5E).
    vout_3v3 = 1.0 * (1 + _r_value(c, "R4") / _r_value(c, "R5"))
    assert 3.201 <= vout_3v3 <= 3.399, vout_3v3
    assert _r_value(c, "R4") == 23.2e3 and _r_value(c, "R5") == 10e3


def test_reg_side_vs_rail_side_split(c: Circuit):
    """The output bulk caps + the FB sense sit on the REG-side rail; the board
    RAIL the loads see is a SEPARATE external net. This is the series-shunt
    topology a current monitor needs: a project bridges +VOUT_x_REG -> +VOUT_x
    so consumer draw flows through the shunt, NOT the regulator's own caps."""
    # +5V FB top senses the reg-side node, not the rail the loads see.
    assert _cap_nets(c, "C5") == {"+VOUT_5V_REG", "GND"}        # output bulk
    assert "+VOUT_5V_REG" in {n.name for n in
                              (c.net_of(PinRef("R1", "1")),) if n}
    # the +3V3 buck CONSUMES the board +5V rail (its input cap sits there), so
    # the +5V consumer draw is measurable on the rail-side net.
    assert _cap_nets(c, "C7") == {"+VOUT_5V", "GND"}           # +3V3 buck input
    assert _cap_nets(c, "C8") == {"+VOUT_5V", "GND"}
    # the LDO consumes the board +3V3 rail; its output bulk is on the reg-side.
    assert _cap_nets(c, "C12") == {"+VOUT_3V3", "GND"}        # LDO input
    assert _cap_nets(c, "C13") == {"+VOUT_1V8_REG", "GND"}    # LDO output
    # the two sides are genuinely DISTINCT nets (never collapsed in the library)
    for reg, rail in (("+VOUT_5V_REG", "+VOUT_5V"),
                      ("+VOUT_3V3_REG", "+VOUT_3V3"),
                      ("+VOUT_1V8_REG", "+VOUT_1V8")):
        assert reg in c.nets and rail in c.nets and reg != rail


def test_internal_signal_nets_kept_verbatim(c: Circuit):
    """The private regulator wiring stays SIGNAL with its verbatim names (never
    promoted to an external rail/port): SW/FB/BOOT/BIAS/VCC/RT + the PG-LED
    cathode / FET-gate nodes."""
    signal = {n.name for n in c.nets.values()
              if n.net_class is NetClass.SIGNAL}
    assert signal == {
        "U1_VCC", "BIAS_5V0", "RT_5V0", "BOOT_5V0", "SW_5V0", "FB_5V0",
        "CFF_5V0", "PG_5V0",
        "U2_VCC", "BIAS_3V3", "RT_3V3", "BOOT_3V3", "SW_3V3", "FB_3V3",
        "CFF_3V3", "PG_3V3",
        "PG_1V8_G", "PG_1V8_D", "PG_1V8_K"}, signal


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_bulk_bypass_caps_have_a_ratings_row(c: Circuit):
    """Rating coverage for the caps that ride a rail: every bypass/bulk cap that
    sits between an external rail and GND resolves in the ratings catalog so its
    derate can be judged. (Small C0G FB-feedforward caps + the resistor BOM are
    NOT voltage-derated parts — the board catalog covers them fail-soft via
    part_rules — so only the rail-riding bypass/bulk caps are asserted here.)"""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        rail_v = max((power.RAIL_WORST_V.get(n, 0.0)
                      for n in _cap_nets(c, ref)), default=0.0)
        if rail_v <= 0 or "GND" not in _cap_nets(c, ref):
            continue                       # not a rail-to-GND bypass/bulk cap
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"rail bypass caps with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    """Each rail-to-GND bypass/bulk cap is voltage-rated for the worst-case
    voltage of the rail it sits on (the subsystem's own RAIL_WORST_V), with a
    >=1.3x ceramic margin. The +VIN input caps (ride up to 21 V) are the binding
    case. (Caps spanning an internal SIGNAL node — FB feedforward, BOOT — are
    not rail-derated parts and are skipped, as the board part_rules engine does.)"""
    worst = power.RAIL_WORST_V
    checked_vin = False
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        nets = _cap_nets(c, ref)
        rail_v = max((worst.get(n, 0.0) for n in nets), default=0.0)
        if rail_v <= 0 or "GND" not in nets:
            continue
        lcsc = p.fields.get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            continue                       # not a catalogued derate part
        rat = RATINGS_BY_LCSC[lcsc]
        assert rat.v_max is not None and rat.v_max >= 1.3 * rail_v, (
            f"{ref} {p.value}: {rat.v_max}V cap on a {rail_v}V rail "
            f"(<1.3x margin)")
        if "+VIN" in nets:
            checked_vin = True
    assert checked_vin, "the +VIN 21 V input caps were not exercised"


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
        if s.lower().startswith(".subckt power"):
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
    """The .cir subckt declares the abstract rails as its pins (a project wires
    them to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt power"))
    pins = header.split()[2:]
    assert pins == ["VIN", "VOUT_5V_REG", "VOUT_5V", "VOUT_3V3_REG",
                    "VOUT_3V3", "VOUT_1V8_REG", "VOUT_1V8", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in power.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's passive network equals the netlist's interface-spanning caps
    (both pins on an external net), value-for-value — the .cir cannot silently
    drift from the circuit. Caps on internal SIGNAL nodes (BOOT/VCC/BIAS/FB
    feedforward) are private wiring and are documented, not modelled."""
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_REFS)
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)
    # the modelled refs are exactly the interface-spanning caps (no drift)
    assert set(_cir_caps()) == _CIR_REFS


def test_cir_excludes_internal_signal_caps(c: Circuit):
    """Sanity: the caps NOT in the .cir all touch an internal SIGNAL net (so the
    subckt's two-interface-net rule is faithful)."""
    for ref, p in c.parts.items():
        if not p.lib_id.endswith(":C") or ref in _CIR_REFS:
            continue
        nets = _cap_nets(c, ref)
        signal = {n for n in nets
                  if c.nets[n].net_class is NetClass.SIGNAL}
        assert signal, (ref, nets)


def test_spice_analytic_slice_runs_clean_when_bound():
    """The analytic spice gate finds no divider/RC/FB violation and raises no
    error. The FB-divider VOLTAGE check is intrinsically rail-NAME-aware (it
    validates the divider against the real rail's nominal voltage via
    powertree.rail_volts), so — like the I2C pull-up / power-tree headroom — it
    is a board-level concern that runs on the BOUND circuit with the project's
    real rail names. (Run on the abstract names, rail_volts returns 0 V and the
    divider check has no nominal to compare against; that's expected, hence the
    bind.) Here we prove the divider/RC/EN-clamp network is well-formed under a
    carrier-style bind."""
    bound = power.circuit({"bind": _CARRIER_BIND})
    res = spice.extract_checks([_sheet(bound)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, internal SIGNAL names and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = power.circuit()
    bound = power.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; internal SIGNAL nets keep their
    # name; net insertion order preserved (byte-identical emit).
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the internal regulator SIGNAL nets are untouched by the bind
    assert "SW_5V0" in bound.nets and "FB_5V0" in bound.nets
    # U1 draws the faithful dossier symbol (the bind never touches lib_id)
    assert bound.parts["U1"].lib_id == "LM61460AANRJRR:LM61460AANRJRR"
    # the draw budgets followed the renamed rails
    assert "+5V" in bound.loads and "+VOUT_5V" not in bound.loads
    assert "+3V3" in bound.loads and "+1V8" in bound.loads


def test_bind_identity_is_noop():
    base = power.circuit()
    ident = power.circuit({"bind": {n: n for n in power.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_expects_and_notes_override_house_style():
    """The standard meta contract: expects[EN] attaches a linker deferral and
    notes["draws_*"] overrides the power-tree note without changing the netlist
    topology (a project restores its own house-style metadata)."""
    base = power.circuit()
    m = power.circuit({
        "expects": {"EN_VOUT_5V": "my-bringup-sheet"},
        "notes": {"draws_5v": "custom 5v note"},
    })
    # same parts + same externals (metadata-only override)
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    # the EN deferral + draw note followed the override
    assert m.port_type_of("EN_VOUT_5V").expect == "my-bringup-sheet"
    assert m.loads["+VOUT_5V"][0][1] == "custom 5v note"     # (amps, note)
    # an un-overridden draw keeps the library default
    assert m.loads["+VOUT_1V8"][0][1] == power.DRAWS_1V8_NOTE


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        power.circuit({"note": {"draws_5v": "X"}})        # 'note' != 'notes'


def test_bind_rejects_unknown_name():
    c = power.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_RAIL": "+5V"})


def test_bind_rejects_signal_net():
    """An internal regulator SIGNAL net is private wiring — binding one is a hard
    error (LAW 0: never rebind the switch/FB/BOOT nodes)."""
    c = power.circuit()
    assert c.nets["SW_5V0"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"SW_5V0": "SOMETHING"})


def test_bind_rejects_collision():
    c = power.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"+VOUT_5V_REG": "SHARED", "+VOUT_5V": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = power.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
