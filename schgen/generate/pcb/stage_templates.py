from __future__ import annotations

import math
import os
from pathlib import Path

from schgen.core import fallbacks as _fb
from schgen.core import native as _nat
from schgen.core import quantize as _q
from schgen.core.project import spec as _project_spec
from schgen.verify import placement_contract_gate as _g
from schgen.verify.fanout_gate import (
    _is_cluster_passive,
    intelligent_need,
    is_testpoint_ref,
)

from .constants import CONN_MATING_FACE, EDGE_PAD_CLEAR, TEMPLATE_CLEAR, ZONE_PAD
from .footprint import _footprint_bbox
from .footprint import has_thru_pads as _has_thru_pads
from .mating_face import _rot_pad_bbox, connector_edge_rotation
from .placement import _shelf_pack
from .turn import turn_box

_IND_BODY_GAP = 1.0
_LDO_GAP = 0.6
_COUT_GAP = 1.0
_LEFTOVER_BAND_GAP = 2.0
_INTERSTAGE_GAP0 = 6.0
_NONSW_RELIEF = 0.7
_NONSW_STAGE_GAP = round(TEMPLATE_CLEAR + _NONSW_RELIEF, 4)
_ROW_WIDTH_BUDGET = 46.0
_INTERROW_BUCK_GAP = 8.0
_RELAX_STEP = 0.25


class _Part:
    __slots__ = ("bref", "mod", "rot", "side", "ox", "oy")

    def __init__(self, bref: str, mod: Path, rot: float, side: str,
                 ox: float, oy: float) -> None:
        self.bref = bref
        self.mod = mod
        self.rot = rot
        self.side = side
        self.ox = ox
        self.oy = oy

    def pad_boxes(self) -> dict[str, tuple[float, float, float, float]]:
        rel = _g._pad_boxes(self.mod, self.rot)
        return {n: (self.ox + b[0], self.oy + b[1], self.ox + b[2], self.oy + b[3])
                for n, b in rel.items()}

    def local_box(self) -> tuple[float, float, float, float]:
        rb = turn_box(_footprint_bbox(self.mod), self.rot)
        return (self.ox + rb[0], self.oy + rb[1], self.ox + rb[2], self.oy + rb[3])


def _pad_half(mod: Path) -> tuple[float, float]:
    pb = _g._pad_boxes(mod, 0.0)
    b = next(iter(pb.values()))
    return (b[2] - b[0]) / 2.0, (b[3] - b[1]) / 2.0


def _crtyd_half(mod: Path, rot: float) -> tuple[float, float]:
    rb = turn_box(_footprint_bbox(mod), rot)
    return (rb[2] - rb[0]) / 2.0, (rb[3] - rb[1]) / 2.0


def _pin_box_py(ic_boxes: dict[str, tuple], pins: list[str]
                ) -> tuple[float, float, float, float]:
    boxes = [ic_boxes[p] for p in pins if p in ic_boxes]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _pin_box(ic_boxes: dict[str, tuple], pins: list[str]
             ) -> tuple[float, float, float, float]:
    boxes = [ic_boxes[p] for p in pins if p in ic_boxes]
    if not _nat.loaded():
        raise RuntimeError("native pin_box required")
    got = _nat.module().boxes_union(boxes)
    if got is None:
        raise ValueError("pin box: no pads")
    hit = tuple(got)
    if _nat.trace():
        ref = _pin_box_py(ic_boxes, pins)
        if hit != ref:
            raise AssertionError(
                f"native pin_box DIVERGENCE: cpp={hit} python={ref}")
    return hit


def _boxes_overlap_py(a: tuple[float, float, float, float],
                      b: tuple[float, float, float, float], halo: float) -> bool:
    return (a[0] - halo < b[2] and a[2] + halo > b[0]
            and a[1] - halo < b[3] and a[3] + halo > b[1])


def _boxes_overlap(a: tuple[float, float, float, float],
                   b: tuple[float, float, float, float], halo: float) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native boxes_overlap required")
    got = _nat.module().boxes_overlap(a, b, halo)
    if _nat.trace():
        ref = _boxes_overlap_py(a, b, halo)
        if got is not ref:
            raise AssertionError(
                "native boxes_overlap DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


_BUCK_CACHE: dict[tuple, list[tuple[float, float, float]]] = {}


def _build_buck_stage(ic_bref: str, members: dict[str, str],
                      resolvable: dict[str, Path],
                      hf_caps: list[str], bulk_caps: list[str],
                      out_caps: list[str],
                      inductor: str, fb_members: list[str],
                      boot_cap: str, vcc_cap: str,
                      bias_r: str, bias_c: str, rt_r: str,
                      pins: dict[str, str]) -> list[_Part]:
    ic_mod = resolvable[ic_bref]
    slot_brefs = ([ic_bref, inductor, *hf_caps, *bulk_caps, *out_caps,
                   *fb_members, boot_cap, vcc_cap, bias_r, bias_c, rt_r])
    sig = (str(ic_mod), tuple(str(resolvable[b]) for b in slot_brefs),
           tuple(sorted(pins.items())))
    cached = _BUCK_CACHE.get(sig)
    if cached is not None:
        return [_Part(b, resolvable[b], rot, "top", ox, oy)
                for b, (rot, ox, oy) in zip(slot_brefs, cached, strict=True)]

    parts: list[_Part] = []
    solved = False
    for scale in range(0, 20):
        pad = scale * _RELAX_STEP
        parts = _lay_buck(ic_bref, ic_mod, resolvable, hf_caps, bulk_caps,
                          out_caps, inductor, fb_members, boot_cap, vcc_cap,
                          bias_r, bias_c, rt_r, pins, pad)
        if not _any_overlap(parts):
            solved = True
            break
    if not solved:
        raise ZoneInfeasible(
            f"buck stage {ic_bref}: 20-scale widen exhausted with parts "
            f"still overlapping — the datasheet stage recipe is infeasible "
            f"for these footprints (no silent overlap ship, no legacy pack)")
    by_bref = {p.bref: p for p in parts}
    _BUCK_CACHE[sig] = [(by_bref[b].rot, by_bref[b].ox, by_bref[b].oy)
                        for b in slot_brefs]
    return parts


def _beside_py(mod: Path, rot: float, side: str,
               target: tuple[float, float, float, float],
               direction: str, gap: float,
               along_center: float | None, hx: float, hy: float) -> _Part:
    tcx = (target[0] + target[2]) / 2.0
    tcy = (target[1] + target[3]) / 2.0
    if direction == "L":
        ox = target[0] - gap - hx
        oy = along_center if along_center is not None else tcy
    elif direction == "R":
        ox = target[2] + gap + hx
        oy = along_center if along_center is not None else tcy
    elif direction == "U":
        oy = target[1] - gap - hy
        ox = along_center if along_center is not None else tcx
    else:
        oy = target[3] + gap + hy
        ox = along_center if along_center is not None else tcx
    return _Part("", mod, rot, side, round(ox, 4), round(oy, 4))


def _beside(mod: Path, rot: float, side: str,
            target: tuple[float, float, float, float],
            direction: str, gap: float,
            along_center: float | None = None) -> _Part:
    hx, hy = _crtyd_half(mod, rot)
    if not _nat.loaded():
        raise RuntimeError("native beside required")
    ox, oy = _nat.module().beside_offset(
        hx, hy, target, direction, gap, along_center)
    if _nat.trace():
        ref = _beside_py(mod, rot, side, target, direction, gap,
                         along_center, hx, hy)
        if (ox, oy) != (ref.ox, ref.oy):
            raise AssertionError(
                "native beside_offset DIVERGENCE: "
                f"cpp={(ox, oy)} python={(ref.ox, ref.oy)}")
    return _Part("", mod, rot, side, ox, oy)


def _rebref(p: _Part, bref: str) -> _Part:
    return _Part(bref, p.mod, p.rot, p.side, p.ox, p.oy)


def _lay_buck(ic_bref: str, ic_mod: Path, resolvable: dict[str, Path],
              hf_caps: list[str], bulk_caps: list[str], out_caps: list[str],
              inductor: str, fb_members: list[str], boot_cap: str, vcc_cap: str,
              bias_r: str, bias_c: str, rt_r: str, pins: dict[str, str],
              pad: float) -> list[_Part]:
    ic = _Part(ic_bref, ic_mod, 0.0, "top", 0.0, 0.0)
    ib = ic.pad_boxes()
    icb = ic.local_box()
    parts: list[_Part] = [ic]

    m = 0.2
    clr = TEMPLATE_CLEAR + m + pad
    vin1, pgnd1 = pins["vin1"], pins["pgnd1"]
    vin2, pgnd2 = pins["vin2"], pins["pgnd2"]

    swb = ib[pins["sw"]]
    ind = _rebref(_beside(resolvable[inductor], 0.0, "top", icb, "R",
                          _IND_BODY_GAP + pad,
                          along_center=(swb[1] + swb[3]) / 2.0), inductor)
    parts.append(ind)
    ind_left = ind.local_box()[0]

    for oc in _cout_column(resolvable, out_caps, ind.pad_boxes()[pins["ind_out"]],
                           pad):
        parts.append(oc)

    hf1 = _hf_cap(resolvable[hf_caps[0]], ib, [vin1, pgnd1], "D", clr, ind_left,
                  hf_caps[0])
    hf2 = _hf_cap(resolvable[hf_caps[1]], ib, [vin2, pgnd2], "U", clr, ind_left,
                  hf_caps[1])
    parts += [hf1, hf2]

    bulk1 = bulk2 = None
    if len(bulk_caps) >= 1:
        bulk1 = _bulk_cap(resolvable[bulk_caps[0]], hf1, "D", clr, ind_left,
                          bulk_caps[0])
        parts.append(bulk1)
    if len(bulk_caps) >= 2:
        bulk2 = _bulk_cap(resolvable[bulk_caps[1]], hf2, "U", clr, ind_left,
                          bulk_caps[1])
        parts.append(bulk2)

    sw = pins["sw"]
    demands = [
        *[(m, [pins["fb"]], 3.0, [sw], 2.0) for m in fb_members],
        (vcc_cap, [pins["vcc"]], 2.0, None, 0.0),
        (boot_cap, [pins["rboot"], pins["cboot"]], 2.0, None, 0.0),
        (bias_c, [pins["bias"]], 3.0, None, 0.0),
        (rt_r, [pins["rt"]], 3.0, None, 0.0),
        (bias_r, [pins["bias"]], 20.0, None, 0.0),
    ]
    seated = _seat_all(demands, resolvable, ib, icb, parts, pad)
    parts += seated
    return parts


def _hf_cap(mod: Path, ib: dict[str, tuple], pair: list[str], direction: str,
            gap: float, ind_left: float, bref: str) -> _Part:
    p = _beside(mod, 0.0, "top", _pin_box(ib, pair), direction, gap)
    hx, _hy = _crtyd_half(mod, 0.0)
    if not _nat.loaded():
        raise RuntimeError("native hf_cap_pose required")
    ox, oy = _nat.module().hf_cap_pose(p.oy, ind_left, TEMPLATE_CLEAR, hx)
    if _nat.trace():
        ref = (round(ind_left - TEMPLATE_CLEAR - hx, 4), p.oy)
        if (ox, oy) != ref:
            raise AssertionError(
                "native hf_cap_pose DIVERGENCE: "
                f"cpp={(ox, oy)} python={ref}")
    return _Part(bref, mod, 0.0, "top", ox, oy)


def _bulk_cap_py(mod: Path, hf: _Part, direction: str, gap: float,
                 ind_left: float, bref: str) -> _Part:
    hfb = hf.local_box()
    hx, hy = _crtyd_half(mod, 90.0)
    cy = (hfb[3] + gap + hy) if direction == "D" else (hfb[1] - gap - hy)
    ox = min(hf.ox, ind_left - TEMPLATE_CLEAR - hx)
    return _Part(bref, mod, 90.0, "top", round(ox, 4), round(cy, 4))


def _bulk_cap(mod: Path, hf: _Part, direction: str, gap: float,
              ind_left: float, bref: str) -> _Part:
    if not _nat.loaded():
        raise RuntimeError("native bulk_cap required")
    hx, hy = _crtyd_half(mod, 90.0)
    ox, oy = _nat.module().bulk_cap_pose(
        hf.ox, hf.local_box(), direction, gap, hx, hy, ind_left,
        TEMPLATE_CLEAR)
    if _nat.trace():
        ref = _bulk_cap_py(mod, hf, direction, gap, ind_left, bref)
        if (ox, oy) != (ref.ox, ref.oy):
            raise AssertionError(
                "native bulk_cap_pose DIVERGENCE: "
                f"cpp={(ox, oy)} python={(ref.ox, ref.oy)}")
    return _Part(bref, mod, 90.0, "top", ox, oy)


def _cout_column_py(resolvable: dict[str, Path], out_caps: list[str],
                    ind_out_box: tuple[float, float, float, float],
                    pad: float) -> list[_Part]:
    if not out_caps:
        return []
    mods = [resolvable[c] for c in out_caps]
    halves = [_crtyd_half(m, 90.0) for m in mods]
    hx = max(h[0] for h in halves)
    col_x = round(ind_out_box[2] + _COUT_GAP + pad + hx, 4)
    pad_cy = (ind_out_box[1] + ind_out_box[3]) / 2.0
    step = TEMPLATE_CLEAR + pad
    heights = [2 * h[1] for h in halves]
    total = sum(heights) + step * (len(out_caps) - 1)
    y = pad_cy - total / 2.0
    parts: list[_Part] = []
    for c, m, (_chx, chy) in zip(out_caps, mods, halves, strict=True):
        cy = y + chy
        parts.append(_Part(c, m, 90.0, "top", col_x, round(cy, 4)))
        y += 2 * chy + step
    return parts


def _cout_column(resolvable: dict[str, Path], out_caps: list[str],
                 ind_out_box: tuple[float, float, float, float],
                 pad: float) -> list[_Part]:
    if not out_caps:
        return []
    if not _nat.loaded():
        raise RuntimeError("native cout_column required")
    mods = [resolvable[c] for c in out_caps]
    halves = [_crtyd_half(m, 90.0) for m in mods]
    centers = [tuple(p) for p in _nat.module().cout_column_centers(
        ind_out_box, pad, _COUT_GAP, TEMPLATE_CLEAR, halves)]
    parts = [_Part(c, m, 90.0, "top", cx, cy)
             for c, m, (cx, cy) in zip(out_caps, mods, centers,
                                       strict=True)]
    if _nat.trace():
        ref = _cout_column_py(resolvable, out_caps, ind_out_box, pad)
        hit = [(p.bref, p.ox, p.oy) for p in parts]
        want = [(p.bref, p.ox, p.oy) for p in ref]
        if hit != want:
            raise AssertionError(
                "native cout_column_centers DIVERGENCE: "
                f"cpp={hit} python={want}")
    return parts


class ZoneInfeasible(RuntimeError):
    pass


_CAND_STEP = 0.5
_CAND_CAP = 400
_CAND_RADIUS = 9.0
_NODE_BUDGET = 300_000
_SEAT_TRACE = os.environ.get("SCHGEN_SEAT_TRACE", "") == "1"

_Demand = tuple[str, "list[str] | None", float, "list[str] | None", float]
_Cand = tuple[_Part, tuple[float, float, float, float]]


def _candidates(bref: str, mod: Path, ib: dict[str, tuple],
                icb: tuple[float, float, float, float],
                target_pins: list[str] | None,
                bound: float, keep_pins: list[str] | None, keep_min: float,
                pad: float, skel_boxes: list[tuple[float, float, float, float]],
                forbid_plus_x: bool = True) -> list[_Cand]:
    if not _nat.loaded():
        raise RuntimeError("native candidates required")
    got = _candidates_native(bref, mod, ib, icb, target_pins, bound,
                             keep_pins, keep_min, pad, skel_boxes,
                             forbid_plus_x)
    if _nat.trace():
        ref = _candidates_py(bref, mod, ib, icb, target_pins, bound,
                             keep_pins, keep_min, pad, skel_boxes,
                             forbid_plus_x)
        a = [(p.rot, p.ox, p.oy) for p, _b in got]
        b = [(p.rot, p.ox, p.oy) for p, _b in ref]
        if a != b:
            raise AssertionError(
                f"native candidates DIVERGENCE: {bref} cpp={a[:6]} "
                f"python={b[:6]} n={len(a)}/{len(b)}")
    return got


def _candidates_native(bref: str, mod: Path, ib: dict[str, tuple],
                       icb: tuple[float, float, float, float],
                       target_pins: list[str] | None,
                       bound: float, keep_pins: list[str] | None,
                       keep_min: float, pad: float,
                       skel_boxes: list[tuple[float, float, float, float]],
                       forbid_plus_x: bool) -> list[_Cand]:
    if target_pins:
        tgt = _pin_box(ib, target_pins)
        all_pins = target_pins
    else:
        allb = list(ib.values())
        tgt = (min(b[0] for b in allb), min(b[1] for b in allb),
               max(b[2] for b in allb), max(b[3] for b in allb))
        all_pins = list(ib)
    tcx, tcy = (tgt[0] + tgt[2]) / 2.0, (tgt[1] + tgt[3]) / 2.0
    n = int((_CAND_RADIUS + pad) / _CAND_STEP)
    halo = TEMPLATE_CLEAR + pad
    rots = (90.0, 0.0)
    bodies = [turn_box(_footprint_bbox(mod), rot) for rot in rots]
    rel_pads = [list(_g._pad_boxes(mod, rot).values()) for rot in rots]
    target_boxes = [ib[p] for p in all_pins if p in ib]
    keep_boxes = [ib[p] for p in keep_pins if p in ib] if keep_pins else []
    hits, truncated = _nat.module().seat_candidates(
        tcx, tcy, n, _CAND_STEP, halo, _q.snap_erosion_bound(bound),
        keep_min, forbid_plus_x, _CAND_CAP, icb, list(skel_boxes),
        list(rots), bodies, rel_pads, target_boxes, keep_boxes)
    if truncated:
        _fb.record("cand_cap_truncated")
    return [(_Part(bref, mod, rot, "top", cx, cy), (x0, y0, x1, y1))
            for _d, _ax, _ay, rot, cx, cy, x0, y0, x1, y1 in hits]


def _candidates_py(bref: str, mod: Path, ib: dict[str, tuple],
                   icb: tuple[float, float, float, float],
                   target_pins: list[str] | None,
                   bound: float, keep_pins: list[str] | None, keep_min: float,
                   pad: float, skel_boxes: list[tuple[float, float, float, float]],
                   forbid_plus_x: bool = True) -> list[_Cand]:
    if target_pins:
        tgt = _pin_box(ib, target_pins)
    else:
        allb = list(ib.values())
        tgt = (min(b[0] for b in allb), min(b[1] for b in allb),
               max(b[2] for b in allb), max(b[3] for b in allb))
    tcx, tcy = (tgt[0] + tgt[2]) / 2.0, (tgt[1] + tgt[3]) / 2.0
    all_pins = list(ib) if not target_pins else target_pins
    n = int((_CAND_RADIUS + pad) / _CAND_STEP)
    halo = TEMPLATE_CLEAR + pad
    scored: list[tuple[float, float, float, _Part, tuple]] = []
    for rot in (90.0, 0.0):
        for gx in range(-n, n + 1):
            for gy in range(-n, n + 1):
                cx = round(tcx + gx * _CAND_STEP, 4)
                cy = round(tcy + gy * _CAND_STEP, 4)
                p = _Part(bref, mod, rot, "top", cx, cy)
                b = p.local_box()
                if forbid_plus_x and b[2] + halo > icb[2]:
                    continue
                if _boxes_overlap(b, icb, halo):
                    continue
                if any(_boxes_overlap(b, s, halo) for s in skel_boxes):
                    continue
                d = _pins_to_target(p, ib, all_pins)
                eff = _q.snap_erosion_bound(bound)
                if d > eff:
                    continue
                if keep_pins and _pins_to_target(p, ib, keep_pins) < keep_min:
                    continue
                scored.append((round(d, 4), abs(cx), abs(cy), p, b))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3].rot))
    if len(scored) > _CAND_CAP:
        _fb.record("cand_cap_truncated")
    return [(p, b) for _d, _ax, _ay, p, b in scored[:_CAND_CAP]]


def _seat_all(demands: list[_Demand], resolvable: dict[str, Path],
              ib: dict[str, tuple], icb: tuple[float, float, float, float],
              skeleton: list[_Part], pad: float,
              forbid_plus_x: bool = True) -> list[_Part]:
    if not _nat.loaded():
        raise RuntimeError("native seat_all required")
    got = _seat_all_native(demands, resolvable, ib, icb, skeleton, pad,
                           forbid_plus_x)
    if _nat.trace():
        ref = _seat_all_py(demands, resolvable, ib, icb, skeleton, pad,
                           forbid_plus_x)
        a = [(p.bref, p.rot, p.ox, p.oy) for p in got]
        b = [(p.bref, p.rot, p.ox, p.oy) for p in ref]
        if a != b:
            raise AssertionError(
                f"native seat_dfs DIVERGENCE: cpp={a} python={b}")
    return got


def _seat_all_native(demands: list[_Demand], resolvable: dict[str, Path],
                     ib: dict[str, tuple], icb: tuple[float, float, float, float],
                     skeleton: list[_Part], pad: float,
                     forbid_plus_x: bool) -> list[_Part]:
    halo = TEMPLATE_CLEAR + pad
    skel_boxes = [s.local_box() for s in skeleton]
    cand: dict[str, list[_Cand]] = {}
    for bref, tpins, bound, keep, kmin in demands:
        cand[bref] = _candidates(bref, resolvable[bref], ib, icb, tpins, bound,
                                 keep, kmin, pad, skel_boxes,
                                 forbid_plus_x=forbid_plus_x)
    order = sorted((d[0] for d in demands), key=lambda r: len(cand[r]))
    rows = [[b for _p, b in cand[r]] for r in order]
    try:
        solved, budget_hit, _nodes, pick = _nat.module().seat_dfs(
            rows, skel_boxes, halo, _NODE_BUDGET)
    except RuntimeError as exc:
        if "TRIPWIRE" in str(exc):
            raise AssertionError(str(exc)) from exc
        raise
    if budget_hit:
        _fb.record("seat_node_budget")
    if solved:
        picked = {order[i]: cand[order[i]][pick[i]][0]
                  for i in range(len(order))}
        return [picked[d[0]] for d in demands]
    return [(cand[d[0]][0][0] if cand[d[0]]
             else _Part(d[0], resolvable[d[0]], 90.0, "top", icb[0] - 1.0, 0.0))
            for d in demands]


def _seat_all_py(demands: list[_Demand], resolvable: dict[str, Path],
                 ib: dict[str, tuple], icb: tuple[float, float, float, float],
                 skeleton: list[_Part], pad: float,
                 forbid_plus_x: bool = True) -> list[_Part]:
    halo = TEMPLATE_CLEAR + pad
    skel_boxes = [s.local_box() for s in skeleton]
    cand: dict[str, list[_Cand]] = {}
    for bref, tpins, bound, keep, kmin in demands:
        cand[bref] = _candidates(bref, resolvable[bref], ib, icb, tpins, bound,
                                 keep, kmin, pad, skel_boxes,
                                 forbid_plus_x=forbid_plus_x)
    order = sorted((d[0] for d in demands), key=lambda r: len(cand[r]))
    chosen: dict[str, tuple[float, float, float, float]] = {}
    picked: dict[str, _Part] = {}

    nodes = [0]
    n_ord = len(order)

    exp: dict[str, list[tuple]] = {}
    for br, cs in cand.items():
        rows = []
        for p, b in cs:
            e0, e1, e2, e3 = b[0] - halo, b[1] - halo, b[2] + halo, b[3] + halo
            for q in skel_boxes:
                if e0 < q[2] and e2 > q[0] and e1 < q[3] and e3 > q[1]:
                    raise AssertionError(
                        f"seat DFS TRIPWIRE: candidate for {br} at "
                        f"({p.ox}, {p.oy}) rot {p.rot} conflicts with the "
                        f"skeleton under halo {halo} — _candidates no longer "
                        f"pre-clears the skeleton, or the expanded-box kernel "
                        f"drifted from _boxes_overlap; fix the kernel, never "
                        f"relax the check")
            rows.append((p, b, e0, e1, e2, e3))
        exp[br] = rows

    def _bt(i: int, boxes: list[tuple[float, float, float, float]]) -> bool:
        if i == n_ord:
            return True
        nodes[0] += 1
        if nodes[0] > _NODE_BUDGET:
            return False
        bref = order[i]
        for p, b, e0, e1, e2, e3 in exp[bref]:
            hit = False
            for q in boxes:
                if e0 < q[2] and e2 > q[0] and e1 < q[3] and e3 > q[1]:
                    hit = True
                    break
            if hit:
                continue
            chosen[bref] = b
            picked[bref] = p
            boxes.append(b)
            if _bt(i + 1, boxes):
                return True
            boxes.pop()
            del chosen[bref]
            del picked[bref]
        return False

    def _bt_traced(i: int, boxes: list[tuple[float, float, float, float]]
                   ) -> bool:
        if i == n_ord:
            return True
        nodes[0] += 1
        if nodes[0] > _NODE_BUDGET:
            return False
        if list(chosen.values()) != boxes:
            raise AssertionError(
                f"seat trace DIVERGENCE: DFS box stack {len(boxes)} out of "
                f"step with chosen {len(chosen)} at depth {i}")
        bref = order[i]
        for p, b, e0, e1, e2, e3 in exp[bref]:
            hit = False
            for q in boxes:
                if e0 < q[2] and e2 > q[0] and e1 < q[3] and e3 > q[1]:
                    hit = True
                    break
            ref = any(_boxes_overlap(b, q, halo) for q in boxes)
            if ref is not hit:
                raise AssertionError(
                    f"seat trace DIVERGENCE: expanded-box={hit} "
                    f"_boxes_overlap={ref} for {bref} candidate at "
                    f"({p.ox}, {p.oy}) rot {p.rot} over {len(boxes)} placed "
                    f"(halo {halo})")
            if hit:
                continue
            chosen[bref] = b
            picked[bref] = p
            boxes.append(b)
            if _bt_traced(i + 1, boxes):
                return True
            boxes.pop()
            del chosen[bref]
            del picked[bref]
        return False

    solved = (_bt_traced if _SEAT_TRACE else _bt)(0, [])
    if nodes[0] > _NODE_BUDGET:
        _fb.record("seat_node_budget")
    if solved:
        return [picked[d[0]] for d in demands]
    return [(cand[d[0]][0][0] if cand[d[0]]
             else _Part(d[0], resolvable[d[0]], 90.0, "top", icb[0] - 1.0, 0.0))
            for d in demands]


def _pins_to_target(p: _Part, ib: dict[str, tuple],
                    target_pins: list[str]) -> float:
    pin_boxes = {pin: ib[pin] for pin in target_pins if pin in ib}
    got = _g._pins_to_part(pin_boxes, p.pad_boxes(), list(pin_boxes))
    if got is None:
        return 1e9
    return float(got)


_PROX_CACHE: dict[tuple, list[tuple[float, float, float]]] = {}


def _build_proximity_cluster(anchor_bref: str, contract: dict,
                             bref_of: dict[str, str],
                             resolvable: dict[str, Path]) -> list[_Part] | None:
    anchor_mod = resolvable.get(anchor_bref)
    if anchor_mod is None:
        raise ZoneInfeasible(
            f"proximity cluster: anchor {anchor_bref} has no resolvable "
            f"footprint — the contract names a part the board cannot place")

    demands: list[_Demand] = []
    member_brefs: list[str] = []
    for st in contract.get("structures", []):
        if st.get("type") != "proximity":
            continue
        if bref_of.get(st.get("anchor", "")) != anchor_bref:
            continue
        apins = st.get("anchor_pins")
        bound = float(st["max_mm"])
        keep_pins: list[str] | None = None
        keep_min = 0.0
        for mf in st.get("min_from", []):
            if bref_of.get(mf.get("part", "")) == anchor_bref and mf.get("pin"):
                keep_pins = [mf["pin"]]
                keep_min = float(mf.get("min_mm", 0.0))
                break
        for mlib in st.get("members", []):
            mb = bref_of.get(mlib)
            if mb is None or mb not in resolvable:
                raise ZoneInfeasible(
                    f"proximity cluster at {anchor_bref}: member {mlib!r} "
                    f"does not resolve on this sheet — unplaceable contract")
            demands.append((mb, list(apins) if apins else None, bound,
                            keep_pins, keep_min))
            member_brefs.append(mb)

    if not demands:
        return [_Part(anchor_bref, anchor_mod, 0.0, "top", 0.0, 0.0)]

    sig = (str(anchor_mod),
           tuple((str(resolvable[d[0]]), round(d[2], 4),
                  tuple(d[1] or []), round(d[4], 4)) for d in demands))
    cached = _PROX_CACHE.get(sig)
    if cached is not None:
        anchor = _Part(anchor_bref, anchor_mod, 0.0, "top", 0.0, 0.0)
        return [anchor] + [
            _Part(mb, resolvable[mb], rot, "top", ox, oy)
            for mb, (rot, ox, oy) in zip(member_brefs, cached, strict=True)]

    anchor = _Part(anchor_bref, anchor_mod, 0.0, "top", 0.0, 0.0)
    ib = anchor.pad_boxes()
    icb = anchor.local_box()
    seated: list[_Part] = []
    solved = False
    for scale in range(0, 20):
        pad = scale * _RELAX_STEP
        seated = _seat_all(demands, resolvable, ib, icb, [anchor], pad,
                           forbid_plus_x=False)
        if (not _any_overlap([anchor, *seated])
                and _demands_met(seated, demands, ib)):
            solved = True
            break
    if not solved:
        raise ZoneInfeasible(
            f"proximity cluster at {anchor_bref}: 20-scale widen exhausted "
            f"without a collision-free, bound-satisfying seat for "
            f"{[d[0] for d in demands]} — solver infeasible (no silent "
            f"fallback, no legacy pack)")
    parts = [anchor, *seated]
    by_bref = {p.bref: p for p in seated}
    _PROX_CACHE[sig] = [(by_bref[mb].rot, by_bref[mb].ox, by_bref[mb].oy)
                        for mb in member_brefs]
    return parts


def _demands_met(seated: list[_Part], demands: list[_Demand],
                 ib: dict[str, tuple]) -> bool:
    by_bref = {p.bref: p for p in seated}
    for mb, tpins, bound, keep, kmin in demands:
        part = by_bref.get(mb)
        if part is None:
            return False
        d = _pins_to_target(part, ib, tpins or list(ib))
        if d > _q.snap_erosion_bound(bound):
            return False
        if keep and _pins_to_target(part, ib, keep) < kmin:
            return False
    return True


_MULTI_CACHE: dict[tuple, list[tuple[str, float, float, float]]] = {}

_Attract = tuple[str, "tuple[str, ...] | None", float]
_Repel = tuple[str, "str | None", float]

_ROOT_GAP = 2.0
_CONN_ROOT_CABLE_GAP = 20.0
_NET_W = 0.1
_OVEC = {"N": (0.0, -1.0), "S": (0.0, 1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}
_GRID_MAX_N = 60
_PILOT_PROX_SHEETS = _project_spec().pilot_prox_sheets


def _is_single_anchor_star(contract: dict, bref_of: dict[str, str]) -> bool:
    anchors: set[str] = set()
    for st in contract.get("structures", []):
        if st.get("type") != "proximity":
            continue
        a = bref_of.get(st.get("anchor", ""))
        if a is not None:
            anchors.add(a)
        for mf in st.get("min_from", []):
            mp = bref_of.get(mf.get("part", ""))
            if mp is not None and mp != a:
                return False
    return len(anchors) <= 1


_FLIP_MIN_PINS = 10
_FLIP_SYM_TOL = 0.1
_FLIP_DOM_PCT = 60

_SOM_PARTNERS: dict[str, tuple[Path, float, dict[str, tuple[str, ...]]]] | None \
    = None
_SHEET_INTER: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {}
_FLIP_CACHE: dict[tuple[str, str], float] = {}


def _raw_pad_centers(mod: Path) -> list[tuple[float, float]]:
    from schgen.core import sexpr
    from schgen.core.sexpr import Sym
    out: list[tuple[float, float]] = []
    for node in sexpr.loads(mod.read_text()):
        if isinstance(node, list) and node and node[0] == Sym("pad"):
            at = sexpr.find(node, "at")
            if at and len(at) >= 3:
                out.append((float(at[1]), float(at[2])))
    return out


def _pad_set_180_symmetric_py(mod: Path) -> bool:
    pts = _raw_pad_centers(mod)
    if not pts:
        return False
    cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0
    cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0
    rest = sorted(pts)
    for x, y in pts:
        tx, ty = 2.0 * cx - x, 2.0 * cy - y
        hit = next((q for q in rest
                    if abs(q[0] - tx) <= _FLIP_SYM_TOL
                    and abs(q[1] - ty) <= _FLIP_SYM_TOL), None)
        if hit is None:
            return False
        rest.remove(hit)
    return True


def _pad_set_180_symmetric(mod: Path) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native pad_set_180_symmetric required")
    pts = _raw_pad_centers(mod)
    got = bool(_nat.module().pad_set_180_symmetric(pts, _FLIP_SYM_TOL))
    if _nat.trace():
        ref = _pad_set_180_symmetric_py(mod)
        if got is not ref:
            raise AssertionError(
                "native pad_set_180_symmetric DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _som_partner_nets() -> dict[str, tuple[Path, float, dict[str, tuple[str, ...]]]]:
    global _SOM_PARTNERS
    if _SOM_PARTNERS is not None:
        return _SOM_PARTNERS
    import re

    from schgen.core.link import all_subsystem_paths, load_subsystem

    from .footprint import resolve_mod
    out: dict[str, tuple[Path, float, dict[str, tuple[str, ...]]]] = {}
    jsheets = sorted(p.stem for p in all_subsystem_paths()
                     if re.fullmatch(r"som_j\d", p.stem))
    if jsheets:
        from schgen.generate.floorplan import extract_som
        jrot = {j.ref: (90.0 if j.w < j.h else 0.0) for j in extract_som().js}
        for s in jsheets:
            jref = "J" + s[len("som_j"):]
            sc = load_subsystem(s)
            part = sc.circuit.parts.get(jref)
            mod = resolve_mod(part.footprint) if part is not None else None
            if mod is None or jref not in jrot:
                continue
            nets: dict[str, tuple[str, ...]] = {}
            for nm, net in sc.circuit.nets.items():
                pins = tuple(pr.pin for pr in net.pins if pr.ref == jref)
                if pins:
                    nets[nm] = pins
            out[s] = (mod, jrot[jref], nets)
    _SOM_PARTNERS = out
    return out


def _sheet_inter_nets(sheet_name: str) -> dict[str, dict[str, tuple[str, ...]]]:
    hit = _SHEET_INTER.get(sheet_name)
    if hit is not None:
        return hit
    from schgen.core.link import load_subsystem
    from schgen.core.model import NetClass
    sc = load_subsystem(sheet_name)
    per_ref: dict[str, dict[str, tuple[str, ...]]] = {}
    for nm, net in sc.circuit.nets.items():
        if net.net_class not in (NetClass.PORT, NetClass.POWER,
                                 NetClass.GROUND):
            continue
        for pr in net.pins:
            if pr.ref.startswith("#"):
                continue
            d = per_ref.setdefault(pr.ref, {})
            d[nm] = d.get(nm, ()) + (pr.pin,)
    _SHEET_INTER[sheet_name] = per_ref
    return per_ref


def _long_axis_coords_py(mod: Path, rot: float) -> dict[str, float]:
    boxes = _g._pad_boxes(mod, rot)
    cs = {n: ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
          for n, b in boxes.items()}
    xs = [c[0] for c in cs.values()]
    ys = [c[1] for c in cs.values()]
    ax = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
    return {n: c[ax] for n, c in cs.items()}


def _long_axis_coords(mod: Path, rot: float) -> dict[str, float]:
    if not _nat.loaded():
        raise RuntimeError("native long_axis_coords required")
    boxes = _g._pad_boxes(mod, rot)
    if not boxes:
        raise RuntimeError("long_axis_coords: centers required")
    centers = [(n, (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
               for n, b in boxes.items()]
    got = {n: v for n, v in _nat.module().long_axis_coords(centers)}
    if _nat.trace():
        ref = _long_axis_coords_py(mod, rot)
        if got != ref:
            raise AssertionError(
                "native long_axis_coords DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _inversion_count_py(pairs: list[tuple[float, float, str]]) -> int:
    seq = [b for _a, b, _n in sorted(pairs, key=lambda t: (t[0], t[2]))]
    inv = 0
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            if seq[i] > seq[j] + 1e-9:
                inv += 1
    return inv


def _inversion_count(pairs: list[tuple[float, float, str]]) -> int:
    if not _nat.loaded():
        raise RuntimeError("native inversion_count required")
    got = int(_nat.module().inversion_count(pairs))
    if _nat.trace():
        ref = _inversion_count_py(pairs)
        if got != ref:
            raise AssertionError(
                "native inversion_count DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _som_flip_rot(sheet_name: str, lib_ref: str, mod: Path) -> float:
    key = (sheet_name, lib_ref)
    hit = _FLIP_CACHE.get(key)
    if hit is not None:
        return hit
    rot = 0.0
    if (len(_g._pad_boxes(mod, 0.0)) >= _FLIP_MIN_PINS
            and mod.stem not in CONN_MATING_FACE
            and not sheet_name.startswith("som_j")
            and _pad_set_180_symmetric(mod)):
        inter = _sheet_inter_nets(sheet_name).get(lib_ref, {})
        partners = _som_partner_nets()
        if inter and partners:
            counts = {s: sum(1 for nm in inter if nm in p[2])
                      for s, p in partners.items()}
            psheet, cnt = sorted(counts.items(),
                                 key=lambda kv: (-kv[1], kv[0]))[0]
            if cnt * 100 >= _FLIP_DOM_PCT * len(inter):
                jmod, jrot, jnets = partners[psheet]
                jcoord = _long_axis_coords(jmod, jrot)
                knets = sorted(nm for nm in inter if nm in jnets)

                def _inv(r: float) -> int:
                    pc = _long_axis_coords(mod, r)
                    pairs: list[tuple[float, float, str]] = []
                    for nm in knets:
                        a = [pc[p] for p in inter[nm] if p in pc]
                        b = [jcoord[p] for p in jnets[nm] if p in jcoord]
                        if a and b:
                            pairs.append((sum(a) / len(a),
                                          sum(b) / len(b), nm))
                    return _inversion_count(pairs)

                if _inv(180.0) < _inv(0.0):
                    rot = 180.0
    _FLIP_CACHE[key] = rot
    return rot


def _topo_order_py(parts: set[str], deps: dict[str, set[str]]) -> list[str] | None:
    indeg = {p: len(deps.get(p, set())) for p in parts}
    ready = sorted(p for p in parts if indeg[p] == 0)
    out: list[str] = []
    while ready:
        p = ready.pop(0)
        out.append(p)
        for q in sorted(parts):
            if p in deps.get(q, set()):
                indeg[q] -= 1
                if indeg[q] == 0:
                    ready.append(q)
        ready.sort()
    return out if len(out) == len(parts) else None


def _topo_order(parts: set[str], deps: dict[str, set[str]]) -> list[str] | None:
    if not _nat.loaded():
        raise RuntimeError("native topo_order required")
    raw = _nat.module().topo_order(
        list(parts), [(k, list(v)) for k, v in deps.items()])
    got = None if raw is None else list(raw)
    if _nat.trace():
        ref = _topo_order_py(parts, deps)
        if got != ref:
            raise AssertionError(
                "native topo_order DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


_SHEET_NETS_CACHE: dict[str, dict[tuple[str, str], str]] = {}


def _sheet_pad_nets(sheet_name: str) -> dict[tuple[str, str], str]:
    hit = _SHEET_NETS_CACHE.get(sheet_name)
    if hit is not None:
        return hit
    out: dict[tuple[str, str], str] = {}
    try:
        from schgen.core.link import load_subsystem
        band = _g._board_refs_by_sheet(sheet_name)
        sc = load_subsystem(sheet_name)
    except SystemExit:
        band, sc = {}, None
    if sc is not None:
        for nname, net in sc.circuit.nets.items():
            for p in net.pins:
                b = band.get(p.ref)
                if b is not None:
                    out[(b, p.pin)] = nname
    _SHEET_NETS_CACHE[sheet_name] = out
    return out


def _net_rot180_differs_py(mod: Path, mem_nets: dict[str, str]) -> bool:
    def sig(rot: float):
        return sorted((round((b[0] + b[2]) / 2, 2), round((b[1] + b[3]) / 2, 2),
                       mem_nets[n])
                      for n, b in _g._pad_boxes(mod, rot).items()
                      if n in mem_nets)
    return sig(0.0) != sig(180.0)


def _net_rot180_differs(mod: Path, mem_nets: dict[str, str]) -> bool:
    if not _nat.loaded():
        raise RuntimeError("native named_box_center_sigs required")

    def sig(rot: float):
        rows = [(mem_nets[n], *b)
                for n, b in _g._pad_boxes(mod, rot).items() if n in mem_nets]
        return [tuple(r) for r in _nat.module().named_box_center_sigs(rows, 2)]

    got = sig(0.0) != sig(180.0)
    if _nat.trace():
        ref = _net_rot180_differs_py(mod, mem_nets)
        if got is not ref:
            raise AssertionError(
                "native named_box_center_sigs DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _gcandidates(bref: str, mod: Path,
                 attractors: list[_Attract], repuls: list[_Repel],
                 placed: dict[str, _Part], pad: float,
                 forbid: list[tuple[float, float, float, float]] | None = None,
                 conn_roots: set[str] | None = None,
                 pad_net: dict[tuple[str, str], str] | None = None
                 ) -> list[_Part]:
    head = _gc_head(bref, mod, attractors, repuls, placed, pad, conn_roots,
                    pad_net)
    out = _gc_scan_fast(bref, mod, forbid, *head)
    if _SEAT_TRACE:
        ref = _gc_scan_ref(bref, mod, forbid, *head)
        if ([(q.bref, q.rot, q.ox, q.oy) for q in out]
                != [(q.bref, q.rot, q.ox, q.oy) for q in ref]):
            raise AssertionError(
                f"seat trace DIVERGENCE: _gc_scan_fast != _gc_scan_ref for "
                f"{bref} ({len(out)} vs {len(ref)} poses)")
    return out


def _gc_head(bref: str, mod: Path,
             attractors: list[_Attract], repuls: list[_Repel],
             placed: dict[str, _Part], pad: float,
             conn_roots: set[str] | None,
             pad_net: dict[tuple[str, str], str] | None) -> tuple:
    att: list[tuple[dict[str, tuple], list[str], float]] = []
    for ab, apins, bound in attractors:
        pb = placed[ab].pad_boxes()
        att.append((pb, list(apins) if apins else list(pb), bound))
    prim = min(range(len(att)), key=lambda k: att[k][2])
    ppb, ppins, pbound = att[prim]
    tgt = _pin_box(ppb, ppins)
    tcx, tcy = (tgt[0] + tgt[2]) / 2.0, (tgt[1] + tgt[3]) / 2.0
    rep: list[tuple[dict[str, tuple], list[str], float]] = []
    for rb, rpin, mm in repuls:
        pb = placed[rb].pad_boxes()
        rep.append((pb, [rpin] if rpin else list(pb), mm))
    placed_boxes = [pp.local_box() for pp in placed.values()]
    halo = TEMPLATE_CLEAR + pad
    member_pins = len(_g._pad_boxes(mod, 0.0))
    own_need = intelligent_need(member_pins)[0] if member_pins >= 3 else 0.0
    member_exempt = (_is_cluster_passive(bref, member_pins)
                     or is_testpoint_ref(bref))
    subjects: list[tuple[tuple[float, float, float, float], float]] = []
    for pp in placed.values():
        npins = len(_g._pad_boxes(pp.mod, 0.0))
        if npins >= 3 and not member_exempt:
            subjects.append((pp.local_box(),
                             _q.quant_credit(intelligent_need(npins)[0])))
        if own_need and not (_is_cluster_passive(pp.bref, npins)
                             or is_testpoint_ref(pp.bref)):
            subjects.append((pp.local_box(), _q.quant_credit(own_need)))
    t_half = max(tgt[2] - tgt[0], tgt[3] - tgt[1]) / 2.0
    n = min(int((t_half + pbound + _CAND_RADIUS + pad) / _CAND_STEP),
            _GRID_MAX_N)
    mem_nets: dict[str, str] = {}
    net_pts: dict[str, list[tuple[float, float]]] = {}
    if pad_net and member_pins >= 4:
        mem_nets = {pn: pad_net[(bref, pn)]
                    for pn in _g._pad_boxes(mod, 0.0) if (bref, pn) in pad_net}
        want = set(mem_nets.values())
        for pp in placed.values():
            for pn, bb in pp.pad_boxes().items():
                nn = pad_net.get((pp.bref, pn))
                if nn in want:
                    net_pts.setdefault(nn, []).append(
                        ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0))
    rots = (90.0, 0.0)
    if net_pts and _net_rot180_differs(mod, mem_nets):
        rots = (0.0, 90.0, 180.0, 270.0)
    align: dict[float, list[tuple[float, float, list[tuple[float, float]]]]] = {}
    rel_pads: dict[float, list[tuple[float, float, float, float]]] = {}
    for rot in rots:
        arr = []
        for pn, bb in _g._pad_boxes(mod, rot).items():
            pts = net_pts.get(mem_nets.get(pn, ""))
            if pts:
                arr.append(((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0, pts))
        align[rot] = arr
        rel_pads[rot] = list(_g._pad_boxes(mod, rot).values())
    att_pre = [([pb[pin] for pin in pins if pin in pb],
                _q.snap_erosion_bound(bound))
               for pb, pins, bound in att]
    rep_pre = [([pb[pin] for pin in pins if pin in pb],
                _q.snap_erosion_pad(mm))
               for pb, pins, mm in rep]
    return (tcx, tcy, n, halo, placed_boxes, subjects, att_pre, rep_pre, rots,
            align, rel_pads)


def _gc_scan_ref(bref, mod, forbid, tcx, tcy, n, halo, placed_boxes, subjects,
                 att_pre, rep_pre, rots, align, rel_pads):
    _hypot = math.hypot
    scored: list[tuple[float, float, float, float, _Part]] = []
    for rot in rots:
        rel = rel_pads[rot]
        for gx in range(-n, n + 1):
            for gy in range(-n, n + 1):
                cx = round(tcx + gx * _CAND_STEP, 4)
                cy = round(tcy + gy * _CAND_STEP, 4)
                p = _Part(bref, mod, rot, "top", cx, cy)
                b = p.local_box()
                if any(_boxes_overlap(b, q, halo) for q in placed_boxes):
                    continue
                if forbid and any(_boxes_overlap(b, f, halo) for f in forbid):
                    continue
                dsum = 0.0
                ok = True
                for tboxes, eff in att_pre:
                    best = 1e9
                    for tb in tboxes:
                        t0, t1, t2, t3 = tb
                        for rb in rel:
                            dx = t0 - (cx + rb[2])
                            qx = (cx + rb[0]) - t2
                            if qx > dx:
                                dx = qx
                            if dx < 0.0:
                                dx = 0.0
                            dy = t1 - (cy + rb[3])
                            qy = (cy + rb[1]) - t3
                            if qy > dy:
                                dy = qy
                            if dy < 0.0:
                                dy = 0.0
                            g = _hypot(dx, dy)
                            if g < best:
                                best = g
                    if best > eff:
                        ok = False
                        break
                    dsum += best
                if not ok:
                    continue
                for tboxes, mmv in rep_pre:
                    best = 1e9
                    for tb in tboxes:
                        t0, t1, t2, t3 = tb
                        for rb in rel:
                            dx = t0 - (cx + rb[2])
                            qx = (cx + rb[0]) - t2
                            if qx > dx:
                                dx = qx
                            if dx < 0.0:
                                dx = 0.0
                            dy = t1 - (cy + rb[3])
                            qy = (cy + rb[1]) - t3
                            if qy > dy:
                                dy = qy
                            if dy < 0.0:
                                dy = 0.0
                            g = _hypot(dx, dy)
                            if g < best:
                                best = g
                    if best < mmv:
                        ok = False
                        break
                if not ok:
                    continue
                for sb, need in subjects:
                    if _boxes_overlap(b, sb, need):
                        ok = False
                        break
                if not ok:
                    continue
                dis = 0.0
                for rxc, ryc, pts in align[rot]:
                    px, py = cx + rxc, cy + ryc
                    dis += min(abs(px - qx) + abs(py - qy) for qx, qy in pts)
                scored.append((round(dsum + _NET_W * dis, 4),
                               abs(cx), abs(cy), rot, p))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    if len(scored) > _CAND_CAP:
        _fb.record("cand_cap_truncated")
    return [t[4] for t in scored[:_CAND_CAP]]


def _gc_union_py(boxes):
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _gc_union(boxes):
    if not _nat.loaded():
        raise RuntimeError("native gc_union required")
    got = _nat.module().boxes_union(list(boxes))
    if got is not None:
        got = tuple(got)
    if _nat.trace():
        ref = _gc_union_py(boxes)
        if got != ref:
            raise AssertionError(
                f"native boxes_union DIVERGENCE: cpp={got} python={ref}")
    return got


def _gc_scan_native(bref, mod, forbid, tcx, tcy, n, halo, placed_boxes,
                    subjects, att_pre, rep_pre, rots, align, rel_pads):
    geom = _nat.module()
    bodies = [turn_box(_footprint_bbox(mod), rot) for rot in rots]
    hits, truncated = geom.seat_scan(
        tcx, tcy, n, _CAND_STEP, halo, _NET_W, _CAND_CAP,
        list(placed_boxes), list(forbid or ()),
        [(sb, need) for sb, need in subjects],
        [(tboxes, eff) for tboxes, eff in att_pre],
        [(tboxes, mmv) for tboxes, mmv in rep_pre],
        list(rots),
        [list(rel_pads[rot]) for rot in rots],
        bodies,
        [list(align[rot]) for rot in rots])
    if truncated:
        _fb.record("cand_cap_truncated")
    if _nat.trace():
        ref = _gc_scan_fast_py(bref, mod, forbid, tcx, tcy, n, halo,
                               placed_boxes, subjects, att_pre, rep_pre,
                               rots, align, rel_pads)
        got = [(h[3], h[4], h[5]) for h in hits]
        want = [(q.rot, q.ox, q.oy) for q in ref]
        if got != want:
            idx = next((i for i, (a, b) in enumerate(zip(got, want, strict=False))
                        if a != b), min(len(got), len(want)))
            raise AssertionError(
                f"native seat DIVERGENCE: {bref} at {idx} "
                f"cpp={got[idx:idx + 4]} python={want[idx:idx + 4]} "
                f"n={len(got)}/{len(want)}")
    return [_Part(bref, mod, rot, "top", cx, cy)
            for _s, _ax, _ay, rot, cx, cy in hits]


def _gc_scan_fast(bref, mod, forbid, tcx, tcy, n, halo, placed_boxes, subjects,
                  att_pre, rep_pre, rots, align, rel_pads):
    if not _nat.loaded():
        raise RuntimeError("native gc_scan_fast required")
    return _gc_scan_native(bref, mod, forbid, tcx, tcy, n, halo,
                           placed_boxes, subjects, att_pre, rep_pre,
                           rots, align, rel_pads)


def _gc_scan_fast_py(bref, mod, forbid, tcx, tcy, n, halo, placed_boxes, subjects,
                  att_pre, rep_pre, rots, align, rel_pads):
    _hypot = math.hypot
    att3 = [(tboxes, eff, _gc_union(tboxes)) for tboxes, eff in att_pre]
    rep3 = [(tboxes, mmv, _gc_union(tboxes)) for tboxes, mmv in rep_pre]
    xs = [round(tcx + gx * _CAND_STEP, 4) for gx in range(-n, n + 1)]
    ys = [round(tcy + gy * _CAND_STEP, 4) for gy in range(-n, n + 1)]
    scored: list[tuple[float, float, float, float, _Part]] = []
    for rot in rots:
        rel = rel_pads[rot]
        rb0, rb1, rb2, rb3 = turn_box(_footprint_bbox(mod), rot)
        ru = _gc_union(rel)
        ru0 = ru1 = ru2 = ru3 = 0.0
        if ru is not None:
            ru0, ru1, ru2, ru3 = ru
        arr = align[rot]
        for cx in xs:
            b0 = cx + rb0
            b2 = cx + rb2
            h0 = b0 - halo
            h2 = b2 + halo
            cu0 = cx + ru0
            cu2 = cx + ru2
            for cy in ys:
                b1 = cy + rb1
                b3 = cy + rb3
                h1 = b1 - halo
                h3 = b3 + halo
                ok = True
                for q in placed_boxes:
                    if h0 < q[2] and h2 > q[0] and h1 < q[3] and h3 > q[1]:
                        ok = False
                        break
                if not ok:
                    continue
                if forbid:
                    for f in forbid:
                        if h0 < f[2] and h2 > f[0] and h1 < f[3] and h3 > f[1]:
                            ok = False
                            break
                    if not ok:
                        continue
                cu1 = cy + ru1
                cu3 = cy + ru3
                dsum = 0.0
                rel_off = None
                for tboxes, eff, u in att3:
                    if u is None or ru is None:
                        if 1e9 > eff:
                            ok = False
                            break
                        dsum += 1e9
                        continue
                    dx = u[0] - cu2
                    qx = cu0 - u[2]
                    if qx > dx:
                        dx = qx
                    if dx < 0.0:
                        dx = 0.0
                    dy = u[1] - cu3
                    qy = cu1 - u[3]
                    if qy > dy:
                        dy = qy
                    if dy < 0.0:
                        dy = 0.0
                    lb = _hypot(dx, dy)
                    if lb > eff:
                        ok = False
                        break
                    if rel_off is None:
                        rel_off = [(cx + rb[0], cy + rb[1],
                                    cx + rb[2], cy + rb[3]) for rb in rel]
                    best = 1e9
                    for tb in tboxes:
                        t0, t1, t2, t3 = tb
                        for ro in rel_off:
                            dx = t0 - ro[2]
                            qx = ro[0] - t2
                            if qx > dx:
                                dx = qx
                            if dx < 0.0:
                                dx = 0.0
                            dy = t1 - ro[3]
                            qy = ro[1] - t3
                            if qy > dy:
                                dy = qy
                            if dy < 0.0:
                                dy = 0.0
                            g = _hypot(dx, dy)
                            if g < best:
                                best = g
                    if best < lb:
                        raise AssertionError(
                            f"seat LB TRIPWIRE: exact attractor gap {best} < "
                            f"union lower bound {lb} for {bref} pose "
                            f"({cx}, {cy}) rot {rot} — union monotonicity "
                            f"broke; fix the bound, never relax the test")
                    if best > eff:
                        ok = False
                        break
                    dsum += best
                if not ok:
                    continue
                for tboxes, mmv, u in rep3:
                    if u is None or ru is None:
                        if 1e9 < mmv:
                            ok = False
                            break
                        continue
                    dx = u[0] - cu2
                    qx = cu0 - u[2]
                    if qx > dx:
                        dx = qx
                    if dx < 0.0:
                        dx = 0.0
                    dy = u[1] - cu3
                    qy = cu1 - u[3]
                    if qy > dy:
                        dy = qy
                    if dy < 0.0:
                        dy = 0.0
                    lb = _hypot(dx, dy)
                    if lb >= mmv:
                        continue
                    if rel_off is None:
                        rel_off = [(cx + rb[0], cy + rb[1],
                                    cx + rb[2], cy + rb[3]) for rb in rel]
                    best = 1e9
                    for tb in tboxes:
                        t0, t1, t2, t3 = tb
                        for ro in rel_off:
                            dx = t0 - ro[2]
                            qx = ro[0] - t2
                            if qx > dx:
                                dx = qx
                            if dx < 0.0:
                                dx = 0.0
                            dy = t1 - ro[3]
                            qy = ro[1] - t3
                            if qy > dy:
                                dy = qy
                            if dy < 0.0:
                                dy = 0.0
                            g = _hypot(dx, dy)
                            if g < best:
                                best = g
                    if best < lb:
                        raise AssertionError(
                            f"seat LB TRIPWIRE: exact repulsor gap {best} < "
                            f"union lower bound {lb} for {bref} pose "
                            f"({cx}, {cy}) rot {rot} — union monotonicity "
                            f"broke; fix the bound, never relax the test")
                    if best < mmv:
                        ok = False
                        break
                if not ok:
                    continue
                for sb, need in subjects:
                    if (b0 - need < sb[2] and b2 + need > sb[0]
                            and b1 - need < sb[3] and b3 + need > sb[1]):
                        ok = False
                        break
                if not ok:
                    continue
                dis = 0.0
                for rxc, ryc, pts in arr:
                    px, py = cx + rxc, cy + ryc
                    dis += min(abs(px - qx) + abs(py - qy) for qx, qy in pts)
                scored.append((round(dsum + _NET_W * dis, 4),
                               abs(cx), abs(cy), rot,
                               _Part(bref, mod, rot, "top", cx, cy)))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    if len(scored) > _CAND_CAP:
        _fb.record("cand_cap_truncated")
    return [t[4] for t in scored[:_CAND_CAP]]


def _seat_multi(order: list[str], roots: set[str],
                attractors: dict[str, list[_Attract]],
                repulsors: dict[str, list[_Repel]],
                resolvable: dict[str, Path], pad: float,
                conn_roots: set[str] | None = None,
                outer_vec: tuple[float, float] | None = None,
                root_rot: dict[str, float] | None = None,
                pad_net: dict[tuple[str, str], str] | None = None
                ) -> dict[str, _Part] | None:
    placed: dict[str, _Part] = {}
    _along_y = outer_vec is not None and abs(outer_vec[0]) > abs(outer_vec[1])
    cursor = 0.0
    prev_conn = False
    for r in sorted(roots):
        is_conn = bool(conn_roots and r in conn_roots)
        gap = _CONN_ROOT_CABLE_GAP if (prev_conn and is_conn) else _ROOT_GAP
        rr = (root_rot or {}).get(r, 0.0)
        p0 = _Part(r, resolvable[r], rr, "top", 0.0, 0.0)
        b0 = p0.local_box()
        if _along_y:
            d = round(cursor - b0[1], 4)
            p = _Part(r, resolvable[r], rr, "top", 0.0, d)
            cursor = p.local_box()[3] + TEMPLATE_CLEAR + pad + gap
        else:
            d = round(cursor - b0[0], 4)
            p = _Part(r, resolvable[r], rr, "top", d, 0.0)
            cursor = p.local_box()[2] + TEMPLATE_CLEAR + pad + gap
        placed[r] = p
        prev_conn = is_conn
    _sweeps: list[tuple[float, float, float, float]] = []
    if conn_roots and outer_vec is not None:
        _far = 1e4
        vx, vy = outer_vec
        faces = []
        for r in sorted(conn_roots):
            if r not in placed:
                continue
            pp = placed[r]
            sb = _rot_pad_bbox(pp.mod, pp.rot)
            faces.append(pp.ox + sb[2] if vx > 0
                         else pp.ox + sb[0] if vx < 0
                         else pp.oy + sb[3] if vy > 0
                         else pp.oy + sb[1])
        if faces:
            face = min(faces) if (vx > 0 or vy > 0) else max(faces)
            face += (-_q.seat_slide() if (vx > 0 or vy > 0)
                     else _q.seat_slide())
            if vx > 0:
                _sweeps.append((face, -_far, _far, _far))
            elif vx < 0:
                _sweeps.append((-_far, -_far, face, _far))
            elif vy > 0:
                _sweeps.append((-_far, face, _far, _far))
            else:
                _sweeps.append((-_far, -_far, _far, face))
    for bref in order:
        if bref in roots:
            continue
        cands = _gcandidates(bref, resolvable[bref], attractors[bref],
                             repulsors.get(bref, []), placed, pad,
                             forbid=_sweeps or None, conn_roots=conn_roots,
                             pad_net=pad_net)
        if not cands:
            return None
        placed[bref] = cands[0]
    return placed


def _solve_contract(contract: dict, bref_of: dict[str, str],
                    resolvable: dict[str, Path],
                    outer_dir: str | None = None,
                    sheet_name: str | None = None,
                    pad_net: dict[tuple[str, str], str] | None = None
                    ) -> list[_Part]:
    attractors: dict[str, list[_Attract]] = {}
    repulsors: dict[str, list[_Repel]] = {}
    all_parts: set[str] = set()
    members: set[str] = set()
    for st in contract.get("structures", []):
        if st.get("type") != "proximity":
            continue
        a = bref_of.get(st.get("anchor", ""))
        if a is None or a not in resolvable:
            raise ZoneInfeasible(
                f"contract graph: proximity anchor {st.get('anchor')!r} "
                f"does not resolve on this sheet — unplaceable contract")
        apins = tuple(st["anchor_pins"]) if st.get("anchor_pins") else None
        bound = float(st["max_mm"])
        mfs: list[tuple[str, str | None, float]] = []
        for mf in st.get("min_from", []):
            rp = bref_of.get(mf.get("part", ""))
            if rp is None or rp not in resolvable:
                continue
            mfs.append((rp, mf.get("pin"), float(mf.get("min_mm", 0.0))))
        all_parts.add(a)
        for mlib in st.get("members", []):
            mb = bref_of.get(mlib)
            if mb is None or mb not in resolvable:
                raise ZoneInfeasible(
                    f"contract graph: proximity member {mlib!r} does not "
                    f"resolve on this sheet — unplaceable contract")
            all_parts.add(mb)
            members.add(mb)
            attractors.setdefault(mb, []).append((a, apins, bound))
            for rp, pin, mm in mfs:
                repulsors.setdefault(mb, []).append((rp, pin, mm))
                all_parts.add(rp)
    if not members:
        raise ZoneInfeasible(
            "contract graph: no resolvable proximity members — an authored "
            "contract with nothing the solver can place")

    adj: dict[str, set[str]] = {p: set() for p in all_parts}
    for m in members:
        for a, _p, _b in attractors.get(m, []):
            adj[m].add(a)
            adj[a].add(m)
        for rp, _pin, _mm in repulsors.get(m, []):
            adj[m].add(rp)
            adj[rp].add(m)
    comps: list[set[str]] = []
    seen: set[str] = set()
    for p in sorted(all_parts):
        if p in seen:
            continue
        stack, comp = [p], set()
        while stack:
            q = stack.pop()
            if q in seen:
                continue
            seen.add(q)
            comp.add(q)
            stack.extend(adj[q] - seen)
        comps.append(comp)

    _outer_vec = {"N": (0.0, -1.0), "S": (0.0, 1.0),
                  "E": (1.0, 0.0), "W": (-1.0, 0.0)}.get(outer_dir or "")
    _conn_roots = {r for r in (all_parts - members)
                   if resolvable[r].stem in CONN_MATING_FACE}
    _root_rot = {r: connector_edge_rotation(
                     CONN_MATING_FACE[resolvable[r].stem], outer_dir)
                 for r in _conn_roots} if outer_dir else {}
    if sheet_name:
        _lib_of = {b: lb for lb, b in bref_of.items()}
        for r in sorted(all_parts - members):
            if r in _conn_roots or r in _root_rot or r not in _lib_of:
                continue
            fr = _som_flip_rot(sheet_name, _lib_of[r], resolvable[r])
            if fr:
                _root_rot[r] = fr

    sig = (outer_dir or "",
           tuple(sorted(_root_rot.items())),
           tuple((b, str(resolvable[b])) for b in sorted(all_parts)),
           tuple((m, tuple((a, p or (), round(bd, 4))
                           for a, p, bd in attractors.get(m, [])),
                  tuple((r, pn or "", round(mm, 4))
                        for r, pn, mm in repulsors.get(m, [])))
                 for m in sorted(members)),
           tuple(sorted((r, p, n) for (r, p), n in (pad_net or {}).items()
                        if r in all_parts)))
    cached = _MULTI_CACHE.get(sig)
    if cached is not None:
        return [_Part(b, resolvable[b], rot, "top", ox, oy)
                for b, rot, ox, oy in cached]

    clusters: list[list[_Part]] = []
    for comp in sorted(comps, key=sorted):
        cl = _solve_component(comp, members, attractors, repulsors, resolvable,
                              conn_roots=_conn_roots, outer_vec=_outer_vec,
                              root_rot=_root_rot, pad_net=pad_net)
        clusters.append(cl)
    parts = _compose_clusters(clusters, conn_roots=_conn_roots,
                              outer_vec=_outer_vec)
    _MULTI_CACHE[sig] = [(p.bref, p.rot, p.ox, p.oy) for p in parts]
    return parts


def _solve_component(comp: set[str], members: set[str],
                     attractors: dict[str, list[_Attract]],
                     repulsors: dict[str, list[_Repel]],
                     resolvable: dict[str, Path],
                     conn_roots: set[str] | None = None,
                     outer_vec: tuple[float, float] | None = None,
                     root_rot: dict[str, float] | None = None,
                     pad_net: dict[tuple[str, str], str] | None = None
                     ) -> list[_Part]:
    members_c = comp & members
    roots_c = comp - members_c
    deps: dict[str, set[str]] = {p: set() for p in comp}
    for m in members_c:
        for a, _p, _b in attractors.get(m, []):
            if a in comp:
                deps[m].add(a)
        for rp, _pin, _mm in repulsors.get(m, []):
            if rp in comp:
                deps[m].add(rp)
        deps[m].discard(m)
    order = _topo_order(comp, deps)
    if order is None:
        raise ZoneInfeasible(
            f"contract graph: cyclic constraint graph over {sorted(comp)} — "
            f"no seat order exists")
    for scale in range(0, 24):
        placed = _seat_multi(order, roots_c, attractors, repulsors,
                             resolvable, scale * _RELAX_STEP,
                             conn_roots=(conn_roots or set()) & comp,
                             outer_vec=outer_vec, root_rot=root_rot,
                             pad_net=pad_net)
        if placed is None:
            continue
        parts = [placed[b] for b in order]
        if not _any_overlap(parts):
            return parts
    raise ZoneInfeasible(
        f"contract graph: component {sorted(comp)} found no collision-free "
        f"seat after the 24-scale widen — solver infeasible (no silent "
        f"fallback, no legacy pack)")


def _compose_clusters(clusters: list[list[_Part]],
                      conn_roots: set[str] | None = None,
                      outer_vec: tuple[float, float] | None = None
                      ) -> list[_Part]:
    along_y = outer_vec is not None and abs(outer_vec[0]) > abs(outer_vec[1])
    vx, vy = outer_vec if outer_vec is not None else (0.0, 0.0)
    out: list[_Part] = []
    cursor = 0.0
    prev_conn = False
    placed_clusters: list[list[_Part]] = []
    for cl in clusters:
        has_conn = bool(conn_roots and any(p.bref in conn_roots for p in cl))
        gap = _CONN_ROOT_CABLE_GAP if (prev_conn and has_conn) else _ROOT_GAP
        minx = min(p.local_box()[0] for p in cl)
        miny = min(p.local_box()[1] for p in cl)
        if along_y:
            height = max(p.local_box()[3] for p in cl) - miny
            moved = [_Part(p.bref, p.mod, p.rot, "top",
                           round(p.ox - minx, 4),
                           round(p.oy - miny + cursor, 4)) for p in cl]
            cursor += height + TEMPLATE_CLEAR + gap
        else:
            width = max(p.local_box()[2] for p in cl) - minx
            moved = [_Part(p.bref, p.mod, p.rot, "top",
                           round(p.ox - minx + cursor, 4),
                           round(p.oy - miny, 4)) for p in cl]
            cursor += width + TEMPLATE_CLEAR + gap
        placed_clusters.append(moved)
        prev_conn = has_conn
    if conn_roots and outer_vec is not None:
        def _face(cl: list[_Part]) -> float | None:
            fs = []
            for p in cl:
                if p.bref not in conn_roots:
                    continue
                sb = _rot_pad_bbox(p.mod, p.rot)
                fs.append(p.ox + sb[2] if vx > 0
                          else p.ox + sb[0] if vx < 0
                          else p.oy + sb[3] if vy > 0
                          else p.oy + sb[1])
            if not fs:
                return None
            return max(fs) if (vx > 0 or vy > 0) else min(fs)
        faces = [f for f in (_face(cl) for cl in placed_clusters)
                 if f is not None]
        if faces:
            target = max(faces) if (vx > 0 or vy > 0) else min(faces)
            for i, cl in enumerate(placed_clusters):
                f = _face(cl)
                if f is None:
                    continue
                d = round(target - f, 4)
                if d:
                    placed_clusters[i] = [
                        _Part(p.bref, p.mod, p.rot, "top",
                              round(p.ox + (d if vx else 0.0), 4),
                              round(p.oy + (d if vy else 0.0), 4))
                        for p in cl]
            inline = round(target + (_q.seat_slide() if (vx < 0 or vy < 0)
                                     else -_q.seat_slide()), 4)
            for i, cl in enumerate(placed_clusters):
                if _face(cl) is not None:
                    continue
                if vx > 0:
                    e = max(p.local_box()[2] for p in cl)
                    d = min(0.0, round(inline - e, 4))
                elif vx < 0:
                    e = min(p.local_box()[0] for p in cl)
                    d = max(0.0, round(inline - e, 4))
                elif vy > 0:
                    e = max(p.local_box()[3] for p in cl)
                    d = min(0.0, round(inline - e, 4))
                else:
                    e = min(p.local_box()[1] for p in cl)
                    d = max(0.0, round(inline - e, 4))
                if d:
                    placed_clusters[i] = [
                        _Part(p.bref, p.mod, p.rot, "top",
                              round(p.ox + (d if vx else 0.0), 4),
                              round(p.oy + (d if vy else 0.0), 4))
                        for p in cl]
    for cl in placed_clusters:
        out.extend(cl)
    return out


def _build_ldo_stage(ic_bref: str, resolvable: dict[str, Path],
                     cin: str, cin_pin: str, cout: str, cout_pin: str
                     ) -> list[_Part]:
    ic_mod = resolvable[ic_bref]
    for scale in range(0, 12):
        pad = scale * _RELAX_STEP
        ic = _Part(ic_bref, ic_mod, 0.0, "top", 0.0, 0.0)
        ib = ic.pad_boxes()
        parts = [ic]
        for cap, pin, sgn in ((cin, cin_pin, -1), (cout, cout_pin, +1)):
            mod = resolvable[cap]
            hx, _hy = _pad_half(mod)
            pb = ib[pin]
            cy = (pb[1] + pb[3]) / 2.0
            if sgn < 0:
                cx = pb[0] - _LDO_GAP - pad - hx
            else:
                cx = pb[2] + _LDO_GAP + pad + hx
            parts.append(_Part(cap, mod, 0.0, "top", round(cx, 4), round(cy, 4)))
        if not _any_overlap(parts):
            return parts
    return parts


def _any_overlap_py(boxes: list[tuple[float, float, float, float]]) -> bool:
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _boxes_overlap_py(boxes[i], boxes[j], TEMPLATE_CLEAR):
                return True
    return False


def _any_overlap(parts: list[_Part]) -> bool:
    boxes = [p.local_box() for p in parts]
    if not _nat.loaded():
        raise RuntimeError("native any_overlap required")
    got = _nat.module().any_boxes_overlap(boxes, TEMPLATE_CLEAR)
    if _nat.trace():
        ref = _any_overlap_py(boxes)
        if got is not ref:
            raise AssertionError(
                "native any_boxes_overlap DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _stage_extent_py(parts: list[_Part]) -> tuple[float, float, float, float]:
    xs0 = [p.local_box()[0] for p in parts]
    ys0 = [p.local_box()[1] for p in parts]
    xs1 = [p.local_box()[2] for p in parts]
    ys1 = [p.local_box()[3] for p in parts]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _stage_extent(parts: list[_Part]) -> tuple[float, float, float, float]:
    boxes = [p.local_box() for p in parts]
    if not _nat.loaded():
        raise RuntimeError("native stage_extent required")
    got = _nat.module().boxes_union(boxes)
    if got is None:
        raise ValueError("stage extent: no parts")
    hit = tuple(got)
    if _nat.trace():
        ref = _stage_extent_py(parts)
        if hit != ref:
            raise AssertionError(
                "native stage_extent DIVERGENCE: "
                f"cpp={hit} python={ref}")
    return hit


def contract_member_brefs(sheet_name: str, contract: dict,
                          resolvable: dict[str, Path]) -> set[str]:
    lib2board = _g._board_refs_by_sheet(sheet_name)
    libs: set[str] = set(contract.get("roles", {}))
    for st in contract.get("structures", []):
        for key in ("members", "caps"):
            libs.update(st.get(key) or [])
        for key in ("cap", "resistor", "inductor", "cin", "cout"):
            v = st.get(key)
            if isinstance(v, str):
                libs.add(v)
    out: set[str] = set()
    for lib in libs:
        b = lib2board.get(lib)
        if b is not None and b in resolvable:
            out.add(b)
    return out


def build_zone(sheet_name: str, contract: dict, refs: list[str],
               side_of: dict[str, str],
               bbox_of: dict[str, tuple[float, float, float, float]],
               resolvable: dict[str, Path],
               rot_out: dict[str, float] | None = None,
               facing: str | None = None,
               outer_dir: str | None = None
               ) -> tuple[dict[str, tuple[float, float]],
                          dict[str, tuple[float, float]],
                          float, float]:
    if contract is None:
        raise AssertionError(
            f"build_zone({sheet_name}): called without a contract — the hook "
            f"guards on load_contract; a None here is a programming error")
    rot_out = rot_out if rot_out is not None else {}
    _types = {st.get("type") for st in contract.get("structures", [])}
    if "hot_loop" not in _types:
        if "proximity" in _types:
            return _build_proximity_zone(
                sheet_name, contract, refs, side_of, bbox_of, resolvable,
                rot_out, facing=facing, outer_dir=outer_dir)
        raise ZoneInfeasible(
            f"{sheet_name}: contract has no hot_loop/proximity structure the "
            f"template engine supports (types: "
            f"{sorted(t for t in _types if t)}) — author a supported "
            f"structure; there is no legacy pack")

    lib2board = _g._board_refs_by_sheet(sheet_name)
    board_set = set(refs)

    def bref(lib: str) -> str | None:
        b = lib2board.get(lib)
        return b if (b is not None and b in board_set and b in resolvable) else None

    roles = contract.get("roles", {})
    structs = contract.get("structures", [])
    order = contract.get("stage_order", [])

    def _find(typ: str, ic: str) -> dict | None:
        for st in structs:
            if st.get("type") == typ and st.get("ic") == ic:
                return st
        return None

    def _buck_pins(ic: str) -> dict[str, str]:
        hl = _find("hot_loop", ic)
        sw = _find("sw_node", ic)
        fb = _find("fb_cluster", ic)
        boot = _find("boot", ic)
        vcc = _find("vcc_cap", ic)
        bias = _find("bias_cap", ic)
        rt = _find("rt_r", ic)
        bo = _find("bulk_out", ic)
        return {
            "vin1": hl["pin_pairs"][0][0], "pgnd1": hl["pin_pairs"][0][1],
            "vin2": hl["pin_pairs"][1][0], "pgnd2": hl["pin_pairs"][1][1],
            "sw": sw["sw_pin"], "fb": fb["fb_pin"],
            "rboot": boot["pins"][0], "cboot": boot["pins"][1],
            "vcc": vcc["pin"], "bias": bias["pin"], "rt": rt["pin"],
            "ind_out": bo["inductor_out_pin"] if bo else "2",
        }

    bias_r_libs = [k for k, v in roles.items() if v == "bias_r"]
    bias_r_iter = iter(bias_r_libs)

    stages: list[list[_Part]] = []
    stage_kind: list[str] = []
    for ic in order:
        ic_b = bref(ic)
        if ic_b is None:
            raise ZoneInfeasible(
                f"{sheet_name}: stage_order IC {ic!r} does not resolve on "
                f"this sheet — unplaceable contract")
        role = roles.get(ic, "")
        if role == "buck_ic":
            hl = _find("hot_loop", ic)
            bulk = _find("bulk_in", ic)
            bulk_o = _find("bulk_out", ic)
            sw = _find("sw_node", ic)
            fb = _find("fb_cluster", ic)
            boot = _find("boot", ic)
            vcc = _find("vcc_cap", ic)
            bias = _find("bias_cap", ic)
            rt = _find("rt_r", ic)
            hf = [bref(c) for c in hl["caps"]]
            bulk_c = [bref(c) for c in bulk["caps"]]
            out_c = [bref(c) for c in bulk_o["caps"]] if bulk_o else []
            ind = bref(sw["inductor"])
            fbm = [bref(m) for m in fb["members"]]
            boot_c = bref(boot["cap"])
            vcc_c = bref(vcc["cap"])
            bias_r_lib = next(bias_r_iter, None)
            bias_r_b = bref(bias_r_lib) if bias_r_lib else None
            bias_c = bref(bias["cap"])
            rt_b = bref(rt["resistor"])
            need = hf + bulk_c + out_c + [ind, boot_c, vcc_c, bias_r_b, bias_c,
                                          rt_b] + fbm
            if any(x is None for x in need):
                raise ZoneInfeasible(
                    f"{sheet_name}: buck stage {ic!r} has unresolvable "
                    f"member ref(s) — unplaceable contract")
            pins = _buck_pins(ic)
            parts = _build_buck_stage(
                ic_b, roles, resolvable, hf, bulk_c, out_c, ind, fbm,
                boot_c, vcc_c, bias_r_b, bias_c, rt_b, pins)
            stages.append(parts)
            stage_kind.append("buck")
        elif role == "ldo_ic":
            ldo = _find("ldo_stage", ic)
            cin, cout = bref(ldo["cin"]), bref(ldo["cout"])
            if cin is None or cout is None:
                raise ZoneInfeasible(
                    f"{sheet_name}: ldo stage {ic!r} cin/cout do not resolve "
                    f"on this sheet — unplaceable contract")
            parts = _build_ldo_stage(ic_b, resolvable, cin, ldo["cin_pin"],
                                     cout, ldo["cout_pin"])
            stages.append(parts)
            stage_kind.append("ldo")
        else:
            raise ZoneInfeasible(
                f"{sheet_name}: stage_order IC {ic!r} has unsupported role "
                f"{role!r} (not buck_ic/ldo_ic) — no legacy pack")

    _stage_of = {p.bref: si for si, sp in enumerate(stages) for p in sp}
    _bound_of: dict[str, float] = {}
    _att_of: dict[str, list] = {}
    _rep_of: dict[str, list] = {}
    for st in structs:
        _t = st.get("type")
        if _t == "proximity":
            _a = bref(st.get("anchor", ""))
            _mm = float(st.get("max_mm", 0.0) or 0.0)
            if _a is None or _mm <= 0.0:
                continue
            _ap = st.get("anchor_pins")
            for _ml in st.get("members", []):
                _mb = bref(_ml)
                if _mb is not None and _mm < _bound_of.get(_mb, 1e9):
                    _bound_of[_mb] = _mm
                    _att_of[_mb] = [(_a, tuple(_ap) if _ap else None, _mm)]
                    _rep_of[_mb] = []
            continue
        _spec = {"fb_cluster": ("members", "fb_pin", "max_to_fb_mm"),
                 "rt_r": ("resistor", "pin", "max_pad_to_pin_mm"),
                 "bias_cap": ("cap", "pin", "max_pad_to_pin_mm"),
                 "boot": ("cap", "pins", "max_pad_to_pin_mm"),
                 "vcc_cap": ("cap", "pin", "max_pad_to_pin_mm")}.get(_t)
        if _spec is None:
            continue
        _mk, _pk, _bk = _spec
        _ic = bref(st.get("ic", ""))
        _mm = float(st.get(_bk, 0.0) or 0.0)
        if _ic is None or _mm <= 0.0:
            continue
        _pins = st.get(_pk)
        _pins = tuple(_pins) if isinstance(_pins, list) else (_pins,)
        _mls = st.get(_mk)
        _mls = _mls if isinstance(_mls, list) else [_mls]
        _rep = []
        if _t == "fb_cluster":
            _msw = float(st.get("min_to_own_sw_mm", 0.0) or 0.0)
            if _msw > 0.0:
                if st.get("own_sw_pin"):
                    _rep.append((_ic, st["own_sw_pin"], _msw))
                _ol = bref(st.get("own_inductor", ""))
                if _ol is not None:
                    _rep.append((_ol, None, _msw))
        for _ml in _mls:
            _mb = bref(_ml)
            if _mb is not None and _mm < _bound_of.get(_mb, 1e9):
                _bound_of[_mb] = _mm
                _att_of[_mb] = [(_ic, _pins, _mm)]
                _rep_of[_mb] = _rep

    _pad_net = _sheet_pad_nets(sheet_name)

    def _try_place(mb, att, frame, rep=()):
        rep = [r for r in rep if r[0] in frame]
        for wpad in (0.0, 0.5, 1.0):
            cands = _gcandidates(mb, resolvable[mb], att, list(rep), frame,
                                 wpad, pad_net=_pad_net)
            if cands:
                return cands[0]
        return None

    for st in structs:
        if st.get("type") != "proximity":
            continue
        ab = bref(st.get("anchor", ""))
        si = _stage_of.get(ab)
        bound = float(st.get("max_mm", 0.0) or 0.0)
        if si is None:
            raise ZoneInfeasible(
                f"{sheet_name}: proximity anchor {st.get('anchor')!r} is not "
                f"a placed stage part — the structure would go silently "
                f"unenforced; anchor it on a stage IC/member")
        if bound <= 0.0:
            raise ZoneInfeasible(
                f"{sheet_name}: proximity at {st.get('anchor')!r} has no "
                f"positive max_mm — malformed structure")
        apins = st.get("anchor_pins")
        att = [(ab, tuple(apins) if apins else None, bound)]
        for mlib in st.get("members", []):
            mb = bref(mlib)
            if mb is None or mb not in resolvable:
                raise ZoneInfeasible(
                    f"{sheet_name}: proximity member {mlib!r} does not "
                    f"resolve on this sheet — unplaceable contract")
            if mb in _stage_of:
                continue
            frame = {p.bref: p for p in stages[si]}
            got = _try_place(mb, att, frame)
            if got is None:
                ring = [r for r in frame
                        if r != ab and _bound_of.get(r, 0.0) >= bound
                        and r in _att_of
                        and len(_g._pad_boxes(frame[r].mod, 0.0)) <= 2]
                ring.sort(key=lambda r: (-_bound_of[r], r))
                for victim in ring:
                    f2 = dict(frame)
                    f2.pop(victim)
                    got2 = _try_place(mb, att, f2)
                    if got2 is None:
                        continue
                    f2[mb] = got2
                    back = _try_place(victim, _att_of[victim], f2,
                                      _rep_of.get(victim, ()))
                    if back is None:
                        continue
                    stages[si] = [*(p for p in stages[si]
                                    if p.bref != victim), got2, back]
                    _stage_of[mb] = si
                    got = got2
                    break
                if got is None:
                    raise ZoneInfeasible(
                        f"{sheet_name}: proximity member {mb} found no seat "
                        f"within {bound} mm of {ab} even after bound-priority "
                        f"displacement — solver infeasible (a silent drop to "
                        f"the leftover pack is outlawed)")
            else:
                stages[si] = [*stages[si], got]
                _stage_of[mb] = si

    def _has_sw(si: int) -> bool:
        return stage_kind[si] == "buck"

    def _mirror_stage(parts: list[_Part]) -> list[_Part]:
        ext = _stage_extent(parts)
        sp: list[_Part] = []
        for p in parts:
            nrot = (p.rot + 180.0) % 360.0
            nb = _g._pad_boxes(p.mod, nrot)
            ob = _g._pad_boxes(p.mod, p.rot)
            ocx = p.ox + (min(b[0] for b in ob.values())
                          + max(b[2] for b in ob.values())) / 2.0
            ocy = p.oy + (min(b[1] for b in ob.values())
                          + max(b[3] for b in ob.values())) / 2.0
            ecx = (ext[0] + ext[2]) / 2.0
            ecy = (ext[1] + ext[3]) / 2.0
            ncx = 2 * ecx - ocx
            ncy = 2 * ecy - ocy
            nhx = (min(b[0] for b in nb.values())
                   + max(b[2] for b in nb.values())) / 2.0
            nhy = (min(b[1] for b in nb.values())
                   + max(b[3] for b in nb.values())) / 2.0
            sp.append(_Part(p.bref, p.mod, nrot, p.side,
                            round(ncx - nhx, 4), round(ncy - nhy, 4)))
        return sp

    def _lay(layout: list[list[int]], mirror: set[int]) -> dict[str, _Part]:
        frames = [
            _mirror_stage(stages[si]) if si in mirror
            else [_Part(p.bref, p.mod, p.rot, p.side, p.ox, p.oy)
                  for p in stages[si]]
            for si in range(len(stages))]
        abs_parts: dict[str, _Part] = {}
        y_base = ZONE_PAD
        for ri, row in enumerate(layout):
            row_min_y = min(_stage_extent(frames[si])[1] for si in row)
            dy = y_base - row_min_y
            x = ZONE_PAD
            row_bottom = y_base
            for k, si in enumerate(row):
                sp = frames[si]
                ext = _stage_extent(sp)
                dx = x - ext[0]
                for p in sp:
                    abs_parts[p.bref] = _Part(p.bref, p.mod, p.rot, p.side,
                                              round(p.ox + dx, 4),
                                              round(p.oy + dy, 4))
                row_bottom = max(row_bottom, ext[3] + dy)
                if k + 1 < len(row):
                    nxt = row[k + 1]
                    gap = (_INTERSTAGE_GAP0 if (_has_sw(si) and _has_sw(nxt))
                           else _NONSW_STAGE_GAP)
                    x = ext[2] + dx + gap
            row_gap = TEMPLATE_CLEAR
            if ri + 1 < len(layout):
                nxt_row = layout[ri + 1]
                if (any(_has_sw(si) for si in row)
                        and any(_has_sw(si) for si in nxt_row)):
                    row_gap = _INTERROW_BUCK_GAP
            y_base = row_bottom + row_gap
        return abs_parts

    def _width(placed: dict[str, _Part]) -> float:
        return _row_extent(placed)[0]

    min_foreign = _foreign_sw_bound(structs)

    def _ok(placed: dict[str, _Part]) -> bool:
        return _foreign_ok(placed, contract, lib2board, board_set, resolvable,
                           min_foreign)

    bucks = [si for si in range(len(stages)) if stage_kind[si] == "buck"]
    others = [si for si in range(len(stages)) if stage_kind[si] != "buck"]
    seq = list(range(len(stages)))
    candidates: list[tuple[list[list[int]], set[int]]] = []
    candidates.append(([seq], {bucks[1]} if len(bucks) >= 2 else set()))
    if bucks and others:
        candidates.append(
            ([bucks, others], {bucks[1]} if len(bucks) >= 2 else set()))
    if len(bucks) >= 2:
        rows2 = [[b] for b in bucks[:-1]] + [[bucks[-1], *others]]
        candidates.append((rows2, set()))
    candidates.append(([[si] for si in seq], set()))

    scored = []
    for ci, (layout, mirror) in enumerate(candidates):
        cand = _lay(layout, mirror)
        w = _width(cand)
        if w <= _ROW_WIDTH_BUDGET and _ok(cand):
            scored.append((round(w, 4), len(layout), ci, cand))
    if scored:
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        placed_abs = scored[0][3]
    else:
        ok_cands = [_lay(la, mi) for la, mi in candidates]
        valid = [c for c in ok_cands if _ok(c)]
        placed_abs = (min(valid, key=_width) if valid
                      else min(ok_cands, key=_width))

    out_libs = [k for k, v in roles.items()
                if v in set(contract.get("external", {}).get(
                    "output_roles", ["cout_bulk"]))]
    out_brefs = {b for b in (bref(x) for x in out_libs) if b is not None}
    placed_abs = _apply_facing(placed_abs, out_brefs, facing)

    stage_refs = set(placed_abs)
    leftovers = [r for r in refs if r not in stage_refs]
    blockers = [pp.local_box() for pp in placed_abs.values()]
    row_bottom = max((b[3] for b in blockers), default=ZONE_PAD)

    top_off: dict[str, tuple[float, float]] = {}
    bot_off: dict[str, tuple[float, float]] = {}
    for p in placed_abs.values():
        top_off[p.bref] = (p.ox, p.oy)
        if abs(p.rot) > 1e-6 and p.mod.stem not in CONN_MATING_FACE:
            rot_out[p.bref] = p.rot % 360.0

    zw, zh = _row_extent(placed_abs)

    if leftovers:
        lt = [r for r in leftovers if side_of.get(r, "top") == "top"]
        lb = [r for r in leftovers if side_of.get(r, "top") == "bottom"]
        target_w = max(zw - 2 * ZONE_PAD, 8.0)
        band_top = row_bottom + _LEFTOVER_BAND_GAP
        t_lo, t_w, t_h, b_lo, b_w, b_h = _pack_leftover_bands(
            lt, lb, target_w, bbox_of, resolvable)
        for r, (dx, dy) in t_lo.items():
            top_off[r] = (round(dx, 4), round(dy + band_top - ZONE_PAD, 4))
        for r, (dx, dy) in b_lo.items():
            bot_off[r] = (round(dx, 4), round(dy + band_top - ZONE_PAD, 4))
        zw = round(max(zw, t_w, b_w), 4)
        zh = round(max(zh, band_top - ZONE_PAD + t_h, band_top - ZONE_PAD + b_h),
                   4)

    return top_off, bot_off, round(zw, 4), round(zh, 4)


def _build_proximity_zone(sheet_name: str, contract: dict, refs: list[str],
                          side_of: dict[str, str],
                          bbox_of: dict[str, tuple[float, float, float, float]],
                          resolvable: dict[str, Path],
                          rot_out: dict[str, float],
                          facing: str | None = None,
                          outer_dir: str | None = None
                          ) -> tuple[dict[str, tuple[float, float]],
                                     dict[str, tuple[float, float]],
                                     float, float]:
    lib2board = _g._board_refs_by_sheet(sheet_name)
    board_set = set(refs)
    bref_of = {lib: b for lib, b in lib2board.items()
               if b in board_set and b in resolvable}

    anchor_lib: str | None = None
    for st in contract.get("structures", []):
        if st.get("type") == "same_side" and st.get("ics"):
            anchor_lib = st["ics"][0]
            break
    if anchor_lib is None:
        for st in contract.get("structures", []):
            if st.get("type") == "proximity":
                anchor_lib = st.get("anchor")
                break
    anchor_bref = bref_of.get(anchor_lib or "")
    if anchor_bref is None:
        raise ZoneInfeasible(
            f"{sheet_name}: proximity contract has no resolvable anchor "
            f"({anchor_lib!r}) — unplaceable contract")

    if sheet_name in _PILOT_PROX_SHEETS and _is_single_anchor_star(contract, bref_of):
        parts = _build_proximity_cluster(anchor_bref, contract, bref_of, resolvable)
    else:
        parts = _solve_contract(contract, bref_of, resolvable,
                                outer_dir=outer_dir, sheet_name=sheet_name,
                                pad_net=_sheet_pad_nets(sheet_name))

    minx = min(b[0] for p in parts for b in p.pad_boxes().values())
    miny = min(b[1] for p in parts for b in p.pad_boxes().values())
    dx, dy = ZONE_PAD - minx, ZONE_PAD - miny
    placed_abs = {p.bref: _Part(p.bref, p.mod, p.rot, p.side,
                                round(p.ox + dx, 4), round(p.oy + dy, 4))
                  for p in parts}

    media_brefs: set[str] = set()
    for st in contract.get("structures", []):
        if st.get("type") != "proximity" or not st.get("anchor_pins"):
            continue
        if bref_of.get(st.get("anchor", "")) != anchor_bref:
            continue
        for mlib in st.get("members", []):
            mb = bref_of.get(mlib)
            if mb is not None:
                media_brefs.add(mb)
    placed_abs = _apply_media_facing(placed_abs, media_brefs, facing)

    top_off: dict[str, tuple[float, float]] = {}
    bot_off: dict[str, tuple[float, float]] = {}
    for p in placed_abs.values():
        top_off[p.bref] = (p.ox, p.oy)
        if abs(p.rot) > 1e-6 and p.mod.stem not in CONN_MATING_FACE:
            rot_out[p.bref] = p.rot % 360.0

    zw, zh = _row_extent(placed_abs)
    row_bottom = max((pp.local_box()[3] for pp in placed_abs.values()),
                     default=ZONE_PAD)
    _gx = _gy = 0.0

    leftovers = [r for r in refs if r not in placed_abs]
    if leftovers:
        lt = [r for r in leftovers if side_of.get(r, "top") == "top"]
        lb = [r for r in leftovers if side_of.get(r, "top") == "bottom"]
        _in = {"S": (0.0, -1.0)}.get(outer_dir or "N", (0.0, 1.0))
        target_w = max(zw - 2 * ZONE_PAD, 8.0)
        _conn_lo, _conn_hi = [], []
        if outer_dir:
            for pp in placed_abs.values():
                if pp.mod.stem in CONN_MATING_FACE:
                    bb = pp.local_box()
                    _cn = _q.quant_credit(intelligent_need(
                        len(_g._pad_boxes(pp.mod, 0.0)))[0])
                    _conn_lo.append(bb[1] - _cn)
                    _conn_hi.append(bb[3] + _cn)
        t_lo, t_w, t_h, b_lo, b_w, b_h = _pack_leftover_bands(
            lt, lb, target_w, bbox_of, resolvable)
        row_top = min((pp.local_box()[1] for pp in placed_abs.values()),
                      default=ZONE_PAD)
        if _in == (0.0, 1.0):
            floor_y = max([row_bottom] + _conn_hi)
            bx, by = 0.0, floor_y + _LEFTOVER_BAND_GAP - ZONE_PAD
        else:
            bh_all = max(t_h, b_h)
            ceil_y = min([row_top] + _conn_lo)
            bx, by = 0.0, ceil_y - _LEFTOVER_BAND_GAP - bh_all - ZONE_PAD
        if outer_dir == "W":
            _pf0 = [pp.ox + _rot_pad_bbox(pp.mod, pp.rot)[0]
                    for pp in placed_abs.values()
                    if pp.mod.stem in CONN_MATING_FACE]
            if _pf0:
                bx = min(_pf0) + _q.seat_slide()
        for r, (ox, oy) in t_lo.items():
            top_off[r] = (round(ox + bx, 4), round(oy + by, 4))
        for r, (ox, oy) in b_lo.items():
            bot_off[r] = (round(ox + bx, 4), round(oy + by, 4))
        allx = [v[0] for v in top_off.values()] + [v[0] for v in bot_off.values()]
        ally = [v[1] for v in top_off.values()] + [v[1] for v in bot_off.values()]
        sx = ZONE_PAD - min(allx) if min(allx) < ZONE_PAD else 0.0
        sy = ZONE_PAD - min(ally) if min(ally) < ZONE_PAD else 0.0
        if sx or sy:
            _gx, _gy = sx, sy
            top_off = {r: (round(x + sx, 4), round(y + sy, 4))
                       for r, (x, y) in top_off.items()}
            bot_off = {r: (round(x + sx, 4), round(y + sy, 4))
                       for r, (x, y) in bot_off.items()}
        ext_x = [pp.local_box()[2] + sx for pp in placed_abs.values()]
        ext_y = [pp.local_box()[3] + sy for pp in placed_abs.values()]
        if t_lo or b_lo:
            ext_x += [bx + sx + t_w, bx + sx + b_w]
            ext_y += [by + sy + t_h, by + sy + b_h]
        zw = round(max(ext_x) + ZONE_PAD, 4)
        zh = round(max(ext_y) + ZONE_PAD, 4)

    _connp = [pp for pp in placed_abs.values()
              if pp.mod.stem in CONN_MATING_FACE]
    if outer_dir and _connp:
        vx, vy = _OVEC[outer_dir]

        def _pface(pp: _Part) -> float:
            sb = _rot_pad_bbox(pp.mod, pp.rot)
            return (pp.ox + sb[2] + _gx if vx > 0
                    else pp.ox + sb[0] + _gx if vx < 0
                    else pp.oy + sb[3] + _gy if vy > 0
                    else pp.oy + sb[1] + _gy)

        faces = [_pface(pp) for pp in _connp]
        if vx > 0:
            zw = max(faces) + EDGE_PAD_CLEAR
        elif vy > 0:
            zh = max(faces) + EDGE_PAD_CLEAR
        else:
            d = EDGE_PAD_CLEAR - min(faces)
            if vx < 0:
                top_off = {r: (round(x + d, 4), y)
                           for r, (x, y) in top_off.items()}
                bot_off = {r: (round(x + d, 4), y)
                           for r, (x, y) in bot_off.items()}
                zw += d
            else:
                top_off = {r: (x, round(y + d, 4))
                           for r, (x, y) in top_off.items()}
                bot_off = {r: (x, round(y + d, 4))
                           for r, (x, y) in bot_off.items()}
                zh += d

    return top_off, bot_off, round(zw, 4), round(zh, 4)


def _pack_leftover_bands(lt: list[str], lb: list[str], target_w: float,
                         bbox_of: dict[str, tuple[float, float, float, float]],
                         resolvable: dict[str, Path]
                         ) -> tuple[dict, float, float, dict, float, float]:
    t_items = [(r, bbox_of[r], 0.0) for r in lt]
    t_lo, t_w, t_h = _shelf_pack(t_items, target_w)
    blockers = []
    for r in lt:
        if r in resolvable and _has_thru_pads(resolvable[r]):
            ox, oy = t_lo[r]
            bx0, by0, bx1, by1 = bbox_of[r]
            blockers.append((ox + bx0 - TEMPLATE_CLEAR / 2,
                             oy + by0 - TEMPLATE_CLEAR / 2,
                             ox + bx1 + TEMPLATE_CLEAR / 2,
                             oy + by1 + TEMPLATE_CLEAR / 2))
    b_items = [(r, bbox_of[r], 0.0) for r in lb]
    b_lo, b_w, b_h = _shelf_pack(b_items, target_w, blockers)
    return t_lo, t_w, t_h, b_lo, b_w, b_h


def _buck_index(stage_i: int, stage_kind: list[str]) -> int:
    return sum(1 for k in stage_kind[:stage_i] if k == "buck")


def _foreign_sw_bound(structs: list[dict]) -> float:
    for st in structs:
        if st.get("type") == "fb_cluster":
            return float(st.get("min_to_foreign_sw_mm", 5.0))
    return 5.0


def _foreign_ok(placed: dict[str, _Part], contract: dict,
                lib2board: dict[str, str], board_set: set[str],
                resolvable: dict[str, Path], min_foreign: float) -> bool:
    def b(lib: str | None) -> str | None:
        x = lib2board.get(lib) if lib else None
        return x if x in placed else None
    for st in contract.get("structures", []):
        if st.get("type") != "fb_cluster":
            continue
        if "foreign_ic" not in st:
            continue
        for_ic = b(st["foreign_ic"])
        for_l = b(st.get("foreign_inductor"))
        if for_ic is None:
            continue
        for_boxes = placed[for_ic].pad_boxes()
        sw_box = for_boxes.get(st["foreign_sw_pin"])
        l_boxes = placed[for_l].pad_boxes() if for_l else {}
        for m in st["members"]:
            mb = b(m)
            if mb is None:
                continue
            for pb in placed[mb].pad_boxes().values():
                if sw_box is not None and _g._box_gap(pb, sw_box) < min_foreign:
                    return False
                for lb in l_boxes.values():
                    if _g._box_gap(pb, lb) < min_foreign:
                        return False
    return True


def _row_extent_py(placed: dict[str, _Part]) -> tuple[float, float]:
    allb = [pp.local_box() for pp in placed.values()]
    zw = round(max(b[2] for b in allb) + ZONE_PAD, 4)
    zh = round(max(b[3] for b in allb) + ZONE_PAD, 4)
    return zw, zh


def _row_extent(placed: dict[str, _Part]) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native row_extent required")
    allb = [pp.local_box() for pp in placed.values()]
    got = tuple(_nat.module().row_extent(allb, ZONE_PAD))
    if _nat.trace():
        ref = _row_extent_py(placed)
        if got != ref:
            raise AssertionError(
                "native row_extent DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


_FACING_VEC: dict[str, tuple[float, float]] = {
    "N": (0.0, -1.0), "S": (0.0, 1.0), "W": (-1.0, 0.0), "E": (1.0, 0.0),
}


def _pad_center_py(p: _Part) -> tuple[float, float]:
    b = p.pad_boxes().values()
    xs = [x for bb in b for x in (bb[0], bb[2])]
    ys = [y for bb in b for y in (bb[1], bb[3])]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _pad_center(p: _Part) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native boxes_center required")
    got = tuple(_nat.module().boxes_center(list(p.pad_boxes().values())))
    if _nat.trace():
        ref = _pad_center_py(p)
        if got != ref:
            raise AssertionError(
                "native boxes_center DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _centroid_py(pts: list[tuple[float, float]]) -> tuple[float, float]:
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def _centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    if not _nat.loaded():
        raise RuntimeError("native points_centroid required")
    got = tuple(_nat.module().points_centroid(pts))
    if _nat.trace():
        ref = _centroid_py(pts)
        if got != ref:
            raise AssertionError(
                "native points_centroid DIVERGENCE: "
                f"cpp={got} python={ref}")
    return got


def _turn_zone_180(placed: dict[str, _Part]) -> dict[str, _Part]:
    if not _nat.loaded():
        raise RuntimeError("native turn_origin_180 required")
    allpts: list[tuple[float, float]] = []
    for p in placed.values():
        for bb in p.pad_boxes().values():
            allpts.append((bb[0], bb[1]))
            allpts.append((bb[2], bb[3]))
    ecx, ecy = _nat.module().aabb_center(allpts)
    out: dict[str, _Part] = {}
    for ref, p in placed.items():
        nrot = (p.rot + 180.0) % 360.0
        ob = _g._pad_boxes(p.mod, p.rot)
        nb = _g._pad_boxes(p.mod, nrot)
        ocx, ocy = _nat.module().boxes_span_center(list(ob.values()))
        ocx += p.ox
        ocy += p.oy
        nhx, nhy = _nat.module().boxes_span_center(list(nb.values()))
        nox, noy = _nat.module().turn_origin_180(
            ecx, ecy, ocx, ocy, nhx, nhy, 4)
        out[ref] = _Part(ref, p.mod, nrot, p.side, nox, noy)
    minx = min(bb[0] for p in out.values() for bb in p.pad_boxes().values())
    miny = min(bb[1] for p in out.values() for bb in p.pad_boxes().values())
    dx, dy = ZONE_PAD - minx, ZONE_PAD - miny
    return {ref: _Part(ref, p.mod, p.rot, p.side,
                       round(p.ox + dx, 4), round(p.oy + dy, 4))
            for ref, p in out.items()}


def _apply_facing(placed: dict[str, _Part], out_brefs: set[str],
                  facing: str | None) -> dict[str, _Part]:
    fv = _FACING_VEC.get((facing or "").upper())
    if fv is None or not out_brefs:
        return placed
    present = [r for r in out_brefs if r in placed]
    if not present:
        return placed

    def _dot(pl: dict[str, _Part]) -> float:
        zc = _centroid([_pad_center(p) for p in pl.values()])
        oc = _centroid([_pad_center(pl[r]) for r in present])
        return _nat.module().facing_align_dot(
            zc[0], zc[1], oc[0], oc[1], fv[0], fv[1])

    if _dot(placed) > 0.0:
        return placed
    turned = _turn_zone_180(placed)
    return turned if _dot(turned) > _dot(placed) else placed


def _sheet_cross_mst(sheet_name: str,
                     own_xy: dict[str, tuple[float, float]],
                     own_rot: dict[str, float],
                     resolvable: dict[str, Path],
                     net_pins: dict[str, list[tuple[str, str]]],
                     foreign_pts: dict[str, list[tuple[float, float, str]]]
                     ) -> float:
    from schgen.generate.ratsnest import _mst_edges
    total = 0.0
    for net in sorted(foreign_pts):
        pts = [(x, y, "", s) for x, y, s in foreign_pts[net]]
        for r, pn in net_pins.get(net, ()):
            if r not in own_xy or r not in resolvable:
                continue
            bb = _g._pad_boxes(resolvable[r],
                               own_rot.get(r, 0.0) % 360.0).get(pn)
            if bb is None:
                continue
            pts.append((round(own_xy[r][0] + (bb[0] + bb[2]) / 2.0, 3),
                        round(own_xy[r][1] + (bb[1] + bb[3]) / 2.0, 3),
                        r, sheet_name))
        for a, b in _mst_edges(pts):
            if pts[a][3] != pts[b][3]:
                total += _nat.module().hypot_xy(
                    pts[a][0], pts[a][1], pts[b][0], pts[b][1])
    return total


def refit_facing(sheet_name: str, contract: dict,
                 parts_xy: dict[str, tuple[float, float]],
                 rots_now: dict[str, float],
                 resolvable: dict[str, Path],
                 down_centroid: tuple[float, float],
                 net_pins: dict[str, list[tuple[str, str]]],
                 foreign_pts: dict[str, list[tuple[float, float, str]]]
                 ) -> dict[str, tuple[float, float, float]] | None:
    roles = contract.get("roles", {})
    out_libs = [k for k, v in roles.items()
                if v in set(contract.get("external", {}).get(
                    "output_roles", ["cout_bulk"]))]
    lib2board = _g._board_refs_by_sheet(sheet_name)
    out_brefs = {lib2board.get(x) for x in out_libs} - {None}
    present = sorted(r for r in out_brefs if r in parts_xy)
    if not present:
        return None
    if any(r not in resolvable for r in parts_xy):
        return None
    placed = {r: _Part(r, resolvable[r], rots_now.get(r, 0.0) % 360.0,
                       "top", x, y)
              for r, (x, y) in parts_xy.items()}

    def _gate_dot(xy: dict[str, tuple[float, float]]) -> float:
        zc = _nat.module().points_centroid(list(xy.values()))
        oc = _nat.module().points_centroid([xy[r] for r in present])
        return _nat.module().facing_align_dot(
            zc[0], zc[1], oc[0], oc[1],
            down_centroid[0] - zc[0], down_centroid[1] - zc[1])

    allpts: list[tuple[float, float]] = []
    for p in placed.values():
        for bb in p.pad_boxes().values():
            allpts.append((bb[0], bb[1]))
            allpts.append((bb[2], bb[3]))
    ecx, ecy = _nat.module().aabb_center(allpts)
    turned: dict[str, tuple[float, float, float]] = {}
    for r, p in placed.items():
        nrot = (p.rot + 180.0) % 360.0
        ob = _g._pad_boxes(p.mod, p.rot)
        nb = _g._pad_boxes(p.mod, nrot)
        ocx, ocy = _nat.module().boxes_span_center(list(ob.values()))
        ocx += p.ox
        ocy += p.oy
        nhx, nhy = _nat.module().boxes_span_center(list(nb.values()))
        nox, noy = _nat.module().turn_origin_180(
            ecx, ecy, ocx, ocy, nhx, nhy, 4)
        turned[r] = (nox, noy, nrot)
    turned_xy = {r: (t[0], t[1]) for r, t in turned.items()}
    gate_now = _gate_dot(parts_xy) > 0.0
    gate_turned = _gate_dot(turned_xy) > 0.0
    if gate_now and not gate_turned:
        return None
    if not gate_now and gate_turned:
        return turned
    air_now = _sheet_cross_mst(sheet_name, parts_xy, rots_now, resolvable,
                               net_pins, foreign_pts)
    air_turned = _sheet_cross_mst(
        sheet_name, turned_xy, {r: t[2] for r, t in turned.items()},
        resolvable, net_pins, foreign_pts)
    return turned if air_turned < air_now - 1e-6 else None


def _turn_zone_quadrant(placed: dict[str, _Part], deg: float
                        ) -> dict[str, _Part]:
    deg = deg % 360.0
    if abs(deg) < 1e-6:
        return placed
    if not _nat.loaded():
        raise RuntimeError("native rotate_origin required")
    allpts: list[tuple[float, float]] = []
    for p in placed.values():
        for bb in p.pad_boxes().values():
            allpts.append((bb[0], bb[1]))
            allpts.append((bb[2], bb[3]))
    ecx, ecy = _nat.module().aabb_center(allpts)
    out: dict[str, _Part] = {}
    for ref, p in placed.items():
        nrot = (p.rot + deg) % 360.0
        ob = _g._pad_boxes(p.mod, p.rot)
        nb = _g._pad_boxes(p.mod, nrot)
        ocx, ocy = _nat.module().boxes_span_center(list(ob.values()))
        ocx += p.ox
        ocy += p.oy
        nhx, nhy = _nat.module().boxes_span_center(list(nb.values()))
        nox, noy = _nat.module().rotate_origin(
            ecx, ecy, ocx, ocy, nhx, nhy, deg, 4)
        out[ref] = _Part(ref, p.mod, nrot, p.side, nox, noy)
    minx = min(bb[0] for p in out.values() for bb in p.pad_boxes().values())
    miny = min(bb[1] for p in out.values() for bb in p.pad_boxes().values())
    dx, dy = ZONE_PAD - minx, ZONE_PAD - miny
    return {ref: _Part(ref, p.mod, p.rot, p.side,
                       round(p.ox + dx, 4), round(p.oy + dy, 4))
            for ref, p in out.items()}


def _apply_media_facing(placed: dict[str, _Part], media_brefs: set[str],
                        facing: str | None) -> dict[str, _Part]:
    fv = _FACING_VEC.get((facing or "").upper())
    if fv is None or not media_brefs:
        return placed
    present = [r for r in media_brefs if r in placed]
    if not present:
        return placed

    def _dot(pl: dict[str, _Part]) -> float:
        zc = _centroid([_pad_center(p) for p in pl.values()])
        mc = _centroid([_pad_center(pl[r]) for r in present])
        return _nat.module().facing_align_dot(
            zc[0], zc[1], mc[0], mc[1], fv[0], fv[1])

    best = placed
    best_dot = _dot(placed)
    best_turn = 0.0
    for deg in (90.0, 180.0, 270.0):
        cand = _turn_zone_quadrant(placed, deg)
        d = _dot(cand)
        if d > best_dot + 1e-6:
            best, best_dot, best_turn = cand, d, deg
    _ = best_turn
    return best
