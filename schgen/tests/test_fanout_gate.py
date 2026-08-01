from __future__ import annotations

from schgen.generate import pcb
from schgen.generate.pcb import (
    ORIGIN_X,
    ORIGIN_Y,
    FootprintInst,
    PcbModel,
)
from schgen.verify import fanout_gate as fg

_R_MOD = pcb.resolve_mod("Resistor_SMD:R_0603_1608Metric")
assert _R_MOD is not None, "R_0603 footprint missing"


def _part(ref, x, y, npins, *, sheet="s", side="top", mod=None, value="x"):
    m = mod or _R_MOD
    pad_nets = {str(i): (i, f"N{i}") for i in range(1, npins + 1)}
    return FootprintInst(ref=ref, value=value, footprint="lib:x", x=x, y=y,
                         rotation=0.0, pad_nets=pad_nets, mod_path=m,
                         sheet=sheet, side=side)


def _model(insts):
    return PcbModel(board_w=100.0, board_h=80.0, insts=insts,
                    net_numbers={"": 0}, netclass_of={}, classes={},
                    placed=len(insts), deferred=[])


def test_need_scales_with_pin_count():
    n2, _ = fg.intelligent_need(2)
    n8, _ = fg.intelligent_need(8)
    n20, _ = fg.intelligent_need(20)
    n48, _ = fg.intelligent_need(48)
    n100, _ = fg.intelligent_need(100)
    assert n2 == 0.20 and n8 == 1.50 and n20 == 2.00 and n48 == 2.00 and n100 == 2.00
    assert n2 < n8 < n20 <= n48 <= n100


def test_spacious_ic_passes():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    far = _part("R9", ORIGIN_X + 40, ORIGIN_Y + 20, npins=2, sheet="b")
    res = fg.check(_model([ic, far]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, res.summary()
    assert res.n_starved == 0 and res.ok
    assert rec.clearance > rec.need


def test_starved_ic_fails():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    near = _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b")
    res = fg.check(_model([ic, near]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert rec.starved, res.summary()
    assert rec.clearance < rec.need
    assert res.n_starved >= 1
    assert not res.ok, "baseline 0 => a starved IC is a ratchet regression => FAIL"
    assert any("U1" in g for g in res.regressions)


def test_own_cluster_passive_excluded():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="pwr")
    cap = _part("C1", ORIGIN_X + 21.7, ORIGIN_Y + 20, npins=2, sheet="pwr",
                value="100nF")
    cap.ref = "C1"
    res = fg.check(_model([ic, cap]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, ("own-cluster cap must not crowd", res.summary())
    assert rec.nearest_ref == "(none)"
    assert res.ok


def test_foreign_sheet_passive_does_crowd():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="pwr")
    cap = _part("C9", ORIGIN_X + 21.7, ORIGIN_Y + 20, npins=2, sheet="OTHER",
                value="100nF")
    res = fg.check(_model([ic, cap]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert rec.starved, ("foreign-sheet cap must crowd", res.summary())
    assert rec.nearest_ref == "C9"


def test_opposite_side_part_excluded():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a", side="top")
    under = _part("U2", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="b",
                  side="bottom")
    res = fg.check(_model([ic, under]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, ("opposite-side part must not crowd", res.summary())
    assert rec.nearest_ref == "(none)"
    under.side = "top"
    res2 = fg.check(_model([ic, under]), baseline=0)
    rec2 = next(r for r in res2.records if r.ref == "U1")
    assert rec2.starved and rec2.clearance == 0.0, res2.summary()


def test_df40_plug_excluded_as_subject_and_neighbour():
    plug = _part("J24001", ORIGIN_X + 20, ORIGIN_Y + 20, npins=104, sheet="som_j1")
    ic = _part("U1", ORIGIN_X + 22, ORIGIN_Y + 20, npins=8, sheet="a")
    res = fg.check(_model([plug, ic]), baseline=0)
    assert not any(r.ref == "J24001" for r in res.records), "DF40 must not be a subject"
    rec = next(r for r in res.records if r.ref == "U1")
    assert rec.nearest_ref == "(none)", ("DF40 must not crowd", res.summary())
    assert not rec.starved


def test_two_pin_passive_not_a_subject():
    r1 = _part("R1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=2, sheet="a")
    ic = _part("U1", ORIGIN_X + 40, ORIGIN_Y + 20, npins=8, sheet="a")
    res = fg.check(_model([r1, ic]), baseline=0)
    subjects = {r.ref for r in res.records}
    assert "R1" not in subjects and "U1" in subjects


def test_ratchet_passes_at_or_below_baseline_fails_above():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    near = _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b")
    m = _model([ic, near])
    assert fg.check(m, baseline=2).n_starved == 2
    assert fg.check(m, baseline=2).ok
    assert not fg.check(m, baseline=1).ok


def test_first_run_self_pins_baseline_and_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(fg, "_BASELINE_PATH", tmp_path / "absent_fanout_baseline.json")
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    near = _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b")
    res = fg.check(_model([ic, near]), baseline=None)
    assert res.baseline is not None and res.baseline >= res.n_starved
    assert res.ok


def test_write_baseline_only_ratchets_down(tmp_path):
    p = tmp_path / "fanout_baseline.json"
    fg.write_baseline(18, path=p)
    fg.write_baseline(12, path=p)
    import json
    assert json.loads(p.read_text())["starved_baseline"] == 12
    fg.write_baseline(30, path=p)
    assert json.loads(p.read_text())["starved_baseline"] == 12


def test_records_sorted_worst_first_deterministic():
    insts = [
        _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=24, sheet="a"),
        _part("U2", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=8, sheet="b"),
        _part("U3", ORIGIN_X + 60, ORIGIN_Y + 20, npins=8, sheet="c"),
    ]
    r1 = fg.check(_model(insts), baseline=0)
    r2 = fg.check(_model(insts), baseline=0)
    assert [r.ref for r in r1.records] == [r.ref for r in r2.records]
    slacks = [r.slack for r in r1.records]
    assert slacks == sorted(slacks), "worst slack must come first"


def test_testpoint_never_crowds():
    ic = _part("U1", ORIGIN_X + 20, ORIGIN_Y + 20, npins=8, sheet="a")
    tp = _part("TP1", ORIGIN_X + 21.9, ORIGIN_Y + 20, npins=1, sheet="b")
    far = _part("R9", ORIGIN_X + 40, ORIGIN_Y + 20, npins=2, sheet="b")
    res = fg.check(_model([ic, tp, far]), baseline=0)
    rec = next(r for r in res.records if r.ref == "U1")
    assert not rec.starved, res.summary()
    assert rec.nearest_ref != "TP1"
    assert res.ok
