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
    assert abs(thermal.dissipation("ldo", 5.0, 1.8, 0.3, spec) - 0.96) < 1e-9
    assert abs(thermal.dissipation("buck", 20.0, 5.0, 1.0, spec)
               - (1 / 0.85 - 1) * 5.0 * 1.0) < 1e-9
    assert abs(thermal.dissipation("efuse", 5.0, 5.0, 2.0, spec)
               - 4.0 * 0.1) < 1e-9
    assert thermal.dissipation("mystery", 5.0, 1.8, 1.0, spec) == 0.0


def test_current_board_passes_thermal():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.verify import copper_debt
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    copper = copper_debt.scan_board(REPO / "carrier" / "Zynq_Carrier.kicad_pcb")
    r = thermal.analyze(sheets, copper=copper, copper_src="Zynq_Carrier")
    assert r.ok, f"unexpected over-Tj devices: {r.errors}"
    assert not r.findings, f"unspeced devices: {r.findings}"
    assert len(r.devices) > 10
    bucks = [d for d in r.devices if d.value.startswith("LM61460")]
    assert len(bucks) == 3 and all(d.poured for d in bucks), \
        [f"{d.sheet}:{d.ref} granted={d.pour_granted}" for d in bucks]


def test_current_board_fails_without_emitted_copper():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = thermal.analyze(sheets)
    assert not r.ok, "no-copper analysis must FAIL (the fiction the old " \
                     "pour credit hid)"
    u1 = next(d for d in r.devices
              if d.sheet == "power" and d.value.startswith("LM61460"))
    assert not u1.poured and u1.rth_ja == 58.7
    assert u1.tj > 185.0, f"backed-out Tj should be ~192 C, got {u1.tj:.1f}"
    assert any("POUR CREDIT WITHHELD" in e for e in r.errors), r.errors[:2]


def _hot_ldo_sheet():
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
    spec = thermal.THERMAL_SPECS["TPS54302"]
    assert spec.rth_ja == 118.9, "must be the DS JESD51-7 RthJA, not 70.6"
    assert spec.tj_max == 125.0, "must be the rec-op Tj-max, not the 150 abs-max"
    assert spec.rth_ja_pour is None, "no-EP SOT-23 has no pad to pour"
    assert spec.rth_eff == 118.9, "no pour credit -> Tj judged at bare RthJA"


def _tps54302_buck_sheet(iout, vout_rail="+3V3", vin_rail="+5V"):
    c = Circuit("th", "th")
    c.part("U1", "Regulator_Switching:TPS54302", "TPS54302DDCR",
           "Package_TO_SOT_SMD:TSOT-23-6")
    c.part("L1", "Device:L", "10uH", "")
    c.net(vin_rail, "U1.3")
    c.net("GND", "U1.1")
    c.net("SW_X", "U1.2", "L1.1")
    c.net(vout_rail, "L1.2")
    c.draws(vout_rail, iout, "synthetic buck load")
    return c


def test_tps54302_over_2A_fails_at_datasheet_rthja():
    c = _tps54302_buck_sheet(2.745, "+3V3", "+5V")
    pt = powertree.analyze([_sheet("th", c)])
    r = thermal.analyze([_sheet("th", c)], pt_res=pt)
    dev = next(d for d in r.devices if d.ref == "U1")
    assert dev.tj > 200.0, f"Tj should be ~240 C at DS RthJA, got {dev.tj:.1f}"
    assert dev.tj_max == 125.0
    assert not r.ok and dev.over, "must FAIL the 125 C rec-max guard"


def _lm61460_buck_sheet():
    c = Circuit("th", "th")
    c.part("U1", "LM61460AANRJRR:LM61460AANRJRR", "LM61460AANRJRR", "")
    c.part("L1", "Device:L", "10uH", "")
    c.net("+5V", "U1.8")
    c.net("GND", "U1.9", "U1.11", "U1.3")
    c.net("SW_X", "U1.10", "L1.1")
    c.net("+3V3", "L1.2")
    c.draws("+3V3", 2.745, "synthetic buck load")
    return [_sheet("th", c)]


def test_lm61460_ep_buck_passes_same_load():
    sheets = _lm61460_buck_sheet()
    pt = powertree.analyze(sheets)
    copper = _synthetic_copper("LM61460AANRJRR")
    r = thermal.analyze(sheets, pt_res=pt, copper=copper, copper_src="synth")
    dev = next(d for d in r.devices if d.ref == "U1")
    assert dev.poured, "LM61460 must take the verified pour-aware RthJA credit"
    assert dev.tj < 110.0, f"Tj should be ~106 C at the pour RthJA, got {dev.tj:.1f}"
    assert r.ok and not dev.over, "the EP buck must PASS with real margin"


def test_lm61460_old_basis_fails_without_emitted_copper():
    sheets = _lm61460_buck_sheet()
    pt = powertree.analyze(sheets)
    r = thermal.analyze(sheets, pt_res=pt)
    dev = next(d for d in r.devices if d.ref == "U1")
    assert not dev.poured and dev.rth_ja == 58.7
    assert dev.tj > 140.0, f"bare-RthJA Tj should be ~144 C, got {dev.tj:.1f}"
    assert not r.ok and dev.over
    assert any("POUR CREDIT WITHHELD" in e for e in r.errors), r.errors


def test_lm61460_partial_copper_is_not_enough():
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
    c = Circuit("th", "th")
    c.part("U1", "TLV75725PDYDR:TLV75725PDYDR", "TLV75725PDYDR",
           "TLV75725PDYDR:TLV75725PDYDR")
    c.net("+3V3", "U1.1")
    c.net("+2V5_VADJ", "U1.5")
    c.net("GND", "U1.2")
    c.draws("+2V5_VADJ", 0.4, "synthetic VADJ load")
    return [_sheet("th", c)]


def test_dyd_ldo_credit_gated_on_copper():
    sheets = _dyd_ldo_sheet()
    pt = powertree.analyze(sheets)
    good = _synthetic_copper("TLV75725PDYDR", n_vias=2,
                             pour_layers=("F.Cu",))
    r = thermal.analyze(sheets, pt_res=pt, copper=good, copper_src="synth")
    dev = next(d for d in r.devices if d.ref == "U1")
    assert dev.poured and dev.rth_ja == 92.5 and r.ok, \
        f"DYD with copper should pass at 92.5 C/W: Tj {dev.tj:.1f}, {r.errors}"
    r2 = thermal.analyze(sheets, pt_res=pt)
    dev2 = next(d for d in r2.devices if d.ref == "U1")
    assert dev2.rth_ja == 231.0 and dev2.over and not r2.ok, \
        f"DYD without copper must fail at the DBV fallback: Tj {dev2.tj:.1f}"


def _bottom_copper(value: str, pour_layers, x: float = 100.0, y: float = 100.0,
                   n_vias: int = 2) -> BoardCopper:
    bc = _synthetic_copper(value, x=x, y=y, n_vias=n_vias,
                           pour_layers=pour_layers)
    bc.footprints[:] = [FpInfo("U1", value, x, y, "B.Cu", ())]
    return bc


def test_pour_credit_follows_the_part_to_bcu():
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
