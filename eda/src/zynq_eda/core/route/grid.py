"""Cached-grid orthogonal router — connect same-net terminals with clean wires.

Stage C of the convergent layout engine. Placement (Stages A/B) opens wide,
body-and-text-free channels; this router fills them with real wires. It is a
bounded grid A* (Lee/maze-style, every cell expanded at most once → it cannot
loop) on the REAL KiCad 1.27 mm grid, so wire endpoints land exactly on pins.

The obstacle bitmap is built ONCE per :class:`RouteGrid` (the fix for the old
per-net re-rasterisation blow-up) using the SAME two-tier clearance the overlap
validator uses — VISUAL_CLEARANCE_MM around symbols/text, WIRE_VS_WIRE_CLEARANCE
around wires — so a route this finds is a route the validator agrees is clean.

:func:`route_terminals` connects each net's terminals into a tree: the first
terminal seeds the tree, each remaining terminal is routed (multi-goal A*) to
the NEAREST already-laid cell of its own net, so taps naturally share a trunk
and a junction dot is dropped at every T. Other nets' wires are obstacles, so
the router never lays a foreign crossing; same-net cells are free, so it merges.
"""

from __future__ import annotations

import heapq
from collections import defaultdict

from zynq_eda.core.layout._constants import (
    VISUAL_CLEARANCE_MM,
    WIRE_THICKNESS_MM,
    WIRE_VS_WIRE_CLEARANCE_MM,
)
from zynq_eda.core.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from zynq_eda.core.model.sheet import PlacedJunction, PlacedWire

_GRID = KICAD_GRID_MM  # 1.27 mm — the real KiCad grid, so wires land on pins.
# A turn costs this many grid-steps of extra length → prefer few-bend routes
# (the hand-drawn look) without refusing to detour.
_TURN_PENALTY = 3.0 * _GRID
_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
# Wire-vs-SYMBOL clearance for ROUTING. The overlap validator checks
# wire×symbol at TRUE overlap (clearance 0) — a wire legitimately runs right up
# to a pin/body edge (overlap.py). So routing must NOT inflate bodies by the
# 2.54 mm symbol-symbol crowding clearance (that walls every pin in). One grid
# step keeps the wire stroke off the body for a hand-drawn look while leaving
# the pin-to-body channel walkable. Validator (true-overlap) stays the judge.
_SYMBOL_WIRE_CLEARANCE_MM = 1.27

# Max cells a per-terminal escape lane marches outboard before giving up. A pin
# tip can quantise into its own body core (just outside in mm, inside after grid
# + stroke inflation); the lane exempts a straight outboard run until the first
# free cell. ~6 cells covers the widest body half + clearance.
_ESCAPE_MAX = 6
# Soft cost (mm) added when a route steps onto a cell adjacent to an already-
# routed foreign net. Large enough to push distinct nets into parallel tracks
# (no two trunks stacking in one channel) yet finite, so a net still uses a
# congested cell when there is genuinely no alternative.
_CONGESTION_PENALTY = 8.0 * _GRID


class RouteGrid:
    """A grid of blocked cells, rasterised ONCE from a sheet's obstacles."""

    def __init__(self, obstacles, *, clearance_mm: float = _SYMBOL_WIRE_CLEARANCE_MM,
                 margin_mm: float = 12.7, bounds_pts=()) -> None:
        # Grid extent covers obstacles AND any extra ``bounds_pts`` (e.g. far
        # terminals) so the search window never drops a terminal off-grid.
        xs = [b.min.x for b in obstacles] + [b.max.x for b in obstacles] + [p.x for p in bounds_pts]
        ys = [b.min.y for b in obstacles] + [b.max.y for b in obstacles] + [p.y for p in bounds_pts]
        if xs:
            min_x = min(xs) - margin_mm
            min_y = min(ys) - margin_mm
            max_x = max(xs) + margin_mm
            max_y = max(ys) + margin_mm
        else:
            min_x = min_y = 0.0
            max_x = max_y = _GRID
        self.ox = snap_to_grid(min_x)
        self.oy = snap_to_grid(min_y)
        self.nx = int((max_x - self.ox) / _GRID) + 2
        self.ny = int((max_y - self.oy) / _GRID) + 2

        self.clearance_mm = clearance_mm
        self.blocked = self.cells_for(obstacles)

    def cells_for(self, obstacles, *, clearance_override: float | None = None) -> set[tuple[int, int]]:
        """Return the set of grid cells the given obstacles block.

        With ``clearance_override`` the symbol clearance is forced to that value
        (e.g. 0.0 → just the body+half-wire CORE the validator flags as a true
        wire-over-body overlap). The two-tier wire rule is unchanged."""
        cells: set[tuple[int, int]] = set()
        half_wire = WIRE_THICKNESS_MM / 2.0
        sym_clr = self.clearance_mm if clearance_override is None else clearance_override
        for b in obstacles:
            clr = WIRE_VS_WIRE_CLEARANCE_MM if b.kind == "wire" else sym_clr
            infl = clr + half_wire
            ix_lo = max(0, int((b.min.x - infl - self.ox) / _GRID) + 1)
            ix_hi = min(self.nx - 1, int((b.max.x + infl - self.ox) / _GRID))
            iy_lo = max(0, int((b.min.y - infl - self.oy) / _GRID) + 1)
            iy_hi = min(self.ny - 1, int((b.max.y + infl - self.oy) / _GRID))
            for ix in range(ix_lo, ix_hi + 1):
                for iy in range(iy_lo, iy_hi + 1):
                    cells.add((ix, iy))
        return cells

    def cell(self, p: Point) -> tuple[int, int]:
        return (round((p.x - self.ox) / _GRID), round((p.y - self.oy) / _GRID))

    def point(self, c: tuple[int, int]) -> Point:
        return Point(snap_to_grid(self.ox + c[0] * _GRID), snap_to_grid(self.oy + c[1] * _GRID))

    def in_bounds(self, c: tuple[int, int]) -> bool:
        return 0 <= c[0] < self.nx and 0 <= c[1] < self.ny

    def route(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        *,
        foreign: frozenset[tuple[int, int]] = frozenset(),
        exempt: frozenset[tuple[int, int]] = frozenset(),
        soft: frozenset[tuple[int, int]] = frozenset(),
    ) -> list[tuple[int, int]] | None:
        """Multi-goal A* from ``start`` to ANY cell in ``goals``.

        ``foreign`` cells (other nets' wires) are blocked; ``exempt`` cells
        (terminal pins + their immediate neighbours) are always walkable so a
        wire can leave/dock at a pin that abuts its own body; ``soft`` cells
        (already-routed nets' surroundings) cost extra so distinct nets fan
        into parallel tracks instead of stacking in one channel (congestion
        routing). Returns the cell path (inclusive) or ``None``.
        """
        if not self.in_bounds(start):
            return None
        if start in goals:
            return [start]
        blocked = set(self.blocked)
        blocked |= foreign
        blocked -= exempt
        blocked -= goals
        blocked.discard(start)

        goal_list = list(goals)

        def h(cx: int, cy: int) -> float:
            return min(abs(cx - gx) + abs(cy - gy) for gx, gy in goal_list) * _GRID

        start_state = (start[0], start[1], -1)
        g_best: dict[tuple[int, int, int], float] = {start_state: 0.0}
        heap: list[tuple[float, tuple[int, int, int]]] = [(h(start[0], start[1]), start_state)]
        came: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        goal_state: tuple[int, int, int] | None = None
        while heap:
            _f, st = heapq.heappop(heap)
            cx, cy, cd = st
            if (cx, cy) in goals:
                goal_state = st
                break
            g = g_best[st]
            for di, (dx, dy) in enumerate(_DIRS):
                ncx, ncy = cx + dx, cy + dy
                if not (0 <= ncx < self.nx and 0 <= ncy < self.ny):
                    continue
                if (ncx, ncy) in blocked:
                    continue
                step = _GRID + (_TURN_PENALTY if cd != -1 and di != cd else 0.0)
                if (ncx, ncy) in soft:
                    step += _CONGESTION_PENALTY
                ng = g + step
                ns = (ncx, ncy, di)
                if ng < g_best.get(ns, float("inf")):
                    g_best[ns] = ng
                    came[ns] = st
                    heapq.heappush(heap, (ng + h(ncx, ncy), ns))
        if goal_state is None:
            return None
        cells: list[tuple[int, int]] = []
        s = goal_state
        while True:
            cells.append((s[0], s[1]))
            if s == start_state:
                break
            s = came[s]
        cells.reverse()
        return cells


def _collinear(a: Point, b: Point, c: Point) -> bool:
    return (a.x == b.x == c.x) or (a.y == b.y == c.y)


def _cells_to_segments(cells: list[tuple[int, int]], grid: RouteGrid) -> list[tuple[Point, Point]]:
    """Collapse a cell path to maximal straight (Point, Point) runs."""
    pts = [grid.point(c) for c in cells]
    segs: list[tuple[Point, Point]] = []
    if len(pts) < 2:
        return segs
    run = pts[0]
    for i in range(1, len(pts)):
        cur = pts[i]
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        turning = nxt is not None and not _collinear(run, cur, nxt)
        if nxt is None or turning:
            if run.x != cur.x or run.y != cur.y:
                segs.append((run, cur))
            run = cur
    return segs


def _strictly_interior(p: Point, a: Point, b: Point) -> bool:
    """True iff ``p`` lies strictly inside the open segment ``a``–``b``."""
    if a.x == b.x == p.x:
        lo, hi = sorted((a.y, b.y))
        return lo < p.y < hi
    if a.y == b.y == p.y:
        lo, hi = sorted((a.x, b.x))
        return lo < p.x < hi
    return False


def _merge_net_segments(segs: list[tuple[Point, Point]]) -> list[tuple[Point, Point]]:
    """Union a net's segments into NON-OVERLAPPING maximal runs.

    The tree router can lay a segment that retraces or overlaps a cell another
    branch of the SAME net already occupies (a real wire×wire overlap the
    validator flags even within one net). Rasterise each segment to unit grid
    edges, dedupe, then re-merge collinear adjacent edges into maximal runs —
    so every grid edge the net covers is emitted exactly once."""
    edges: set[tuple[float, float, float, float]] = set()
    for a, b in segs:
        if a.x == b.x:
            ys = sorted((a.y, b.y))
            y = ys[0]
            while y < ys[1] - 1e-9:
                edges.add((a.x, y, a.x, snap_to_grid(y + _GRID)))
                y = snap_to_grid(y + _GRID)
        elif a.y == b.y:
            xs = sorted((a.x, b.x))
            x = xs[0]
            while x < xs[1] - 1e-9:
                edges.add((x, a.y, snap_to_grid(x + _GRID), a.y))
                x = snap_to_grid(x + _GRID)
    # Merge collinear unit edges into maximal runs.
    h_edges = sorted(e for e in edges if e[1] == e[3])  # horizontal
    v_edges = sorted((e[1], e[0], e[3], e[2]) for e in edges if e[0] == e[2])  # vertical, keyed by x
    out: list[tuple[Point, Point]] = []
    # Horizontal: group by y, merge along x.
    by_y: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for x0, y0, x1, _y1 in h_edges:
        by_y[y0].append((x0, x1))
    for y, spans in by_y.items():
        spans.sort()
        cs, ce = spans[0]
        for s, e in spans[1:]:
            if s <= ce + 1e-9:
                ce = max(ce, e)
            else:
                out.append((Point(cs, y), Point(ce, y)))
                cs, ce = s, e
        out.append((Point(cs, y), Point(ce, y)))
    # Vertical: group by x, merge along y.
    by_x: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for y0, x0, y1, _x1 in v_edges:
        by_x[x0].append((y0, y1))
    for x, spans in by_x.items():
        spans.sort()
        cs, ce = spans[0]
        for s, e in spans[1:]:
            if s <= ce + 1e-9:
                ce = max(ce, e)
            else:
                out.append((Point(x, cs), Point(x, ce)))
                cs, ce = s, e
        out.append((Point(x, cs), Point(x, ce)))
    return out


def _net_junctions(segs: list[tuple[Point, Point]]) -> list[PlacedJunction]:
    """Junction at every point where >= 3 same-net wire ends/passes meet.

    An L-corner (two segment ends, no pass-through) is degree 2 → no junction
    (KiCad connects it implicitly). A T (one end landing mid-span of another)
    is degree 3 → junction. A 4-way is degree 4 → junction.
    """
    end_count: dict[tuple[float, float], int] = defaultdict(int)
    for a, b in segs:
        end_count[(a.x, a.y)] += 1
        end_count[(b.x, b.y)] += 1
    juncs: list[PlacedJunction] = []
    for (px, py), cnt in end_count.items():
        p = Point(px, py)
        interior = any(_strictly_interior(p, a, b) for a, b in segs)
        degree = cnt + (2 if interior else 0)
        if degree >= 3:
            juncs.append(PlacedJunction(p))
    return juncs


def route_terminals(
    obstacles,
    nets: dict[str, list[Point]],
    *,
    clearance_mm: float = _SYMBOL_WIRE_CLEARANCE_MM,
    own_obstacles: dict[str, list] | None = None,
    escape_dirs: dict[str, list[tuple[int, int]]] | None = None,
):
    """Route every net's terminals into clean orthogonal trees.

    ``obstacles`` is the static bitmap (symbol footprints + text + any fixed
    wires). ``nets`` maps a net name to the list of terminal points that must
    be electrically joined. ``own_obstacles`` optionally maps a net name to the
    obstacle bboxes belonging to ITS OWN symbols (the IC pin's body, its
    passives, its power symbols): a wire may traverse its own net's clearance
    halo (those parts are electrically connected to it anyway) but never a
    foreign body — this is what lets a pin escape a large IC body.

    Returns ``(wires, junctions, failures)`` where ``failures`` is the list of
    ``(net, terminal)`` that could not be routed (never silently dropped — the
    caller must surface them).
    """
    # Size the grid to cover BOTH obstacles AND every terminal (with no
    # obstacles the bounds would otherwise collapse and drop far terminals).
    all_pts = [p for pts in nets.values() for p in pts]
    grid = RouteGrid(obstacles, clearance_mm=clearance_mm, bounds_pts=all_pts)
    own_obstacles = own_obstacles or {}
    escape_dirs = escape_dirs or {}

    # Per-net terminal cells. A wire may dock at its OWN net's pins (exempt,
    # even though the pin abuts a body in `blocked`), but must never route onto
    # ANOTHER net's pin — so every other net's terminals are blocked.
    term_cells: dict[str, set[tuple[int, int]]] = {
        name: {grid.cell(p) for p in pts} for name, pts in nets.items()
    }
    all_terms: set[tuple[int, int]] = set()
    for cells in term_cells.values():
        all_terms |= cells

    # Route nets with the fewest terminals first (simplest, least contention).
    order = sorted(nets.items(), key=lambda kv: (len(kv[1]), kv[0]))
    laid: dict[str, set[tuple[int, int]]] = {}
    seg_by_net: dict[str, list[tuple[Point, Point]]] = {}
    failures: list[tuple[str, Point]] = []

    for name, pts in order:
        if len(pts) < 2:
            laid[name] = set(term_cells[name])
            seg_by_net[name] = []
            continue
        # Pin escape: a wire leaving a pin is boxed inside ITS OWN symbols'
        # inflated clearance halo. Exempt exactly the cells blocked by this
        # net's own symbols (IC body, its passives, its power symbols) — a wire
        # may traverse its own net's halo (electrically connected anyway) — plus
        # a 1-cell ring around each terminal so a pin abutting its own body can
        # launch. Foreign bodies/pins/wires stay blocked → no foreign crossing.
        own = term_cells[name]
        # Exempt set = the cells this net's wire may occupy even though the
        # static grid blocks them. Two parts:
        #  (a) own symbols' CLEARANCE HALO minus their CORE — a wire may run up
        #      to its own body/passive (validator allows true touch) but never
        #      plow through a body interior (a real wire×symbol overlap).
        #  (b) per-terminal ESCAPE LANE — a terminal cell can quantise INTO its
        #      own body core (pin tip just outside the body in mm rounds inside
        #      after grid+stroke inflation). March outboard from each terminal
        #      until the first genuinely-free cell, exempting that lane so the
        #      pin always reaches routable space. Outboard = away from the
        #      net's centroid (the body side the pin sits on).
        if name in own_obstacles:
            halo = grid.cells_for(own_obstacles[name])
            core = grid.cells_for(own_obstacles[name], clearance_override=0.0)
            exempt = (halo - core)
        else:
            exempt = set()
        free = grid.blocked
        dirs = escape_dirs.get(name)
        pts_here = nets[name]
        cxs = sum(grid.cell(p)[0] for p in pts_here) / len(pts_here)
        cys = sum(grid.cell(p)[1] for p in pts_here) / len(pts_here)
        for i, p in enumerate(pts_here):
            c = grid.cell(p)
            exempt.add(c)
            # Escape step: use the caller-supplied per-terminal outboard
            # direction (the pin's true page side) when given; else fall back
            # to "away from the net centroid".
            if dirs is not None and i < len(dirs) and dirs[i] != (0, 0):
                sx, sy = dirs[i]
            else:
                ddx = c[0] - cxs
                ddy = c[1] - cys
                if abs(ddx) >= abs(ddy):
                    sx, sy = (1 if ddx >= 0 else -1), 0
                else:
                    sx, sy = 0, (1 if ddy >= 0 else -1)
            cx, cy = c
            for _ in range(_ESCAPE_MAX):
                cx, cy = cx + sx, cy + sy
                if not grid.in_bounds((cx, cy)):
                    break
                exempt.add((cx, cy))
                if (cx, cy) not in free:
                    break  # reached free space — lane done
        # Never exempt a FOREIGN terminal (would let a wire land on another
        # net's pin) or foreign-symbol cells that aren't part of this net.
        exempt -= (all_terms - own)
        exempt_fs = frozenset(exempt)

        foreign_cells: set[tuple[int, int]] = all_terms - own
        for other, cells in laid.items():
            if other != name:
                foreign_cells |= cells
        foreign_fs = frozenset(foreign_cells)
        # Congestion: cells ADJACENT to already-routed nets are soft-penalised
        # so this net fans into a parallel track rather than hugging another
        # trunk (the cross-net wire×wire stacking). Exclude this net's own
        # terminals/escape so it can still dock.
        soft_cells: set[tuple[int, int]] = set()
        for c in foreign_cells:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    soft_cells.add((c[0] + dx, c[1] + dy))
        soft_fs = frozenset(soft_cells - exempt)

        tree: set[tuple[int, int]] = {grid.cell(pts[0])}
        segs: list[tuple[Point, Point]] = []
        origin = pts[0]
        remaining = sorted(pts[1:], key=lambda q: abs(q.x - origin.x) + abs(q.y - origin.y))
        for t in remaining:
            path = grid.route(grid.cell(t), tree, foreign=foreign_fs,
                              exempt=exempt_fs, soft=soft_fs)
            if path is None:
                failures.append((name, t))
                continue
            for c in path:
                tree.add(c)
            segs.extend(_cells_to_segments(path, grid))
        laid[name] = tree
        seg_by_net[name] = segs

    wires: list[PlacedWire] = []
    junctions: list[PlacedJunction] = []
    for name, segs in seg_by_net.items():
        merged = _merge_net_segments(segs)
        for a, b in merged:
            if a != b:
                wires.append(PlacedWire(a, b))
        junctions.extend(_net_junctions(merged))

    seen_j: set[tuple[float, float]] = set()
    jout: list[PlacedJunction] = []
    for j in junctions:
        k = (j.position.x, j.position.y)
        if k not in seen_j:
            seen_j.add(k)
            jout.append(j)
    return wires, jout, failures
