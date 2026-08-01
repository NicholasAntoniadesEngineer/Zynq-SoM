from __future__ import annotations

from dataclasses import dataclass
from math import hypot, pi
from pathlib import Path

from schgen.core import quantize as _q
from schgen.verify.fanout_gate import (
    _is_cluster_passive,
    _rect_gap,
    counts_as_crowder,
    intelligent_need,
    is_testpoint_ref,
)

from .constants import (
    BOARD_EDGE_MARGIN,
    ORIGIN_X,
    ORIGIN_Y,
    PLACE_CLEAR,
    SOM_ZONE_GROW,
)
from .footprint import has_thru_pads, pad_names
from .turn import turn_box

CELL = 0.25
STEP = 0.25
SLACK_MARGIN = 2.0
DF40_BAND = 6.0
BREATHE_MARGIN = 1.0
DISP_GATE = 9.0
DISP_CAP = 8.0
DISP_SMALL_N = 3
LEASH_A_MAX = 11.0
LEASH_B_MAX = 40.0
MIN_SUBJECT_PINS = 3

_R2 = 0.5 ** 0.5
_COMPASS: tuple[tuple[float, float], ...] = (
    (0.0, -1.0), (0.0, 1.0), (1.0, 0.0), (-1.0, 0.0),
    (_R2, -_R2), (-_R2, -_R2), (_R2, _R2), (-_R2, _R2),
)


@dataclass
class BreatheStats:
    moved: int = 0
    n_still_starved: int = 0
    max_travel_mm: float = 0.0
    reverted_sheets: tuple[str, ...] = ()


def _eff_box(bbox: tuple[float, float, float, float], rot: float,
             px: float, py: float) -> tuple[float, float, float, float]:
    ex0, ey0, ex1, ey1 = turn_box(bbox, rot)
    return (px + ex0, py + ey0, px + ex1, py + ey1)


def _halo(b: tuple[float, float, float, float], m: float
          ) -> tuple[float, float, float, float]:
    return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)


class _Grid:
    __slots__ = ("nx", "ny", "cells")

    def __init__(self, board_w: float, board_h: float) -> None:
        self.nx = int(board_w / CELL) + 2
        self.ny = int(board_h / CELL) + 2
        self.cells = bytearray(self.nx * self.ny)

    def _bounds(self, box: tuple[float, float, float, float]
                ) -> tuple[int, int, int, int] | None:
        c0 = int((box[0] - ORIGIN_X) / CELL)
        r0 = int((box[1] - ORIGIN_Y) / CELL)
        c1 = int((box[2] - ORIGIN_X) / CELL)
        r1 = int((box[3] - ORIGIN_Y) / CELL)
        if c1 < 0 or r1 < 0 or c0 >= self.nx or r0 >= self.ny:
            return None
        return (max(0, c0), max(0, r0), min(self.nx - 1, c1), min(self.ny - 1, r1))

    def stamp(self, box: tuple[float, float, float, float], val: int = 1) -> None:
        bnd = self._bounds(box)
        if bnd is None:
            return
        c0, r0, c1, r1 = bnd
        v = 1 if val else 0
        for r in range(r0, r1 + 1):
            base = r * self.nx
            for c in range(c0, c1 + 1):
                self.cells[base + c] = v

    def free(self, box: tuple[float, float, float, float]) -> bool:
        c0f = (box[0] - ORIGIN_X) / CELL
        r0f = (box[1] - ORIGIN_Y) / CELL
        c1f = (box[2] - ORIGIN_X) / CELL
        r1f = (box[3] - ORIGIN_Y) / CELL
        if c0f < 0 or r0f < 0 or c1f >= self.nx or r1f >= self.ny:
            return False
        c0, r0, c1, r1 = int(c0f), int(r0f), int(c1f), int(r1f)
        for r in range(r0, r1 + 1):
            base = r * self.nx
            for c in range(c0, c1 + 1):
                if self.cells[base + c]:
                    return False
        return True


def _is_fixed(ref: str, sheet: str, footprint: str, *,
              mh_refs: set[str], som_j_refs: set[str],
              conn_edge: dict[str, str], contract_sheets: set[str],
              contract_members: frozenset[str] | set[str] = frozenset(),
              l4_exempt: frozenset[str]) -> bool:
    if sheet.startswith("som_j"):
        return True
    if ref in mh_refs:
        return True
    if ref in conn_edge:
        return True
    if sheet == "som_decoupling":
        return True
    if "Fiducial" in footprint:
        return True
    if sheet in contract_sheets:
        return True
    if ref in contract_members:
        return True
    if ref in l4_exempt:
        return True
    return False


def breathe_fanout(
    pos: dict[str, tuple[float, float]],
    *,
    resolvable: dict[str, Path],
    parts: dict[str, tuple[str, str, str, str]],
    bbox_of: dict[str, tuple[float, float, float, float]],
    fixed_rot: dict[str, float],
    side_of: dict[str, str],
    zorigin: dict[str, tuple[float, float]],
    board_w: float,
    board_h: float,
    som_keepout: tuple[float, float, float, float],
    conn_edge: dict[str, str],
    mh_refs: set[str],
    som_j_refs: set[str],
    df40_pad_boxes: list[tuple[float, float, float, float]],
    phase: str,
) -> BreatheStats:
    stats = BreatheStats()

    from schgen.verify.placement_contract_gate import (
        load_contract,
        wired_term_participants,
    )
    contract_sheets = {s for s in zorigin if load_contract(s) is not None}
    l4_exempt, _far = wired_term_participants()
    from schgen.generate.pcb import stage_templates as _st
    from schgen.verify.placement_contract_gate import discover_all
    contract_members: set[str] = set()
    for _sh, _ct in discover_all().items():
        try:
            contract_members |= _st.contract_member_brefs(_sh, _ct, resolvable)
        except Exception:  # noqa: BLE001
            continue

    def rot_of(r: str) -> float:
        return fixed_rot.get(r, 0.0)

    def box_of(r: str, p: tuple[float, float]) -> tuple[float, float, float, float]:
        return _eff_box(bbox_of[r], rot_of(r), p[0], p[1])

    def pins_of(r: str) -> int:
        mod = resolvable.get(r)
        return len(pad_names(mod)) if mod is not None else 0

    movable: list[str] = []
    fixed: list[str] = []
    for r in sorted(pos):
        if r not in bbox_of or r not in resolvable:
            fixed.append(r)
            continue
        sheet = parts[r][0] if r in parts else side_of.get(r, "")
        fp = parts[r][1] if r in parts else ""
        if _is_fixed(r, sheet, fp, mh_refs=mh_refs, som_j_refs=som_j_refs,
                     conn_edge=conn_edge, contract_sheets=contract_sheets,
                     contract_members=contract_members,
                     l4_exempt=l4_exempt):
            fixed.append(r)
        else:
            movable.append(r)

    if not movable:
        return stats

    grid_top = _Grid(board_w, board_h)
    grid_bot = _Grid(board_w, board_h)

    def gridfor(side: str) -> _Grid:
        return grid_bot if side == "bottom" else grid_top

    x0, y0 = ORIGIN_X, ORIGIN_Y
    x1, y1 = ORIGIN_X + board_w, ORIGIN_Y + board_h
    for g in (grid_top, grid_bot):
        g.stamp((x0, y0, x1, y0 + BOARD_EDGE_MARGIN))
        g.stamp((x0, y1 - BOARD_EDGE_MARGIN, x1, y1))
        g.stamp((x0, y0, x0 + BOARD_EDGE_MARGIN, y1))
        g.stamp((x1 - BOARD_EDGE_MARGIN, y0, x1, y1))
        g.stamp(som_keepout)
        g.stamp(_halo(som_keepout, SOM_ZONE_GROW))
        for band in df40_pad_boxes:
            g.stamp(band)

    for r in fixed:
        if r not in bbox_of or r not in resolvable:
            continue
        gridfor(side_of.get(r, "top")).stamp(_halo(box_of(r, pos[r]), PLACE_CLEAR))

    for r in sorted(pos):
        if (side_of.get(r) == "top" and r in resolvable
                and has_thru_pads(resolvable[r]) and r in bbox_of):
            grid_bot.stamp(_halo(box_of(r, pos[r]), PLACE_CLEAR))

    for r in movable:
        gridfor(side_of.get(r, "top")).stamp(_halo(box_of(r, pos[r]), PLACE_CLEAR / 2))

    by_sheet: dict[str, list[str]] = {}
    for r in movable:
        by_sheet.setdefault(parts[r][0], []).append(r)

    @dataclass
    class _Group:
        anchor: str
        members: tuple[str, ...]
        sheet: str

    groups: list[_Group] = []
    for sheet in sorted(by_sheet):
        members = by_sheet[sheet]
        subjects = sorted(r for r in members if pins_of(r) >= MIN_SUBJECT_PINS)
        passives = [r for r in members if _is_cluster_passive(r, pins_of(r))]
        non_riders = sorted(
            r for r in members
            if pins_of(r) < MIN_SUBJECT_PINS and not _is_cluster_passive(r, pins_of(r)))
        if subjects:
            assign: dict[str, list[str]] = {s: [] for s in subjects}
            for p in sorted(passives):
                pc = pos[p]
                best = min(subjects, key=lambda s: (hypot(
                    pos[s][0] - pc[0], pos[s][1] - pc[1]), s))
                assign[best].append(p)
            for p in non_riders:
                pc = pos[p]
                best = min(subjects, key=lambda s: (hypot(
                    pos[s][0] - pc[0], pos[s][1] - pc[1]), s))
                assign[best].append(p)
            for s in subjects:
                mem = tuple(sorted([s, *assign[s]]))
                groups.append(_Group(anchor=s, members=mem, sheet=sheet))
        else:
            mem = tuple(sorted(members))
            if mem:
                groups.append(_Group(anchor=mem[0], members=mem, sheet=sheet))

    seed_pos: dict[str, tuple[float, float]] = {r: pos[r] for r in movable}

    seed_centroid: dict[str, tuple[float, float]] = {}
    zone_diag: dict[str, float] = {}
    sheet_area: dict[str, float] = {}
    seed_disp: dict[str, float] = {}
    for sheet, members in by_sheet.items():
        mem = sorted(members)
        cx = sum(pos[r][0] for r in mem) / len(mem)
        cy = sum(pos[r][1] for r in mem) / len(mem)
        seed_centroid[sheet] = (cx, cy)
        xs0 = [box_of(r, pos[r])[0] for r in mem]
        ys0 = [box_of(r, pos[r])[1] for r in mem]
        xs1 = [box_of(r, pos[r])[2] for r in mem]
        ys1 = [box_of(r, pos[r])[3] for r in mem]
        zw, zh = max(xs1) - min(xs0), max(ys1) - min(ys0)
        zone_diag[sheet] = 0.5 * hypot(zw, zh)
        area = 0.0
        for r in mem:
            b = _eff_box(bbox_of[r], rot_of(r), 0.0, 0.0)
            area += (b[2] - b[0]) * (b[3] - b[1])
        sheet_area[sheet] = area or 1.0
        seed_disp[sheet] = (zw * zh) / sheet_area[sheet]

    def leash_r(sheet: str) -> float:
        r_seed = zone_diag[sheet]
        if phase == "A":
            return min(LEASH_A_MAX, max(2.0, 0.5 * r_seed))
        analytic = (DISP_CAP * sheet_area[sheet] / pi) ** 0.5 - r_seed
        return min(LEASH_B_MAX, max(LEASH_A_MAX, analytic))

    def foreign_boxes(anchor: str, group_members: set[str]
                      ) -> list[tuple[float, float, float, float]]:
        side = side_of.get(anchor, "top")
        my_sheet = parts[anchor][0]
        out: list[tuple[float, float, float, float]] = []
        for r in sorted(pos):
            if r in group_members:
                continue
            if r not in bbox_of or r not in resolvable:
                continue
            if side_of.get(r, "top") != side:
                continue
            r_sheet = parts[r][0] if r in parts else ""
            r_fp = parts[r][1] if r in parts else ""
            if r in som_j_refs:
                continue
            if not counts_as_crowder(r, r_sheet, pins_of(r), r_fp, my_sheet):
                continue
            out.append(box_of(r, pos[r]))
        return out

    def clearance(anchor: str, group_members: set[str],
                  foreigns: list[tuple[float, float, float, float]]) -> float:
        mb = box_of(anchor, pos[anchor])
        best = float("inf")
        for fb in foreigns:
            g = _rect_gap(mb, fb)
            if g < best:
                best = g
        return best

    need_of: dict[str, float] = {}
    target_of: dict[str, float] = {}
    deficit_of: dict[str, float] = {}
    subject_groups: list[_Group] = []
    for grp in groups:
        need, _b = intelligent_need(pins_of(grp.anchor))
        need_of[grp.anchor] = need
        target_of[grp.anchor] = need + BREATHE_MARGIN
        if pins_of(grp.anchor) < MIN_SUBJECT_PINS:
            continue
        fb = foreign_boxes(grp.anchor, set(grp.members))
        cur = clearance(grp.anchor, set(grp.members), fb)
        deficit_of[grp.anchor] = target_of[grp.anchor] - cur
        subject_groups.append(grp)

    subject_groups.sort(key=lambda g: (-deficit_of[g.anchor], g.anchor))

    _EPS = 1e-4

    def unstamp(grp: _Group) -> None:
        for r in grp.members:
            gridfor(side_of.get(r, "top")).stamp(
                _halo(box_of(r, pos[r]), PLACE_CLEAR / 2), 0)

    def restamp(grp: _Group) -> None:
        for r in grp.members:
            gridfor(side_of.get(r, "top")).stamp(
                _halo(box_of(r, pos[r]), PLACE_CLEAR / 2), 1)

    guard_subjects: list[tuple[str, str, str, float]] = []
    for r in sorted(pos):
        if r not in bbox_of or r not in resolvable or r in som_j_refs:
            continue
        p = pins_of(r)
        if p < MIN_SUBJECT_PINS or p >= 40:
            continue
        s_need, _sb = intelligent_need(p)
        if s_need > PLACE_CLEAR + 1e-9:
            guard_subjects.append((r, parts[r][0], side_of.get(r, "top"),
                                   s_need))

    def group_free(grp: _Group, delta: tuple[float, float]) -> bool:
        members = set(grp.members)
        for r in grp.members:
            side = side_of.get(r, "top")
            g = gridfor(side)
            b = _eff_box(bbox_of[r], rot_of(r),
                         pos[r][0] + delta[0], pos[r][1] + delta[1])
            if not g.free(_halo(b, PLACE_CLEAR / 2)):
                return False
            r_sheet = parts[r][0] if r in parts else ""
            r_cp = _is_cluster_passive(r, pins_of(r))
            for s, s_sheet, s_side, s_need in guard_subjects:
                if s in members or s_side != side:
                    continue
                if (r_cp and s_sheet == r_sheet) or is_testpoint_ref(r):
                    continue
                if _rect_gap(b, box_of(s, pos[s])) < s_need - _EPS:
                    return False
            p = pins_of(r)
            if p >= MIN_SUBJECT_PINS:
                r_need, _rb = intelligent_need(p)
                if r_need > PLACE_CLEAR + 1e-9:
                    fb = foreign_boxes(r, members)
                    old_b = box_of(r, pos[r])
                    old_clr = min((_rect_gap(old_b, f) for f in fb),
                                  default=float("inf"))
                    new_clr = min((_rect_gap(b, f) for f in fb),
                                  default=float("inf"))
                    if new_clr < min(r_need, old_clr) - _EPS:
                        return False
        return True

    def group_centroid_after(grp: _Group, delta: tuple[float, float]
                             ) -> tuple[float, float]:
        mem = sorted(by_sheet[grp.sheet])
        cx = sum(pos[r][0] + (delta[0] if r in grp.members else 0.0)
                 for r in mem) / len(mem)
        cy = sum(pos[r][1] + (delta[1] if r in grp.members else 0.0)
                 for r in mem) / len(mem)
        return (cx, cy)

    def leash_ok(grp: _Group, delta: tuple[float, float]) -> bool:
        sc = seed_centroid[grp.sheet]
        ca = group_centroid_after(grp, delta)
        return hypot(ca[0] - sc[0], ca[1] - sc[1]) <= leash_r(grp.sheet) + _EPS

    for grp in subject_groups:
        members = set(grp.members)
        need = target_of[grp.anchor]
        fb0 = foreign_boxes(grp.anchor, members)
        cur = clearance(grp.anchor, members, fb0)
        if cur >= need - _EPS:
            continue
        deficit = need - cur
        reach_cap = deficit + SLACK_MARGIN

        mb = box_of(grp.anchor, pos[grp.anchor])
        mcx = (mb[0] + mb[2]) / 2
        mcy = (mb[1] + mb[3]) / 2
        crowder = min(fb0, key=lambda f: _rect_gap(mb, f)) if fb0 else None
        away: tuple[float, float] | None = None
        if crowder is not None:
            fcx = (crowder[0] + crowder[2]) / 2
            fcy = (crowder[1] + crowder[3]) / 2
            dvx, dvy = mcx - fcx, mcy - fcy
            dn = hypot(dvx, dvy)
            if dn > 1e-6:
                away = (dvx / dn, dvy / dn)

        if phase == "A":
            dirs = [away] if away is not None else []
        else:
            dirs = ([away] if away is not None else []) + list(_COMPASS)

        unstamp(grp)

        best_delta: tuple[float, float] = (0.0, 0.0)
        best_clear = cur
        won = False
        for d in dirs:
            if d is None:
                continue
            ux, uy = d
            n_steps = int(reach_cap / STEP) + 1
            last_free: tuple[float, float] | None = None
            for k in range(1, n_steps + 1):
                delta = (ux * k * STEP, uy * k * STEP)
                if not leash_ok(grp, delta):
                    break
                if not group_free(grp, delta):
                    break
                last_free = delta
                trial_box = _eff_box(bbox_of[grp.anchor], rot_of(grp.anchor),
                                     pos[grp.anchor][0] + delta[0],
                                     pos[grp.anchor][1] + delta[1])
                tclr = min((_rect_gap(trial_box, f) for f in fb0),
                           default=float("inf"))
                if tclr > best_clear + _EPS:
                    best_clear = tclr
                    best_delta = delta
                if tclr >= need - _EPS:
                    best_delta = delta
                    won = True
                    break
            if won:
                break
            del last_free

        if best_delta != (0.0, 0.0):
            ax, ay = pos[grp.anchor]
            snapped_ax = _q.breathe_anchor_grid(
                ORIGIN_X + ax + best_delta[0]) - ORIGIN_X
            snapped_ay = _q.breathe_anchor_grid(
                ORIGIN_Y + ay + best_delta[1]) - ORIGIN_Y
            sdelta = (round(snapped_ax - ax, 4), round(snapped_ay - ay, 4))
            commit: tuple[float, float] | None = None
            if (group_free(grp, sdelta) and leash_ok(grp, sdelta)):
                commit = sdelta
            else:
                bx, by = best_delta
                bn = hypot(bx, by)
                if bn > 1e-6:
                    ux, uy = bx / bn, by / bn
                    for k in range(int(bn / STEP), 0, -1):
                        cand = (ux * k * STEP, uy * k * STEP)
                        cax = _q.breathe_anchor_grid(
                            ORIGIN_X + ax + cand[0]) - ORIGIN_X
                        cay = _q.breathe_anchor_grid(
                            ORIGIN_Y + ay + cand[1]) - ORIGIN_Y
                        cd = (round(cax - ax, 4), round(cay - ay, 4))
                        if group_free(grp, cd) and leash_ok(grp, cd):
                            commit = cd
                            break
            if commit is not None and commit != (0.0, 0.0):
                for r in grp.members:
                    nx = round(pos[r][0] + commit[0], 4)
                    ny = round(pos[r][1] + commit[1], 4)
                    pos[r] = (nx, ny)
                stats.moved += 1
                stats.max_travel_mm = max(stats.max_travel_mm,
                                          hypot(commit[0], commit[1]))
        restamp(grp)

    reverted: list[str] = []
    for sheet in sorted(by_sheet):
        mem = sorted(by_sheet[sheet])
        if len(mem) <= DISP_SMALL_N:
            continue
        xs0 = [box_of(r, pos[r])[0] for r in mem]
        ys0 = [box_of(r, pos[r])[1] for r in mem]
        xs1 = [box_of(r, pos[r])[2] for r in mem]
        ys1 = [box_of(r, pos[r])[3] for r in mem]
        disp = ((max(xs1) - min(xs0)) * (max(ys1) - min(ys0))) / sheet_area[sheet]
        cap = max(DISP_CAP, seed_disp[sheet])
        if disp > cap + _EPS:
            reverted.append(sheet)
            for r in mem:
                if r in seed_pos:
                    pos[r] = seed_pos[r]
    stats.reverted_sheets = tuple(reverted)

    still = 0
    for grp in subject_groups:
        fb = foreign_boxes(grp.anchor, set(grp.members))
        if clearance(grp.anchor, set(grp.members), fb) < need_of[grp.anchor] - _EPS:
            still += 1
    stats.n_still_starved = still
    return stats
