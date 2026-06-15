"""LOCAL electrical-correctness test for the usb_pd reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). It is co-located with the
package so a future migration of any other subsystem follows the same shape.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC pin netted-or-NC (model completeness), port types as declared.
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap to GND on the sheet, exposed pad on GND, no
    floating config strap.
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and the cap on each rail is voltage-derated for that rail
    (the subsystem's own RAIL_WORST_V, since a board power tree is not present
    locally).
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
I2C/INT pull-up completeness (the pull-ups live on a SHARED bus, off-subsystem),
the link/port-driver graph, the full power-tree headroom, board ERC and the
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

import subsystems.usb_pd.usb_pd as usb_pd

HERE = Path(__file__).resolve().parent
CIR = HERE / "usb_pd.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/usb_pd.py.
_CARRIER_BIND = {
    "+VDD_LOGIC": "+3V3_SC", "+VBUS_SENSE": "+VBUS_IN", "GND": "GND",
    "CC1": "STM32_USB_CC1", "CC2": "STM32_USB_CC2",
    "I2C_SDA": "STM32_I2C2_SDA", "I2C_SCL": "STM32_I2C2_SCL",
    "INT_N": "SC_INT_N",
}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return usb_pd.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(usb_pd.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert not any(n.startswith("STM32") or n.endswith("_SC") or n == "+VBUS_IN"
                   for n in externals), externals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in usb_pd.RAILS:
        want = NetClass.GROUND if rail == "GND" else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in usb_pd.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])
    # CC lines are not typed as a diff pair (CC is single-ended per line);
    # the I2C ports carry their bus typing.
    assert c.port_type_of("I2C_SDA").kind == "i2c"
    assert c.port_type_of("I2C_SCL").role == "scl"
    assert c.port_type_of("I2C_SDA").bus == c.port_type_of("I2C_SCL").bus


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # VCONN is the only intentional no-connect (sourcing unused by design)
    assert {str(p) for p in c.nc_pins} == {"U1.12", "U1.13"}


def test_vconn_unused_by_design(c: Circuit):
    for pin in ("12", "13"):
        assert c.net_of(PinRef("U1", pin)) is None
        assert PinRef("U1", pin) in c.nc_pins


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND, the exposed
    pad is on GND, no config strap floats. (The I2C-pull-up rule is board-level
    — pull-ups are shared off-subsystem — so it is NOT asserted here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the VDD supply rail is actually exercised (not a no-op)
    assert r.checked.get("decap", 0) >= 1


def test_vdd_and_vbus_each_have_a_local_bypass(c: Circuit):
    """The datasheet bypass network is present: VDD 100n+10u, VBUS-sense 100n,
    each CC line a 200p — all to GND on this sheet."""
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
    assert caps_to_gnd("+VDD_LOGIC") == ["100n", "10u"]
    assert caps_to_gnd("+VBUS_SENSE") == ["100n"]
    assert caps_to_gnd("CC1") == ["200p"]
    assert caps_to_gnd("CC2") == ["200p"]


# ---- part ratings (part_rules catalog + local derate) ---------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Local rating coverage: every passive's LCSC resolves in the ratings
    catalog (a part_rules.run on abstract rails reports caps as 'rail
    unresolved', so we assert the catalog coverage directly here)."""
    missing = []
    for ref, p in sorted(c.parts.items()):
        if not p.lib_id.endswith(":C"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"caps with no ratings row: {missing}"


def test_caps_voltage_derated_for_their_rail(c: Circuit):
    """Each bypass cap is voltage-rated for the worst-case voltage of the rail
    it sits on (the subsystem's own RAIL_WORST_V), with a >=1.3x ceramic
    margin. The VBUS-sense cap (rides up to 21 V) is the binding case."""
    worst = usb_pd.RAIL_WORST_V
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
    # the VBUS-sense cap must clear the pin abs-max too
    vbus_cap = next(
        p for ref, p in c.parts.items()
        if p.lib_id.endswith(":C")
        and "+VBUS_SENSE" in {n.name for n in
                              (c.net_of(PinRef(ref, "1")),
                               c.net_of(PinRef(ref, "2"))) if n})
    assert RATINGS_BY_LCSC[vbus_cap.fields["LCSC"]].v_max >= worst["+VBUS_SENSE"]


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
        if s.lower().startswith(".subckt usb_pd"):
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
    them to real nets, exactly as the netlist bind does)."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt usb_pd"))
    pins = header.split()[2:]
    assert pins == ["VDD_LOGIC", "VBUS_SENSE", "CC1", "CC2", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in usb_pd.INTERFACE}
    assert all(p in iface for p in pins), pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's passive network equals the netlist's caps, value-for-value
    (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id.endswith(":C"))
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation on this
    subsystem (it has none — pure bypass network) and raises no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type payloads and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = usb_pd.circuit()
    bound = usb_pd.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; order preserved
    assert list(bound.nets) == [_CARRIER_BIND[n] for n in base.nets]
    # port-type payloads survive the rename (i2c bus/role/speed intact)
    assert bound.port_type_of("STM32_I2C2_SCL").role == "scl"
    assert bound.port_type_of("STM32_I2C2_SDA").bus == usb_pd.I2C_BUS
    # the draw budget followed the renamed rail
    assert "+3V3_SC" in bound.loads and "+VDD_LOGIC" not in bound.loads


def test_bind_identity_is_noop():
    base = usb_pd.circuit()
    ident = usb_pd.circuit({"bind": {n: n for n in usb_pd.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    """The standard meta contract: buses["i2c"] renames the bus group and
    notes["draws"] overrides the power-tree note — without changing the netlist
    topology (a project restores its own house-style metadata)."""
    base = usb_pd.circuit()
    m = usb_pd.circuit({"buses": {"i2c": "MY_I2C"},
                        "notes": {"draws": "custom note"}})
    # same parts + same externals (metadata-only override)
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    # the i2c bus group + draw note followed the override
    assert m.port_type_of("I2C_SDA").bus == "MY_I2C"
    assert m.port_type_of("I2C_SCL").bus == "MY_I2C"
    assert m.loads["+VDD_LOGIC"][0][1] == "custom note"   # (amps, note)


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        usb_pd.circuit({"bus": {"i2c": "X"}})        # 'bus' != 'buses'


def test_bind_rejects_unknown_name():
    c = usb_pd.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "+3V3_SC"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. (usb_pd has
    no SIGNAL net of its own, so synthesize a real 2-pin internal net.)"""
    c2 = Circuit("t", "t")
    c2.part("R1", "Device:R", "1k", "")
    c2.part("R2", "Device:R", "1k", "")
    c2.net("MID", "R1.2", "R2.1")
    assert c2.nets["MID"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c2.bind({"MID": "SOMETHING"})


def test_bind_rejects_collision():
    c = usb_pd.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides"):
        c.bind({"CC1": "SHARED", "CC2": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = usb_pd.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
