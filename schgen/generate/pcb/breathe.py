"""BREATHE — space-aware fan-out spread ("breathe into free space").

The seed placer packs the whole board TIGHT at PLACE_CLEAR=0.5 mm so it fits the
fixed floorplan outline (178x163). That tight pack leaves ~54 % of the board
empty, and the empty pockets sit DIRECTLY ADJACENT to the dense shelf-packed
clusters (bringup_modules, usb_jtag, motor_pwm, the SOT-23 rows, the C6xxx /
RN36xxx grids, the ESD arrays). This pass USES that adjacent free space: it moves
each fan-out-STARVED movable IC (with its own cluster passives riding rigidly)
into the gap next to its zone until it reaches its intelligent fan-out NEED, and
then keeps loosening the tightest clusters — WITHOUT growing the board.

The board size is FIXED (HARD constraint): growing it re-centres the SoM, shifts
the fixed DF40 mezzanine, and makes the regenerated escape ladder graze a DF40
pad. So this pass mutates ONLY ``pos[ref]`` for MOVABLE parts and never touches
the board outline, the SoM core, the DF40 receptacles, the escape copper, or any
FIXED part.

Design = a greedy free-space / occupancy-map engine whose no-overlap and
keepout-safety are guaranteed BY CONSTRUCTION: every candidate position is
validated against a stamped occupancy grid (board edge + SoM keepout + escape
region + DF40 6 mm bands + every FIXED courtyard + top-THT-on-bottom) before it
can be committed, and the map is updated incrementally as each part moves. Two
phases, same engine, differing only in the locality-leash radius and the
direction-search policy:

  * PHASE A — tight leash (adjacent-slack depth), direction = away-from-crowder.
    Cannot scatter; the mover only slides into the gap abutting its own zone.
  * PHASE B — wider analytic leash (bounded by the dispersion cap), direction =
    omnidirectional compass search. Lets a hemmed-in still-starved zone reach the
    empty left-third reservoir.

LAW-0 (electrical integrity) and LAW-1 (no overlap) hold by construction; LAW-5
(subsystem locality) holds via the per-sheet leash + a hard dispersion revert.
Determinism: pure function of the seed model, fixed iteration order, grid-snapped
commits, fresh local grids each call.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, pi
from pathlib import Path

from schgen.verify.fanout_gate import (
    _is_cluster_passive,
    _rect_gap,
    intelligent_need,
    is_testpoint_ref,
)

from .constants import ORIGIN_X, ORIGIN_Y, PLACE_CLEAR
from .footprint import _gridify, has_thru_pads, pad_names
from .mating_face import _rot_bbox_cw

# L4-local edge margin (placement.py:1127) — keep shifted copper this far inside
# Edge.Cuts. Not exported from constants; mirrored here as the same 0.6 mm floor.
EDGE_MARGIN = 0.6

# ---- tunables (spec §2, §5, §6) -----------------------------------------------------
CELL = 0.25             # occupancy raster cell (mm); fine enough not to round a gap
STEP = 0.25             # march increment (mm) == CELL
SLACK_MARGIN = 2.0      # allow marching slightly past target so the snap still clears
DF40_BAND = 6.0         # escape-obstacle safe radius around a DF40 pad field (mm)
ZONE_GROW = 2.0         # escape_region = som_keepout grown by this (escape.py:107)
# BREATHE_MARGIN: the pass aims for need + this, so a subject sitting EXACTLY at
# its need (slack~0 — 35 of them at seed) gains REAL breathing room, not a
# hairline touch. The GATE still only requires `need` (LAW-4: gate unchanged);
# this is purely the optimisation target that makes the tight clusters visibly
# loosen. Kept modest so travel + airwire growth stay small.
BREATHE_MARGIN = 1.0    # extra fan-out room to aim for above the gate floor (mm)
# dispersion fail-safe: the RATSNEST gate (ratsnest_gate.py) fails a sheet only
# above DISP_GATE=9.0 (bbox_area / sum-courtyard-area) and exempts sheets with
# <= DISP_SMALL_N parts. Our fail-safe reverts a sheet the pass pushed above
# DISP_CAP (< the gate, with margin) so a ratsnest breach is impossible by
# construction — but NEVER for the sheet's own SEED dispersion (several sheets
# seed at ~5x with no scatter), only for what the pass ADDS.
DISP_GATE = 9.0
DISP_CAP = 8.0          # fail-safe ceiling (< the 9.0 gate)
DISP_SMALL_N = 3        # exempt sheets this small (matches ratsnest_gate.SMALL_N)
LEASH_A_MAX = 11.0      # Phase-A leash hard cap (RECON-2 adjacent-slack depths)
LEASH_B_MAX = 40.0      # Phase-B leash hard cap
MIN_SUBJECT_PINS = 3    # a fan-out subject (matches fanout_gate.MIN_SUBJECT_PINS)

# Phase-B compass directions, fixed deterministic order (N,S,E,W,NE,NW,SE,SW).
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


# ---- geometry helpers (REUSE L4's / the gate's convention) --------------------------
def _eff_box(bbox: tuple[float, float, float, float], rot: float,
             px: float, py: float) -> tuple[float, float, float, float]:
    """Placed courtyard bbox in the board page frame — identical to
    placement.py:_eff_box and to _inst_courtyard (both use _rot_bbox_cw)."""
    ex0, ey0, ex1, ey1 = _rot_bbox_cw(bbox, rot)
    return (px + ex0, py + ey0, px + ex1, py + ey1)


def _halo(b: tuple[float, float, float, float], m: float
          ) -> tuple[float, float, float, float]:
    return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)


# ---- occupancy grid -----------------------------------------------------------------
class _Grid:
    """A boolean occupancy raster over the board interior (one per copper side).

    A cell is True (blocked) if any stamped box overlaps it. ``free`` returns True
    iff every cell overlapping a (haloed) box is clear. Cells outside the board
    interior are treated as blocked (so a candidate can never straddle the edge).
    """

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
        # clamp to the grid; a box that pokes fully outside is fully out-of-bounds
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
        # any part of the box outside the raster interior = not free (edge guard)
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


# ---- MOVABLE / FIXED predicate (spec §3) --------------------------------------------
def _is_fixed(ref: str, sheet: str, footprint: str, *,
              mh_refs: set[str], som_j_refs: set[str],
              conn_edge: dict[str, str], contract_sheets: set[str],
              contract_members: frozenset[str] | set[str] = frozenset(),
              l4_exempt: frozenset[str]) -> bool:
    if sheet.startswith("som_j"):
        return True                       # DF40 receptacles (HARD constraint #2)
    if ref in mh_refs:
        return True                       # mounting holes
    if ref in conn_edge:
        return True                       # off-board edge connectors (LAW-6)
    if sheet == "som_decoupling":
        return True                       # under-SoM grid
    if "Fiducial" in footprint:
        return True                       # fab-art
    if sheet in contract_sheets:
        return True                       # datasheet-true template sheets (wired)
    if ref in contract_members:
        return True                       # ANY contract's distance-constrained member
        #                                   (buck hot-loop/FB/inductor, crystals,
        #                                   in-path ESD/terminations) — inviolable
    if ref in l4_exempt:
        return True                       # T1-wired term participants
    return False


# ---- public entry -------------------------------------------------------------------
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
    """Spread starved MOVABLE ICs (+ riding cluster passives) into adjacent free
    space up to their intelligent fan-out need, bounded by a per-sheet locality
    leash, committing only ``_free`` + in-bounds + grid-snapped positions.
    Mutates ``pos`` in place. See module docstring / spec for the algorithm."""
    stats = BreatheStats()

    # contract (template) sheets + T1-wired participants -> FIXED
    from schgen.verify.placement_contract_gate import (
        load_contract,
        wired_term_participants,
    )
    contract_sheets = {s for s in zorigin if load_contract(s) is not None}
    l4_exempt, _far = wired_term_participants()
    # EVERY subsystem contract's members (not just the 3 wired sheets above):
    # discover_all() + contract_member_brefs give the parts pinned to datasheet-true
    # distances from connectors/pins — buck hot-loop caps + FB divider + inductor,
    # crystals, in-path ESD / terminations. Those distances are INVIOLABLE (user
    # law: "contracts requiring specific distances from connectors and pins
    # absolutely cannot be overruled"), so the spread must never move them.
    from schgen.generate.pcb import stage_templates as _st
    from schgen.verify.placement_contract_gate import discover_all
    contract_members: set[str] = set()
    for _sh, _ct in discover_all().items():
        try:
            contract_members |= _st.contract_member_brefs(_sh, _ct, resolvable)
        except Exception:  # noqa: BLE001 — a malformed contract must not break placement
            continue

    def rot_of(r: str) -> float:
        return fixed_rot.get(r, 0.0)

    def box_of(r: str, p: tuple[float, float]) -> tuple[float, float, float, float]:
        return _eff_box(bbox_of[r], rot_of(r), p[0], p[1])

    def pins_of(r: str) -> int:
        mod = resolvable.get(r)
        return len(pad_names(mod)) if mod is not None else 0

    # ---- classify every placed ref ---------------------------------------------
    movable: list[str] = []
    fixed: list[str] = []
    for r in sorted(pos):
        if r not in bbox_of or r not in resolvable:
            fixed.append(r)                 # can't reason about its box -> treat fixed
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

    # ---- build the two per-side occupancy grids --------------------------------
    grid_top = _Grid(board_w, board_h)
    grid_bot = _Grid(board_w, board_h)

    def gridfor(side: str) -> _Grid:
        return grid_bot if side == "bottom" else grid_top

    # 1. board-edge margin ring (both sides)
    x0, y0 = ORIGIN_X, ORIGIN_Y
    x1, y1 = ORIGIN_X + board_w, ORIGIN_Y + board_h
    for g in (grid_top, grid_bot):
        g.stamp((x0, y0, x1, y0 + EDGE_MARGIN))            # top ring
        g.stamp((x0, y1 - EDGE_MARGIN, x1, y1))            # bottom ring
        g.stamp((x0, y0, x0 + EDGE_MARGIN, y1))            # left ring
        g.stamp((x1 - EDGE_MARGIN, y0, x1, y1))            # right ring
        # 2. SoM keepout (page frame, halo baked in)
        g.stamp(som_keepout)
        # 3. escape region = keepout grown by ZONE_GROW
        g.stamp(_halo(som_keepout, ZONE_GROW))
        # 4. DF40 escape-obstacle bands (6 mm halo, explicit self-contained guard)
        for band in df40_pad_boxes:
            g.stamp(band)

    # 5. every FIXED part's haloed courtyard (halo = PLACE_CLEAR)
    for r in fixed:
        if r not in bbox_of or r not in resolvable:
            continue
        gridfor(side_of.get(r, "top")).stamp(_halo(box_of(r, pos[r]), PLACE_CLEAR))

    # 6. top-side THT pads -> stamp on the BOTTOM grid (cross-layer short guard)
    for r in sorted(pos):
        if (side_of.get(r) == "top" and r in resolvable
                and has_thru_pads(resolvable[r]) and r in bbox_of):
            grid_bot.stamp(_halo(box_of(r, pos[r]), PLACE_CLEAR))

    # 2.2 stamp the movers' seed positions (halo = PLACE_CLEAR/2, matching L4)
    for r in movable:
        gridfor(side_of.get(r, "top")).stamp(_halo(box_of(r, pos[r]), PLACE_CLEAR / 2))

    # ---- group movers: IC subject + its riding same-sheet cluster passives ------
    # A movable sheet's fan-out subject (>=3-pin) anchors a group; its same-sheet
    # 2-pin R/C/L cluster passives ride rigidly. Passive-only groups (no subject)
    # move as their own rigid mini-group keyed on the grid centroid.
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
            # each subject rides its OWN group; assign each passive to the nearest
            # subject by seed centroid distance (deterministic, sorted).
            assign: dict[str, list[str]] = {s: [] for s in subjects}
            for p in sorted(passives):
                pc = pos[p]
                best = min(subjects, key=lambda s: (hypot(
                    pos[s][0] - pc[0], pos[s][1] - pc[1]), s))
                assign[best].append(p)
            # any leftover non-subject non-passive parts ride the nearest subject too
            for p in non_riders:
                pc = pos[p]
                best = min(subjects, key=lambda s: (hypot(
                    pos[s][0] - pc[0], pos[s][1] - pc[1]), s))
                assign[best].append(p)
            for s in subjects:
                mem = tuple(sorted([s, *assign[s]]))
                groups.append(_Group(anchor=s, members=mem, sheet=sheet))
        else:
            # pure passive / no-IC sheet: one rigid mini-group (anchor = 1st ref)
            mem = tuple(sorted(members))
            if mem:
                groups.append(_Group(anchor=mem[0], members=mem, sheet=sheet))

    # snapshot the SEED positions of every mover so a dispersion-breaching sheet
    # can be reverted whole (fail-safe, never a gate softening — LAW-4/LAW-5).
    seed_pos: dict[str, tuple[float, float]] = {r: pos[r] for r in movable}

    # ---- seed centroids + leash radius per sheet (frozen) -----------------------
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
            # Phase A: tight leash — the adjacent-slack depth. Bounded so a mover
            # only reaches the gap abutting its own zone; cannot scatter.
            return min(LEASH_A_MAX, max(2.0, 0.5 * r_seed))
        # Phase B: analytic bound so a still-starved zone can reach a distant
        # pocket while per-sheet dispersion stays under DISP_CAP.
        analytic = (DISP_CAP * sheet_area[sheet] / pi) ** 0.5 - r_seed
        return min(LEASH_B_MAX, max(LEASH_A_MAX, analytic))

    # ---- current foreign clearance for a group's subject ------------------------
    # foreign = same-side courtyards, skipping same-sheet cluster passives, DF40,
    # fiducials (exactly fanout_gate.check's skip list). We measure against the
    # live positions of FIXED parts + OTHER groups' current positions.
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
            if r in som_j_refs or pins_of(r) >= 40:
                continue                    # DF40
            if "Fiducial" in (parts[r][1] if r in parts else ""):
                continue
            if (r in parts and parts[r][0] == my_sheet
                    and _is_cluster_passive(r, pins_of(r))):
                continue                    # own-cluster passive
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

    # ---- iteration order: most-starved first, ref tiebreak ----------------------
    # need_of  = the GATE floor (intelligent_need) — used to report still-starved.
    # target_of = need + BREATHE_MARGIN — the OPTIMISATION aim, so a subject at
    #             exactly its need still gets real breathing room (the loosening).
    need_of: dict[str, float] = {}
    target_of: dict[str, float] = {}
    deficit_of: dict[str, float] = {}
    subject_groups: list[_Group] = []
    for grp in groups:
        need, _b = intelligent_need(pins_of(grp.anchor))
        need_of[grp.anchor] = need
        target_of[grp.anchor] = need + BREATHE_MARGIN
        if pins_of(grp.anchor) < MIN_SUBJECT_PINS:
            continue                        # passive-only group: not spread for itself
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

    # STAYER-NEED GUARD: the stamped grid enforces only the PLACE_CLEAR halo, so
    # a marching group could legally stop inside a STAYING subject's D13 fan-out
    # floor (measured: SW9001's group landed 0.910 from J9001's 1.00-need
    # courtyard — the mover's own clearance was validated, the stayer's never).
    # Every candidate delta must also keep each moved member outside every
    # foreign above-floor subject's need (own-sheet cluster passives waived,
    # exactly the gate's rule), and a moved SUBJECT must never let its own
    # aggregate clearance regress below min(its need, its current clearance).
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

    # ---- greedy per-subject-group march ----------------------------------------
    for grp in subject_groups:
        members = set(grp.members)
        need = target_of[grp.anchor]        # aim for need + BREATHE_MARGIN
        fb0 = foreign_boxes(grp.anchor, members)
        cur = clearance(grp.anchor, members, fb0)
        if cur >= need - _EPS:
            continue                        # already has full breathing room
        deficit = need - cur
        reach_cap = deficit + SLACK_MARGIN

        # crowder direction: unit vector away from the nearest foreign box
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
                    break                   # blocked in this direction; stop marching
                last_free = delta
                # recompute clearance against foreign boxes at this trial delta
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
            # if we didn't win but recorded a better partial, keep it (already stored)
            del last_free

        # grid-snap the winning ANCHOR origin; apply the SAME snapped delta to all.
        # pos is the board-frame origin; the emitted page position is ORIGIN + pos.
        # Zones now emit at their EXACT floorplan pose (no seed snap), but a MOVED
        # anchor still snaps to the page placement grid for a stable, coarse move
        # quantum — safe because the snapped delta is RE-VALIDATED (_free + leash)
        # below and retreats or aborts on any collision, unlike the removed blind
        # seed snap.
        if best_delta != (0.0, 0.0):
            ax, ay = pos[grp.anchor]
            snapped_ax = _gridify(ORIGIN_X + ax + best_delta[0]) - ORIGIN_X
            snapped_ay = _gridify(ORIGIN_Y + ay + best_delta[1]) - ORIGIN_Y
            sdelta = (round(snapped_ax - ax, 4), round(snapped_ay - ay, 4))
            # re-test _free + leash on the SNAPPED delta; if it collides, retreat to
            # the last free pre-snap sub-step; if that too fails, make no move.
            commit: tuple[float, float] | None = None
            if (group_free(grp, sdelta) and leash_ok(grp, sdelta)):
                commit = sdelta
            else:
                # retreat: try snapping toward the anchor in CELL steps
                bx, by = best_delta
                bn = hypot(bx, by)
                if bn > 1e-6:
                    ux, uy = bx / bn, by / bn
                    for k in range(int(bn / STEP), 0, -1):
                        cand = (ux * k * STEP, uy * k * STEP)
                        cax = _gridify(ORIGIN_X + ax + cand[0]) - ORIGIN_X
                        cay = _gridify(ORIGIN_Y + ay + cand[1]) - ORIGIN_Y
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

    # ---- per-sheet dispersion fail-safe (LAW-5): revert a breaching sheet -------
    # A sheet is reverted whole to seed iff the pass pushed its dispersion above
    # the fail-safe cap AND above its own seed dispersion (never punish a sheet for
    # its seed spread — several seed at ~5x with no scatter) — and only for sheets
    # large enough to matter (matching the ratsnest gate's SMALL_N exemption). This
    # makes a ratsnest dispersion breach impossible by construction.
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
                    pos[r] = seed_pos[r]        # restore the whole sheet to seed
    stats.reverted_sheets = tuple(reverted)

    # count still-starved subjects after the pass
    still = 0
    for grp in subject_groups:
        fb = foreign_boxes(grp.anchor, set(grp.members))
        if clearance(grp.anchor, set(grp.members), fb) < need_of[grp.anchor] - _EPS:
            still += 1
    stats.n_still_starved = still
    return stats
