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
    res_t, rot_t, _resolvable, _c = _solve(monkeypatch, "camera", True)
    res_f, rot_f, _resolvable2, _c2 = _solve(monkeypatch, "camera", False)
    assert res_t is not None
    assert res_t == res_f
    assert rot_t == rot_f


def test_usb_pd_trace_differential_and_identity(monkeypatch):
    res_t, rot_t, _resolvable, _c = _solve(monkeypatch, "usb_pd", True)
    res_f, rot_f, _resolvable2, _c2 = _solve(monkeypatch, "usb_pd", False)
    assert res_t is not None
    assert res_t == res_f
    assert rot_t == rot_f


def test_union_lower_bound_never_exceeds_exact_gap():
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
