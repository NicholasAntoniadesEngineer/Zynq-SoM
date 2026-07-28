"""LOCAL electrical-correctness test for the carrier power_som subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board's own verify gates on JUST this
subsystem's circuit, standalone and offline (model + symbol pin tables + ratings
catalog + the analytic SPICE slice; no kicad-cli, no network, no board). Mirrors
the shape of devkit_mini/subsystems/board_services/test_board_services.py, adapted for
the always-on +5V_SOM buck — a CARRIER-LOCAL subsystem (real carrier net names
wired directly, no abstract-interface / bind contract).

LOCAL checks (what this subsystem can prove about ITSELF):
  * model completeness   — every physical pin netted-or-NC (LAW 0: no floats),
    and the ONLY intentional no-connect is U4.5 (PGOOD, unused open-drain).
  * decoupling / heat    — design_rules DECAP/EP/STRAP slice clean: every IC
    supply pin has a local cap-to-GND; and the LM61460 EP-equivalent heat path
    (PGND1/PGND2/AGND) is all on GND (LAW 0: a real GND net, not a prose note).
  * part ratings         — every BOM passive's LCSC resolves in the ratings
    catalog and the per-part rating engine raises no hard finding.
  * FB-divider invariant — R14/R15 = 47.5k/13k sets Vout = Vref*(1+Rtop/Rbot) =
    4.654 V (Vref 1.0 V), inside the SoM 4.2-5.0 V input window — the BOM-critical
    output set the P0/PWR-5 fix depends on.
  * SPICE passives       — the .cir subckt's capacitor network whose elements
    span two external nets matches the netlist one-for-one (parse_si), the subckt
    pins are the carrier externals, and the analytic spice slice runs clean.
  * netlist invariants   — the PWR-1 EN clamp topology, the always-on EN (no
    bring-up port), BOOT/RBOOT short, BIAS-to-VOUT tie, and the input/output
    bulk network.

CROSS-BOARD checks deliberately stay at board level (not duplicated here): the
EN spice/clamp re-derivation, the full power-tree headroom, the thermal join,
board ERC and the board netlist merge — all aggregated by `schgen board`.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

from devkit_mini.subsystems.power_som import circuit as build

HERE = Path(__file__).resolve().parent
CIR = HERE / "power_som.cir"


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return build()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _pins(c: Circuit, net: str) -> set[str]:
    return {f"{p.ref}.{p.pin}" for p in c.nets[net].pins} if net in c.nets else set()


# ---- model completeness --------------------------------------------------------

def test_is_power_som(c: Circuit):
    assert c.name == "power_som"


def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every physical pin of every part is netted or NC (LAW 0: no silent
    floats) — the same hard check the board build runs."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    # the ONLY intentional no-connect: U4 PGOOD (pin 5, unused open-drain).
    assert {str(p) for p in c.nc_pins} == {"U4.5"}


# ---- decoupling + the LM61460 heat path (design_rules LOCAL slice) --------------

def test_decoupling_complete(c: Circuit, lib: Library):
    """DECAP/EP/STRAP clean: every IC supply pin has a local cap-to-GND, no
    config strap floats."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    assert r.checked.get("decap", 0) >= 1


def test_lm61460_heat_path_on_gnd(c: Circuit):
    """The VQFN-HR LM61460 has NO center EP — its die-attach heat path is the
    power-ground pads PGND1(9)/PGND2(11) plus AGND(3), all soldered to the GND
    pour (the EP-equivalent). All three must sit on GND (LAW 0: the exposed-pad-
    equivalent is a real GND net, not a prose layout note)."""
    gnd = _pins(c, "GND")
    for pin in ("3", "9", "11"):
        assert f"U4.{pin}" in gnd, pin


# ---- part ratings --------------------------------------------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    """Every passive (cap AND resistor) LCSC resolves in the ratings catalog."""
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
    subsystem."""
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- FB-divider invariant (the BOM-critical output set) ------------------------

def test_fb_divider_sets_documented_output(c: Circuit):
    """R14/R15 = 47.5k/13k -> Vout = Vref*(1 + Rtop/Rbot) with Vref = 1.0 V =
    4.654 V nom, inside the SoM 4.2-5.0 V input window (the P0/PWR-5 fix)."""
    rtop = parse_si(c.parts["R14"].value)
    rbot = parse_si(c.parts["R15"].value)
    assert rtop == parse_si("47.5k")
    assert rbot == parse_si("13k")
    vout = 1.0 * (1 + rtop / rbot)
    assert 4.6 < vout < 4.7, vout
    assert 4.2 <= vout <= 5.0, vout            # inside the SoM input window
    # the divider node really is the FB pin + the RFF return
    fb = _pins(c, "FB_5V_SOM")
    assert {"U4.4", "R14.2", "R15.1", "R19.2"} <= fb, fb


# ---- SPICE subckt <-> netlist passives -----------------------------------------

def _cir_caps() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt power_som"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^C\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


# the caps the .cir models (BOTH pins on a carrier external rail — +VIN_SYS,
# +5V_SOM or GND). Caps on a private control node (BOOT/VCC/BIAS/EN/FB FF) are
# NOT subckt elements.
_CIR_CAP_REFS = {"C14", "C25", "C15", "C16", "C18", "C19"}


def test_cir_subckt_pins_are_the_carrier_externals():
    """The .cir subckt declares the carrier external nets as its pins."""
    header = next(l for l in CIR.read_text().splitlines()
                  if l.strip().lower().startswith(".subckt power_som"))
    pins = header.split()[2:]
    assert pins == ["+VIN_SYS", "+5V_SOM", "GND"], pins


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's capacitor network equals the netlist's external-spanning
    caps, value-for-value (the .cir cannot silently drift from the circuit)."""
    netlist = sorted(parse_si(c.parts[r].value) for r in _CIR_CAP_REFS)
    cir = sorted(_cir_caps().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    """The analytic spice gate finds no divider/RC/FB violation and no error."""
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- netlist invariants (the facts the gates do not check by themselves) --------

def test_pwr1_en_clamp_topology(c: Circuit):
    """PWR-1: R12 (series +VIN_SYS->EN) + D5 (5.1 V zener EN->GND) + C20 (EN
    bypass) form the always-on EN clamp on the EN/SYNC pin (U4.7)."""
    en = _pins(c, "EN_5V_SOM")
    assert {"U4.7", "R12.2", "D5.1", "C20.1"} <= en, en
    assert "R12.1" in _pins(c, "+VIN_SYS")        # series R off the buck input
    assert {"D5.2", "C20.2"} <= _pins(c, "GND")   # zener/bypass return
    assert c.parts["D5"].value == "MMSZ5231B"     # 5.1 V zener
    assert c.parts["R12"].value == "10k"


def test_en_is_always_on_no_bringup_port(c: Circuit):
    """The +5V_SOM rail is ALWAYS-ON (P0): EN is strapped on by the clamp, NOT a
    bring-up PORT — so EN_5V_SOM carries no external port."""
    assert not getattr(c, "ports", {})            # no PORTs declared at all
    assert "U4.7" in _pins(c, "EN_5V_SOM")        # EN driven only by the strap


def test_boot_rboot_short_and_bias_tie(c: Circuit):
    """BOOT: RBOOT(13) shorted to CBOOT(14) on the same node (DS EC). BIAS(1)
    tied to VOUT via R17 (10R) + bypassed by C23."""
    boot = _pins(c, "BOOT_5V_SOM")
    assert {"U4.14", "U4.13", "C17.1"} <= boot, boot   # RBOOT/CBOOT same node
    assert "R17.1" in _pins(c, "+5V_SOM")              # BIAS series off VOUT
    bias = _pins(c, "BIAS_5V_SOM")
    assert {"U4.1", "R17.2", "C23.1"} <= bias, bias    # BIAS pin + series + bypass


def test_input_and_output_bulk_present(c: Circuit):
    """Input bypass/bulk on +VIN_SYS (2x100n HF + 2x10u) and output bulk on
    +5V_SOM (2x22u), all to GND — the LM61460 datasheet network."""
    def caps_to_gnd(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            on = {n for n in c.nets if {f"{ref}.1", f"{ref}.2"} & _pins(c, n)}
            if on == {rail, "GND"}:
                out.append(p.value)
        return sorted(out)
    assert caps_to_gnd("+VIN_SYS") == ["100n", "100n", "10u", "10u"]
    assert caps_to_gnd("+5V_SOM") == ["22u", "22u"]


def test_u4_is_the_lm61460_ep_buck(c: Circuit):
    """U4 is the LM61460 6 A EP-equivalent buck (the 2026-06-16 thermal re-spec),
    drawing its faithful dossier symbol (no schgen: lib_id override)."""
    u4 = c.parts["U4"]
    assert u4.lib_id.split(":")[-1] == "LM61460AANRJRR"
    assert not u4.lib_id.startswith("schgen:"), u4.lib_id
    assert (u4.fields or {}).get("LCSC") == "C2864505"
