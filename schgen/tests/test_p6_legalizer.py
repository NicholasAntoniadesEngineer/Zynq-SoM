from __future__ import annotations

import pytest

from schgen.generate import floorplan_compose as fc


def _metrics_one_part(w: float, h: float) -> fc.LocalMetrics:
    return fc.LocalMetrics(offsets=(("U1", w / 2, h / 2),),
                           pad_union=(("U1", 0.0, 0.0, w, h),),
                           zone_wh=(w, h))


def _index(terms):
    hard = tuple(t for t in terms if t.enforced)
    soft = tuple(t for t in terms if not t.enforced)
    return fc.TermIndex(hard=hard, soft=soft)


def _near(subject, target, bound, enforced=True):
    return fc.Term(kind="near_max", sheet=subject, subject=subject,
                   target_raw=target, bound=bound, basis="test",
                   enforced=enforced)


_SOM = (60.0, 60.0, 111.0, 103.0)


def test_L0_no_hard_terms_is_untouched():
    v = fc.LegalizeVar("a", 10, 10, (5.0, 5.0), 5.0, 5.0)
    ok = fc.legalize_compact(170, 151, _SOM, [], [v],
                             _index([_near("a", "b", 10.0, enforced=False)]),
                             {"a": _metrics_one_part(10, 10)}, {}, {}, 0.3)
    assert ok and (v.x, v.y) == (5.0, 5.0)


def test_seed_restore_green_candidate_is_byte_identical():
    mets = {"a": _metrics_one_part(10, 10), "b": _metrics_one_part(8, 8)}
    a = fc.LegalizeVar("a", 10, 10, (20.0, 20.0), 20.0, 20.0)
    idx = _index([_near("a", "b", 12.0)])
    fixed_poses = {"b": (34.0, 20.0)}
    ok = fc.legalize_compact(
        170, 151, _SOM, [("b", 34.0, 20.0, 42.0, 28.0)], [a], idx, mets,
        fixed_poses, {}, 0.3)
    assert ok
    assert (a.x, a.y) == (20.0, 20.0), "green seed must not drift"


def test_near_max_violating_seed_is_legalized_red_to_green():
    mets = {"a": _metrics_one_part(10, 10), "b": _metrics_one_part(8, 8)}
    a = fc.LegalizeVar("a", 10, 10, (20.0, 20.0), 20.0, 20.0)
    idx = _index([_near("a", "b", 12.0)])
    fixed_poses = {"b": (54.0, 20.0)}
    seed_evals = fc.evaluate_terms(
        170, 151, _SOM, {"a": (20.0, 20.0), **fixed_poses}, mets, idx)
    assert any(e.term.kind == "near_max" and not e.ok for e in seed_evals), \
        "fixture defect: seed is not red"
    log: list[str] = []
    ok = fc.legalize_compact(
        170, 151, _SOM, [("b", 54.0, 20.0, 62.0, 28.0)], [a], idx, mets,
        fixed_poses, {}, 0.3, log=log)
    assert ok, log
    post = fc.evaluate_terms(
        170, 151, _SOM, {"a": (round(a.x, 4), round(a.y, 4)), **fixed_poses},
        mets, idx)
    assert all(e.ok for e in post if e.term.enforced), (log, post)
    assert a.x > 20.0, "subject must have moved toward the window"


def test_contradictory_windows_named_cycle_rejects():
    mets = {"a": _metrics_one_part(10, 10),
            "b": _metrics_one_part(8, 8), "c": _metrics_one_part(8, 8)}
    a = fc.LegalizeVar("a", 10, 10, (80.0, 20.0), 80.0, 20.0)
    idx = _index([_near("a", "b", 6.0), _near("a", "c", 6.0)])
    fixed = [("b", 1.0, 20.0, 9.0, 28.0), ("c", 160.0, 20.0, 168.0, 28.0)]
    fixed_poses = {"b": (1.0, 20.0), "c": (160.0, 20.0)}
    log: list[str] = []
    ok = fc.legalize_compact(170, 151, _SOM, fixed, [a], idx, mets,
                             fixed_poses, {}, 0.3, log=log)
    assert not ok
    assert any("INFEASIBLE" in x or "REJECT" in x for x in log), log


def test_d13_channel_gap_and_terminus_precedence():
    demand = {frozenset(("a", "b")): 10}
    gap, why = fc.channel_gap_mm("a", "b", demand, set(), 0.3)
    assert gap == pytest.approx(fc.CHANNEL_FLOOR_MM
                                + 10 * fc.CHANNEL_PER_NET_MM)
    assert "D13" in why
    gap2, why2 = fc.channel_gap_mm("a", "b", demand,
                                   {frozenset(("a", "b"))}, 0.3)
    assert gap2 == 0.3 and "terminus" in why2
    gap3, _ = fc.channel_gap_mm("a", "c", demand, set(), 0.3)
    assert gap3 == 0.3


def test_channel_separation_enforced_between_movables():
    mets = {n: _metrics_one_part(10, 10) for n in ("a", "b")}
    mets["t"] = _metrics_one_part(6, 6)
    a = fc.LegalizeVar("a", 10, 10, (20.0, 20.0), 20.0, 20.0)
    b = fc.LegalizeVar("b", 10, 10, (30.5, 20.0), 30.5, 20.0)
    idx = _index([_near("a", "t", 40.0)])
    demand = {frozenset(("a", "b")): 10}
    fixed_poses = {"t": (44.0, 20.0)}
    log: list[str] = []
    ok = fc.legalize_compact(
        170, 151, _SOM, [("t", 44.0, 20.0, 50.0, 26.0)], [a, b], idx, mets,
        fixed_poses, demand, 0.3, log=log)
    assert ok, log
    gap = b.x - (a.x + 10.0)
    corridor = fc.channel_demand_mm(10)
    assert gap >= corridor - 1e-6, (gap, corridor, log)


def test_compaction_shortens_wired_hop_and_is_guarded():
    mets = {"a": _metrics_one_part(10, 10), "b": _metrics_one_part(8, 8)}
    a = fc.LegalizeVar("a", 10, 10, (20.0, 20.0), 20.0, 20.0)
    hop = fc.Term(kind="flow_hop", sheet="a", subject="a", target_raw="b",
                  bound=None, basis="test", enforced=True)
    idx = _index([hop])
    fixed_poses = {"b": (100.0, 20.0)}
    seed_evals = fc.evaluate_terms(
        170, 151, _SOM, {"a": (20.0, 20.0), **fixed_poses}, mets, idx)
    d0 = [e for e in seed_evals if e.term.kind == "flow_hop"][0].measured
    log: list[str] = []
    ok = fc.legalize_compact(
        170, 151, _SOM, [("b", 100.0, 20.0, 108.0, 28.0)], [a], idx, mets,
        fixed_poses, {}, 0.3, compact=True, log=log)
    assert ok, log
    post = fc.evaluate_terms(
        170, 151, _SOM, {"a": (a.x, a.y), **fixed_poses}, mets, idx)
    d1 = [e for e in post if e.term.kind == "flow_hop"][0].measured
    assert d1 < d0 - 1.0, (d0, d1, log)
    assert all(e.ok for e in post if e.term.enforced), log


def test_solver_is_deterministic():
    def run():
        mets = {"a": _metrics_one_part(10, 10), "b": _metrics_one_part(8, 8)}
        a = fc.LegalizeVar("a", 10, 10, (20.0, 20.0), 20.0, 20.0)
        idx = _index([_near("a", "b", 12.0)])
        fixed_poses = {"b": (54.0, 20.0)}
        fc.legalize_compact(170, 151, _SOM,
                            [("b", 54.0, 20.0, 62.0, 28.0)], [a], idx, mets,
                            fixed_poses, {}, 0.3)
        return (a.x, a.y)
    assert run() == run()


def test_escape_corridors_load_and_act_as_keepouts(tmp_path):
    import json

    from schgen.generate.floorplan_compose import (
        escape_corridors,
    )
    real = escape_corridors()
    assert len(real) == 6 and all(n.startswith("escape:") for n, *_ in real)
    side = tmp_path / "escape_block.json"
    side.write_text(json.dumps({"t1_constraints": {"corridors": {
        "JX:N": {"purpose": "t", "rect": [60.0, 40.0, 90.0, 42.0]}}}}))
    corr = escape_corridors(side)
    assert len(corr) == 1
    name, x0, y0, x1, y1 = corr[0]
    mets = {"a": _metrics_one_part(10, 10), "t": _metrics_one_part(6, 6)}
    a = fc.LegalizeVar("a", 10, 10, (36.0, 12.0), 36.0, 12.0)
    idx = _index([_near("a", "t", 40.0)])
    fixed_poses = {"t": (50.0, 12.0)}
    fixed = [("t", 50.0, 12.0, 56.0, 18.0), (name, x0, y0, x1, y1)]
    a.y = 14.0
    a.seed = (36.0, 14.0)
    log: list[str] = []
    ok = fc.legalize_compact(170, 151, _SOM, fixed, [a], idx, mets,
                             fixed_poses, {}, 0.3, log=log)
    assert ok, log
    ay0, ay1 = a.y, a.y + 10
    assert ay1 <= y0 + 1e-6 or ay0 >= y1 - 1e-6, (
        f"movable still intrudes the corridor: {ay0}..{ay1} vs {y0}..{y1}")


def test_cross_axis_repair_flip_never_emits_overlap():
    mets = {"a": _metrics_one_part(10, 10), "t": _metrics_one_part(10, 8)}
    a = fc.LegalizeVar("a", 10, 10, (44.0, 60.0), 44.0, 60.0)
    idx = _index([_near("a", "t", 30.0)])
    obstacle = (40.0, 30.0, 60.0, 50.0)
    fixed = [("t", 48.0, 2.0, 58.0, 10.0), ("o", *obstacle)]
    fixed_poses = {"t": (48.0, 2.0)}
    log: list[str] = []
    ok = fc.legalize_compact(100.0, 100.0, _SOM, fixed, [a], idx, mets,
                             fixed_poses, {}, 0.3, log=log)
    if ok:
        ax0, ay0, ax1, ay1 = a.x, a.y, a.x + 10.0, a.y + 10.0
        for fn, x0, y0, x1, y1 in fixed:
            ox = min(ax1, x1) - max(ax0, x0)
            oy = min(ay1, y1) - max(ay0, y0)
            assert not (ox > 1e-6 and oy > 1e-6), (
                f"legalizer emitted a|{fn} overlap {ox:.2f}x{oy:.2f}", log)
        post = fc.evaluate_terms(
            100.0, 100.0, _SOM, {"a": (a.x, a.y), **fixed_poses}, mets, idx)
        assert all(e.ok for e in post if e.term.enforced), log
    else:
        assert any("REJECT" in x or "INFEASIBLE" in x for x in log), (
            "pack-fail must be NAMED in the log", log)
