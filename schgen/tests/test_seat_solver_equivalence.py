"""Trace-differential harness for the stage-template seat solver fast kernels
(schgen/generate/pcb/stage_templates): the verbatim reference pose scan
(``_gc_scan_ref``) and the fast scan (``_gc_scan_fast``) must return IDENTICAL
pose lists on real contract solves; the ``_seat_all`` expanded-box DFS must
agree with the ``_boxes_overlap`` kernel on every decision; the union-box lower
bound can never exceed the exact pad-edge gap; and the permanent skeleton-clear
tripwire raises loudly when its invariant is violated. The same traced kernels
are selectable on a live build via SCHGEN_SEAT_TRACE=1."""

from __future__ import annotations

import pytest

from schgen.generate.pcb import stage_templates as T
from schgen.tests.test_stage_templates import _run_zone, _subsystem_inputs


def _fresh_caches(monkeypatch):
    monkeypatch.setattr(T, "_BUCK_CACHE", {})
    monkeypatch.setattr(T, "_PROX_CACHE", {})
    monkeypatch.setattr(T, "_MULTI_CACHE", {})


def _solve(monkeypatch, sheet, trace):
    _fresh_caches(monkeypatch)
    monkeypatch.setattr(T, "_SEAT_TRACE", trace)
    return _run_zone(sheet)


def test_camera_trace_differential_and_identity(monkeypatch):
    """Camera (the multi-anchor archetype) solved cold with SCHGEN_SEAT_TRACE
    semantics: every _gcandidates call runs BOTH scan kernels (divergence
    raises inside), and the traced result equals the untraced fast result
    exactly — trace mode observes, never steers."""
    res_t, rot_t, _resolvable, _c = _solve(monkeypatch, "camera", True)
    res_f, rot_f, _resolvable2, _c2 = _solve(monkeypatch, "camera", False)
    assert res_t is not None
    assert res_t == res_f
    assert rot_t == rot_f


def test_usb_pd_trace_differential_and_identity(monkeypatch):
    """usb_pd (frozen pilot star) drives the single-anchor ``_seat_all`` DFS:
    under trace every backtracking decision is double-checked against the
    original ``any(_boxes_overlap(...))`` kernel, and the result is identical
    to the untraced solve."""
    res_t, rot_t, _resolvable, _c = _solve(monkeypatch, "usb_pd", True)
    res_f, rot_f, _resolvable2, _c2 = _solve(monkeypatch, "usb_pd", False)
    assert res_t is not None
    assert res_t == res_f
    assert rot_t == rot_f


def test_union_lower_bound_never_exceeds_exact_gap():
    """The fast scan's rejection logic rests on lb <= exact best (union boxes
    only ever move pad pairs closer). Sweep a real anchor/member pad geometry
    (usb_pd U1 vs its C1 bypass) over a coarse offset grid and verify the bound
    against the verbatim exact kernel at every pose."""
    from schgen.verify import placement_contract_gate as g

    _refs, _side, _bbox, resolvable, _cr, _od = _subsystem_inputs("usb_pd")
    mods = sorted(resolvable.items())
    anchor = max(mods, key=lambda kv: len(g._pad_boxes(kv[1], 0.0)))[1]
    member = min(mods, key=lambda kv: len(g._pad_boxes(kv[1], 0.0)))[1]
    tboxes = list(g._pad_boxes(anchor, 0.0).values())
    checked = 0
    for rot in (0.0, 90.0):
        rel = list(g._pad_boxes(member, rot).values())
        u = T._gc_union(tboxes)
        ru = T._gc_union(rel)
        for gx in range(-6, 7):
            for gy in range(-6, 7):
                cx, cy = gx * 1.7, gy * 1.3
                dx = u[0] - (cx + ru[2])
                qx = (cx + ru[0]) - u[2]
                if qx > dx:
                    dx = qx
                if dx < 0.0:
                    dx = 0.0
                dy = u[1] - (cy + ru[3])
                qy = (cy + ru[1]) - u[3]
                if qy > dy:
                    dy = qy
                if dy < 0.0:
                    dy = 0.0
                lb = T.math.hypot(dx, dy)
                best = min(
                    g._box_gap(tb, (cx + rb[0], cy + rb[1],
                                    cx + rb[2], cy + rb[3]))
                    for tb in tboxes for rb in rel)
                assert lb <= best, (
                    f"union lb {lb} > exact best {best} at rot {rot} "
                    f"pose ({cx}, {cy})")
                checked += 1
    assert checked == 2 * 13 * 13


def test_seat_dfs_skeleton_tripwire_raises(monkeypatch):
    """The permanent _seat_all tripwire: a candidate that is NOT skeleton-clear
    (the invariant _candidates guarantees and the fast DFS relies on) raises
    loudly instead of seating a silently divergent layout."""
    _refs, _side, _bbox, resolvable, _cr, _od = _subsystem_inputs("usb_pd")
    mod = sorted(resolvable.values())[0]
    anchor = T._Part("U1", mod, 0.0, "top", 0.0, 0.0)
    bad = anchor.local_box()

    def fake_candidates(bref, mod_, ib, icb, tpins, bound, keep, kmin, pad,
                        skel_boxes, forbid_plus_x=True):
        return [(T._Part(bref, mod_, 0.0, "top", 0.0, 0.0), bad)]

    monkeypatch.setattr(T, "_candidates", fake_candidates)
    with pytest.raises(AssertionError, match="TRIPWIRE"):
        T._seat_all([("C1", None, 5.0, None, 0.0)], {"C1": mod},
                    anchor.pad_boxes(), bad, [anchor], 0.0)
