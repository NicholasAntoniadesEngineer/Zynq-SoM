"""LOCAL electrical-correctness test for the hdmi_tx reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables +
ratings catalog; no kicad-cli, no network, no board). Co-located with the
package so a future migration of any other subsystem follows the same shape.
See subsystems/usb_pd/test_usb_pd.py for the worked exemplar.

LOCAL checks (what a subsystem can prove about ITSELF):
  * declared abstract interface  — RAILS/PORTS present with the right net class,
    every IC/connector pin netted-or-NC (model completeness), port types as
    declared (the 4 TMDS pairs + the DDC i2c bus).
  * decoupling completeness       — design_rules DECAP/EP/STRAP slice: every IC
    supply pin has a local cap to GND, no floating config strap (the DDC
    pull-up rule is WAIVED — pull-ups are integrated in the TPD12S016).
  * part ratings                  — every BOM passive's LCSC resolves in the
    ratings catalog and each cap is voltage-derated for its rail.
  * SPICE passives                — the .cir subckt's passive network matches the
    netlist one-for-one (parse_si), and the analytic spice slice runs clean.
  * the bind contract             — abstract -> real renames only externals,
    rejects SIGNAL/typo/collision, and a carrier-style bind is order-preserving.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
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

import subsystems.hdmi_tx.hdmi_tx as hdmi_tx

HERE = Path(__file__).resolve().parent
CIR = HERE / "hdmi_tx.cir"

# A carrier-style binding (abstract -> real) used only to exercise bind(); the
# authoritative carrier map lives in carrier/subsystems/hdmi_tx.py.
_CARRIER_BIND = {
    "+VDD_IO": "+3V3_HDMI_TX", "+5V": "+5V_HDMI_TX",
    "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
    "TMDS_D2_P": "ZYNQ_HDMI_TX_TMDS_2_P", "TMDS_D2_N": "ZYNQ_HDMI_TX_TMDS_2_N",
    "TMDS_D1_P": "ZYNQ_HDMI_TX_TMDS_1_P", "TMDS_D1_N": "ZYNQ_HDMI_TX_TMDS_1_N",
    "TMDS_D0_P": "ZYNQ_HDMI_TX_TMDS_0_P", "TMDS_D0_N": "ZYNQ_HDMI_TX_TMDS_0_N",
    "TMDS_CLK_P": "ZYNQ_HDMI_TX_TMDS_CLK_P",
    "TMDS_CLK_N": "ZYNQ_HDMI_TX_TMDS_CLK_N",
    "CEC": "ZYNQ_HDMI_TX_CEC",
    "DDC_SCL": "ZYNQ_HDMI_TX_SCL", "DDC_SDA": "ZYNQ_HDMI_TX_SDA",
    "HPD": "ZYNQ_HDMI_TX_HPD",
}

# Worst-case voltage of each abstract RAIL — the subsystem's own electrical
# contract (V_CCA is a 3.3 V-class rail; V_CC5V rides the cable 5 V). Used by the
# local test to derate the bypass caps without depending on a board power tree.
RAIL_WORST_V = {"+VDD_IO": 3.3, "+5V": 5.0, "GND": 0.0, "CHASSIS_GND": 0.0}


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    """The standalone subsystem (abstract names)."""
    return hdmi_tx.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


# ---- declared abstract interface ------------------------------------------------

def test_interface_is_abstract_and_carrier_free(c: Circuit):
    """Every externally-visible net is one of the declared abstract names — no
    carrier/board net name leaked into the library."""
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(hdmi_tx.INTERFACE), externals
    # the abstract names must not be carrier net names
    assert not any(n.startswith("ZYNQ") or n.endswith("_HDMI_TX")
                   for n in externals), externals
    # the connector-side (B-side) lanes + straps stay PRIVATE SIGNAL wiring
    signals = {n.name for n in c.nets.values()
               if n.net_class is NetClass.SIGNAL}
    assert {"HDMI_TX_CON_5V0", "HDMI_TX_CON_CEC", "HDMI_TX_CON_SCL",
            "HDMI_TX_CON_SDA", "HDMI_TX_CON_HPD",
            "HDMI_TX_LS_OE", "HDMI_TX_CT_HPD"} == signals, signals


def test_rail_and_port_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    for rail in hdmi_tx.RAILS:
        want = NetClass.GROUND if rail in ("GND", "CHASSIS_GND") \
            else NetClass.POWER
        assert cls[rail] is want, (rail, cls[rail])
    for port in hdmi_tx.PORTS:
        assert cls[port] is NetClass.PORT, (port, cls[port])


def test_tmds_pairs_and_ddc_bus_typed(c: Circuit):
    """The 4 TMDS lanes are 100 Ω tmds_pairs (P<->N reciprocal), and the DDC
    bus carries its i2c typing (scl/sda on one named bus)."""
    for p_pos, p_neg in hdmi_tx.TMDS_PAIRS:
        tp, tn = c.port_type_of(p_pos), c.port_type_of(p_neg)
        assert tp.kind == "tmds_pair" and tn.kind == "tmds_pair"
        assert tp.impedance == 100 and tn.impedance == 100
        assert tp.pair_with == p_neg and tn.pair_with == p_pos
    assert c.port_type_of("DDC_SCL").kind == "i2c"
    assert c.port_type_of("DDC_SCL").role == "scl"
    assert c.port_type_of("DDC_SDA").role == "sda"
    assert c.port_type_of("DDC_SCL").bus == c.port_type_of("DDC_SDA").bus
    assert c.port_type_of("DDC_SCL").bus == hdmi_tx.DDC_BUS


def test_tmds_lane_is_one_flow_through_net(c: Circuit):
    """LAW 0: each TMDS lane is ONE net joining the TPD clamp pad (U1) and the
    receptacle (J1) — source -> clamp -> connector, no split."""
    for port, upin, jpin in hdmi_tx.TMDS_LANES:
        pins = {str(p) for p in c.nets[port].pins}
        assert pins == {f"U1.{upin}", f"J1.{jpin}"}, (port, pins)


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Model completeness: every physical pin of every part is netted or NC —
    the same hard check the board build runs (LAW 0: no silent floats)."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # HDMI pin 14 (HEC/Utility) is the only intentional no-connect
    assert {str(p) for p in c.nc_pins} == {"J1.14"}


# ---- decoupling completeness (design_rules LOCAL slice) -------------------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP: every IC supply pin has a local cap-to-GND, no config
    strap floats. (The DDC I2C-pull-up rule is WAIVED — pull-ups are integrated
    in the TPD12S016, DS 7.3.9/7.3.15 — so it is not asserted here.)"""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the supply rails are actually exercised (not a no-op)
    assert r.checked.get("decap", 0) >= 1


def test_each_rail_has_a_local_bypass(c: Circuit):
    """The datasheet bypass network is present: V_CCA 100n+10u, V_CC5V 100n, and
    the cable +5V node 100n+1u — all to GND on this sheet."""
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
    assert caps_to_gnd("+VDD_IO") == ["100n", "10u"]
    assert caps_to_gnd("+5V") == ["100n"]
    assert caps_to_gnd("HDMI_TX_CON_5V0") == ["100n", "1u"]


def test_always_on_straps_pulled_to_vcca(c: Circuit):
    """LS_OE + CT_HPD are 10k to +VDD_IO (DS Fig 15) — no floating config pin."""
    for strap in ("HDMI_TX_LS_OE", "HDMI_TX_CT_HPD"):
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":R"):
                continue
            nets = {n.name for n in
                    (c.net_of(PinRef(ref, "1")), c.net_of(PinRef(ref, "2")))
                    if n}
            if strap in nets:
                assert "+VDD_IO" in nets and p.value == "10k", (strap, nets)
                break
        else:
            pytest.fail(f"no 10k strap on {strap}")


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
    """Each rail-bypass cap is voltage-rated for the worst-case voltage of the
    rail it sits on (RAIL_WORST_V), with a >=1.3x ceramic margin. The cable-5V
    node bypasses ride the 5 V V_CC5V domain."""
    worst = dict(RAIL_WORST_V)
    worst["HDMI_TX_CON_5V0"] = 5.0   # the switched cable +5V node
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

def _cir_caps() -> dict[str, float]:
    """Parse the .cir capacitor lines into {refdes: farads}."""
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt hdmi_tx"):
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
                  if l.strip().lower().startswith(".subckt hdmi_tx"))
    pins = header.split()[2:]
    assert pins == ["VDD_IO", "5V", "GND"], pins
    # every subckt pin is a real abstract interface net (sans the '+' rail mark)
    iface = {n.lstrip("+") for n in hdmi_tx.INTERFACE}
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
    subsystem (it has none — pure bypass + strap network) and raises no
    error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- the bind contract (the reuse API) ------------------------------------------

def test_bind_renames_only_externals_byte_stable():
    """A carrier-style bind renames every external to the real net and touches
    nothing else: part set, refs, NCs, port-type kinds and draw budgets are
    preserved, and the nets dict keeps insertion order (byte-identical emit)."""
    base = hdmi_tx.circuit()
    bound = hdmi_tx.circuit({"bind": _CARRIER_BIND})
    # same parts/refs/NCs
    assert set(bound.parts) == set(base.parts)
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}
    # externals renamed exactly per the map; order preserved (SIGNAL nets are
    # private and keep their name — only the externals in the bind map move)
    assert list(bound.nets) == [_CARRIER_BIND.get(n, n) for n in base.nets]
    # the DDC i2c typing survives the rename
    assert bound.port_type_of("ZYNQ_HDMI_TX_SCL").role == "scl"
    assert bound.port_type_of("ZYNQ_HDMI_TX_TMDS_2_P").kind == "tmds_pair"
    # the draw budgets followed the renamed rails
    assert "+3V3_HDMI_TX" in bound.loads and "+VDD_IO" not in bound.loads
    assert "+5V_HDMI_TX" in bound.loads and "+5V" not in bound.loads
    # the pull-up waivers followed the renamed DDC nets
    assert "ZYNQ_HDMI_TX_SCL" in bound.pull_waivers
    assert "ZYNQ_HDMI_TX_SDA" in bound.pull_waivers


def test_bind_identity_is_noop():
    base = hdmi_tx.circuit()
    ident = hdmi_tx.circuit({"bind": {n: n for n in hdmi_tx.INTERFACE}})
    assert list(ident.nets) == list(base.nets)


def test_meta_buses_and_notes_override_house_style():
    """The standard meta contract: buses["ddc"] renames the bus group and
    notes["draws_*"] override the power-tree notes — without changing the
    netlist topology (a project restores its own house-style metadata)."""
    base = hdmi_tx.circuit()
    m = hdmi_tx.circuit({"buses": {"ddc": "MY_DDC"},
                         "notes": {"draws_vcca": "custom vcca",
                                   "draws_5v": "custom 5v"}})
    assert set(m.parts) == set(base.parts)
    assert list(m.nets) == list(base.nets)
    assert m.port_type_of("DDC_SCL").bus == "MY_DDC"
    assert m.port_type_of("DDC_SDA").bus == "MY_DDC"
    assert m.loads["+VDD_IO"][0][1] == "custom vcca"   # (amps, note)
    assert m.loads["+5V"][0][1] == "custom 5v"


def test_meta_rejects_unknown_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        hdmi_tx.circuit({"bus": {"ddc": "X"}})        # 'bus' != 'buses'


def test_bind_rejects_unknown_name():
    c = hdmi_tx.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_PORT": "X"})


def test_bind_rejects_signal_net():
    """A SIGNAL net is private wiring — binding one is a hard error. hdmi_tx's
    own connector-side lanes are SIGNAL, so try to bind one."""
    c = hdmi_tx.circuit()
    assert c.nets["HDMI_TX_CON_5V0"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c.bind({"HDMI_TX_CON_5V0": "SOMETHING"})


def test_bind_rejects_collision():
    c = hdmi_tx.circuit()
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({"TMDS_D2_P": "SHARED", "TMDS_D2_N": "SHARED"})


def test_bound_circuit_passes_local_decap(lib: Library):
    """Sanity: the carrier-bound circuit still passes the local decoupling slice
    (binding is a pure rename; electrical completeness is unchanged)."""
    bound = hdmi_tx.circuit({"bind": _CARRIER_BIND})
    r = design_rules.check([_sheet(bound)], lib)
    assert not (r.decap or r.ep or r.strap), r.findings
