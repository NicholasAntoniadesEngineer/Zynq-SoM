"""Tests for the per-device JUNCTION-TEMPERATURE gate (schgen/verify/thermal.py).

Locks: the dissipation model per device kind; the CURRENT board passes (every
speced regulator under its Tj guard band, real device coverage); a synthetic
LDO dropping too much power runs OVER Tj and FAILS; an author waive_thermal
demotes that ERROR to a note; and — the GAP1 honesty lock — every pour-aware
RthJA credit is granted ONLY against copper VERIFIED in the emitted board
(red-on-fiction: the old 58.7->30 C/W basis MUST fail when the copper is not
emitted). Pure/offline (Tj = Ta + Pd*RthJA over the powertree tree; no
kicad-cli, no network — the board evidence is a parsed file / synthetic
BoardCopper)."""

from __future__ import annotations

import types
from pathlib import Path

from schgen.core.model import Circuit
from schgen.verify import powertree, thermal
from schgen.verify.copper_debt import BoardCopper, FpInfo, ViaInfo, ZoneInfo

REPO = Path(__file__).resolve().parents[2]


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def _synthetic_copper(value: str, x: float = 100.0, y: float = 100.0,
                      n_vias: int = 8, pour_layers=("F.Cu", "B.Cu"),
                      plane: bool = True) -> BoardCopper:
    """A minimal BoardCopper granting (or, degraded, denying) a pour credit
    for one instance of ``value`` at (x, y)."""
    bc = BoardCopper(path=Path("synthetic"))
    if plane:
        bc.zones.append(ZoneInfo("GND_plane_In1", "GND", ("In1.Cu",),
                                 keepout=False, filled=True,
                                 bbox=(0.0, 0.0, 200.0, 200.0)))
    for lay in pour_layers:
        bc.zones.append(ZoneInfo(f"thermal_pour_U1_{lay[0]}", "GND", (lay,),
                                 keepout=False, filled=True,
                                 bbox=(x - 4, y - 4, x + 4, y + 4)))
    for i in range(n_vias):
        bc.vias.append(ViaInfo(x + 1.5, y - 2.0 + 0.5 * i, "GND"))
    bc.footprints.append(FpInfo("U1", value, x, y, "F.Cu", ()))
    return bc


def test_dissipation_model():
    spec = thermal.ThermalSpec(rth_ja=250.0, tj_max=125.0, rds_on=0.1, eff=0.85)
    # LDO: (Vin - Vout) * Iout
    assert abs(thermal.dissipation("ldo", 5.0, 1.8, 0.3, spec) - 0.96) < 1e-9
    # buck: (1/eff - 1) * Vout * Iout
    assert abs(thermal.dissipation("buck", 20.0, 5.0, 1.0, spec)
               - (1 / 0.85 - 1) * 5.0 * 1.0) < 1e-9
    # load_switch / efuse: Iout^2 * Rds_on
    assert abs(thermal.dissipation("efuse", 5.0, 5.0, 2.0, spec)
               - 4.0 * 0.1) < 1e-9
    # an unknown kind dissipates nothing in the model
    assert thermal.dissipation("mystery", 5.0, 1.8, 1.0, spec) == 0.0


def test_current_board_passes_thermal():
    """The real board + the real EMITTED copper: every credit verified from
    the .kicad_pcb the build wrote (the same call cmd_board makes)."""
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.verify import copper_debt
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    copper = copper_debt.scan_board(REPO / "carrier" / "Zynq_Carrier.kicad_pcb")
    r = thermal.analyze(sheets, copper=copper, copper_src="Zynq_Carrier")
    assert r.ok, f"unexpected over-Tj devices: {r.errors}"
    assert not r.findings, f"unspeced devices: {r.findings}"
    assert len(r.devices) > 10        # real device coverage, not a no-op
    # the LM61460 bucks must be CREDITED (their copper is emitted), and the
    # hottest of them must carry a real positive margin
    bucks = [d for d in r.devices if d.value.startswith("LM61460")]
    assert len(bucks) == 3 and all(d.poured for d in bucks), \
        [f"{d.sheet}:{d.ref} granted={d.pour_granted}" for d in bucks]


def test_current_board_fails_without_emitted_copper():
    """RED-ON-FICTION (the GAP1 defect, locked): the SAME sheets with NO
    board evidence must FAIL — the LM61460 bucks back out to the bare
    58.7 C/W (power:U1 ~192 C vs the 140 C guard) and the DYD LDO to the
    231 C/W DBV fallback. This is exactly the state the old gate PASSED."""
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = thermal.analyze(sheets)                   # copper=None: fail-closed
    assert not r.ok, "no-copper analysis must FAIL (the fiction the old " \
                     "pour credit hid)"
    u1 = next(d for d in r.devices
              if d.sheet == "power" and d.value.startswith("LM61460"))
    assert not u1.poured and u1.rth_ja == 58.7
    assert u1.tj > 185.0, f"backed-out Tj should be ~192 C, got {u1.tj:.1f}"
    assert any("POUR CREDIT WITHHELD" in e for e in r.errors), r.errors[:2]


def _hot_ldo_sheet():
    # an AP2112K (RthJA 250 C/W, Tj_max 125 C) dropping 5.0 -> 1.8 V at 0.3 A
    # (well inside its 0.6 A current limit) dissipates 0.96 W -> Tj = 50 +
    # 0.96*250 = 290 C, far over the 115 C guard (Tj_max 125 - 10 C margin).
    c = Circuit("th", "th")
    c.part("U1", "Fake:LDO", "AP2112K-1.8", "")
    c.net("+5V_REG", "U1.1")
    c.net("+1V8", "U1.5")
    c.draws("+1V8", 0.3, "synthetic hot LDO")
    return c


def test_over_tj_fails():
    c = _hot_ldo_sheet()
    pt = powertree.analyze([_sheet("th", c)])
    assert pt.ok, f"powertree itself must pass (0.3 A < 0.6 A): {pt.errors}"
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    assert not r.ok, "Tj 290 C must FAIL the guard band"
    assert any("OVER Tj" in e and "U1" in e for e in r.errors), r.errors
    dev = next(d for d in r.devices if d.ref == "U1")
    assert dev.over and dev.margin < 0.0


def test_thermal_waiver_demotes_to_note():
    c = _hot_ldo_sheet()
    c.waive_thermal("U1", "bench-validated copper pour + thermal vias")
    pt = powertree.analyze([_sheet("th", c)])
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    assert r.ok, "an author thermal waiver must clear the hard ERROR"
    assert any("WAIVED over-limit" in n and "U1" in n for n in r.notes), r.notes
    assert "th:U1" in r.waived


def test_tps54302_spec_matches_datasheet():
    """LAW-4 honesty lock: the TPS54302 row carries the DATASHEET RthJA + the
    RECOMMENDED Tj-max, not a fabricated value or the abs-max. TI SLVSDG6C 5.4
    (RthJA 118.9 C/W JESD51-7) + 5.3 (Tj rec-op-max 125 C). No EP -> no pour
    credit (rth_eff == bare). Regression-locks the 2026-06-16 re-base so nobody
    can quietly restore the masking 70.6 C/W / 150 C guard."""
    spec = thermal.THERMAL_SPECS["TPS54302"]
    assert spec.rth_ja == 118.9, "must be the DS JESD51-7 RthJA, not 70.6"
    assert spec.tj_max == 125.0, "must be the rec-op Tj-max, not the 150 abs-max"
    assert spec.rth_ja_pour is None, "no-EP SOT-23 has no pad to pour"
    assert spec.rth_eff == 118.9, "no pour credit -> Tj judged at bare RthJA"


def _tps54302_buck_sheet(iout, vout_rail="+3V3", vin_rail="+5V"):
    """A TPS54302 buck (SW->L->rail) carrying `iout` on its output rail, built
    so powertree detects it (value prefix + SW->inductor->rail hop)."""
    c = Circuit("th", "th")
    c.part("U1", "Regulator_Switching:TPS54302", "TPS54302DDCR",
           "Package_TO_SOT_SMD:TSOT-23-6")
    c.part("L1", "Device:L", "10uH", "")
    c.net(vin_rail, "U1.3")               # VIN (pin 3)
    c.net("GND", "U1.1")                   # GND (pin 1)
    c.net("SW_X", "U1.2", "L1.1")          # SW (pin 2) -> inductor
    c.net(vout_rail, "L1.2")               # inductor -> output rail
    c.draws(vout_rail, iout, "synthetic buck load")
    return c


def test_tps54302_over_2A_fails_at_datasheet_rthja():
    """The whole point of the finding: a TPS54302 (no EP) carrying the real
    +3V3 load (~2.745 A) runs OVER its 125 C rec-max even at the conservative
    eff floor. At the DS RthJA the gate MUST fail it (no waiver)."""
    c = _tps54302_buck_sheet(2.745, "+3V3", "+5V")
    pt = powertree.analyze([_sheet("th", c)])
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    dev = next(d for d in r.devices if d.ref == "U1")
    # Pd = (1/0.85-1)*3.3*2.745 = 1.599 W ; Tj = 50 + 1.599*118.9 = 240 C
    assert dev.tj > 200.0, f"Tj should be ~240 C at DS RthJA, got {dev.tj:.1f}"
    assert dev.tj_max == 125.0
    assert not r.ok and dev.over, "must FAIL the 125 C rec-max guard"


def _lm61460_buck_sheet():
    c = Circuit("th", "th")
    c.part("U1", "LM61460AANRJRR:LM61460AANRJRR", "LM61460AANRJRR", "")
    c.part("L1", "Device:L", "10uH", "")
    c.net("+5V", "U1.8")                   # VIN1 (pin 8)
    c.net("GND", "U1.9", "U1.11", "U1.3")  # PGND1/PGND2/AGND heat path
    c.net("SW_X", "U1.10", "L1.1")         # SW (pin 10) -> inductor
    c.net("+3V3", "L1.2")
    c.draws("+3V3", 2.745, "synthetic buck load")
    return [_sheet("th", c)]


def test_lm61460_ep_buck_passes_same_load():
    """The swap target: the LM61460 (PGND/SW pads -> emitted GND pours + via
    field, pour-credit 35 C/W) carries the SAME +3V3 load comfortably under
    its 150 C rec-max guard — proving the reselection actually fixes the
    finding. The credit is granted only because the (synthetic) board copper
    VERIFIES: In1 plane + 8 vias + F/B pours at the instance."""
    sheets = _lm61460_buck_sheet()
    pt = powertree.analyze(sheets)
    copper = _synthetic_copper("LM61460AANRJRR")
    r = thermal.analyze(sheets, pt_res=pt, copper=copper, copper_src="synth")
    dev = next(d for d in r.devices if d.ref == "U1")
    # Pd = (1/0.85-1)*3.3*2.745 = 1.599 W ; Tj = 50 + 1.599*35 = 106 C < 140
    assert dev.poured, "LM61460 must take the verified pour-aware RthJA credit"
    assert dev.tj < 110.0, f"Tj should be ~106 C at the pour RthJA, got {dev.tj:.1f}"
    assert r.ok and not dev.over, "the EP buck must PASS with real margin"


def test_lm61460_old_basis_fails_without_emitted_copper():
    """RED-ON-FICTION lock (LAW 0 / GAP1): the OLD pour-credit basis — trust
    the prose, no emitted copper — must FAIL. Same buck, same load, NO board
    evidence: Tj computes at the bare 58.7 C/W (143.9 C > the 140 C guard)
    and the error says WHY the credit was withheld."""
    sheets = _lm61460_buck_sheet()
    pt = powertree.analyze(sheets)
    r = thermal.analyze(sheets, pt_res=pt)        # copper=None
    dev = next(d for d in r.devices if d.ref == "U1")
    assert not dev.poured and dev.rth_ja == 58.7
    assert dev.tj > 140.0, f"bare-RthJA Tj should be ~144 C, got {dev.tj:.1f}"
    assert not r.ok and dev.over
    assert any("POUR CREDIT WITHHELD" in e for e in r.errors), r.errors


def test_lm61460_partial_copper_is_not_enough():
    """A short via field (5 < the 6 floor), a missing local pour, or a
    missing In1 plane keeps the credit WITHHELD — the evidence bar is the
    emitter's actual output, not 'some copper somewhere' (LAW 4)."""
    sheets = _lm61460_buck_sheet()
    pt = powertree.analyze(sheets)
    for degraded in (
            _synthetic_copper("LM61460AANRJRR", n_vias=5),
            _synthetic_copper("LM61460AANRJRR", pour_layers=("F.Cu",)),
            _synthetic_copper("LM61460AANRJRR", plane=False)):
        r = thermal.analyze(sheets, pt_res=pt, copper=degraded)
        dev = next(d for d in r.devices if d.ref == "U1")
        assert not dev.poured and not r.ok, \
            "degraded copper must withhold the credit"


def _dyd_ldo_sheet():
    """The VADJ LDO shape: TLV75725 DYD (footprint carries 'DYD'), 0.4 A of
    +3V3 -> +2V5 (Pd = 0.32 W)."""
    c = Circuit("th", "th")
    c.part("U1", "TLV75725PDYDR:TLV75725PDYDR", "TLV75725PDYDR",
           "TLV75725PDYDR:TLV75725PDYDR")
    c.net("+3V3", "U1.1")
    c.net("+2V5_VADJ", "U1.5")
    c.net("GND", "U1.2")
    c.draws("+2V5_VADJ", 0.4, "synthetic VADJ load")
    return [_sheet("th", c)]


def test_dyd_ldo_credit_gated_on_copper():
    """The DYD 92.5 C/W is a JESD51-5 (pad + vias + buried plane) figure —
    WITH the emitted copper the LDO passes (~79.6 C); WITHOUT it the gate
    falls back to the DBV bare 231 C/W and correctly FAILS (~123.9 C > the
    115 C guard)."""
    sheets = _dyd_ldo_sheet()
    pt = powertree.analyze(sheets)
    good = _synthetic_copper("TLV75725PDYDR", n_vias=2,
                             pour_layers=("F.Cu",))
    r = thermal.analyze(sheets, pt_res=pt, copper=good, copper_src="synth")
    dev = next(d for d in r.devices if d.ref == "U1")
    assert dev.poured and dev.rth_ja == 92.5 and r.ok, \
        f"DYD with copper should pass at 92.5 C/W: Tj {dev.tj:.1f}, {r.errors}"
    r2 = thermal.analyze(sheets, pt_res=pt)       # no copper
    dev2 = next(d for d in r2.devices if d.ref == "U1")
    assert dev2.rth_ja == 231.0 and dev2.over and not r2.ok, \
        f"DYD without copper must fail at the DBV fallback: Tj {dev2.tj:.1f}"


def _bottom_copper(value: str, pour_layers, x: float = 100.0, y: float = 100.0,
                   n_vias: int = 2) -> BoardCopper:
    """``_synthetic_copper`` with the instance emitted on B.Cu — the only
    difference that matters to the pour check."""
    bc = _synthetic_copper(value, x=x, y=y, n_vias=n_vias,
                           pour_layers=pour_layers)
    bc.footprints[:] = [FpInfo("U1", value, x, y, "B.Cu", ())]
    return bc


def test_pour_credit_follows_the_part_to_bcu():
    """A part's local pour belongs on the part's OWN outer layer (JESD51-5),
    which is what the EMITTER lays for a bottom instance. The gate must ask
    for that copper, not for the library-frame literal: an asymmetric spec
    (TLV75725, F.Cu only) placed on B.Cu keeps its credit, and a bottom part
    whose pour was (wrongly) laid on the far face loses it."""
    assert thermal.pour_layers_for(
        thermal.POUR_EVIDENCE["TLV75725_DYD"], "F.Cu") == ("F.Cu",)
    assert thermal.pour_layers_for(
        thermal.POUR_EVIDENCE["TLV75725_DYD"], "B.Cu") == ("B.Cu",)
    sheets = _dyd_ldo_sheet()
    pt = powertree.analyze(sheets)
    ok = thermal.analyze(sheets, pt_res=pt, copper_src="synth",
                         copper=_bottom_copper("TLV75725PDYDR", ("B.Cu",)))
    dev = next(d for d in ok.devices if d.ref == "U1")
    assert dev.poured and dev.rth_ja == 92.5 and ok.ok, \
        f"B.Cu DYD with its own-side pour must keep the credit: {ok.errors}"
    bad = thermal.analyze(sheets, pt_res=pt, copper_src="synth",
                          copper=_bottom_copper("TLV75725PDYDR", ("F.Cu",)))
    dev2 = next(d for d in bad.devices if d.ref == "U1")
    assert dev2.rth_ja == 231.0 and dev2.over and not bad.ok, \
        "a bottom part poured only on the FAR face must lose the credit"


def test_emitter_and_gate_share_one_layer_swap():
    """The emitter's mirrored-spec layer swap IS the gate's table — one
    definition, so the copper laid and the copper demanded cannot drift."""
    from schgen.generate.pcb import embed
    assert embed._side_thermal_spec(
        {"pour_layers": ("F.Cu",)}, "bottom")["pour_layers"] == ("B.Cu",)
    assert embed._side_thermal_spec(
        {"pour_layers": ("F.Cu",)}, "top")["pour_layers"] == ("F.Cu",)
    spec = {"pour": (-3.0, -4.75, 4.4, 4.75), "via_sites": [(1.55, -2.5)],
            "pour_layers": ("F.Cu", "B.Cu")}
    mir = embed._mirror_thermal_spec(spec)
    assert mir["pour"] == (-3.0, -4.75, 4.4, 4.75)
    assert mir["via_sites"] == [(1.55, 2.5)]
    assert mir["pour_layers"] == ("F.Cu", "B.Cu"), \
        "the DOCUMENT mirror must not touch layers — the FACE decides those"
