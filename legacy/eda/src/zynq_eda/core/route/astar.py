"""Bounded grid A* orthogonal router.

The legacy shape-ladder router (:func:`route_orthogonal_detail`) enumerates
thousands of pre-shaped detour candidates and collision-checks each; on dense
or separated geometry that explodes into a multi-second stall (effectively a
hang). This router instead does an A* search on the KiCad grid: every cell is
expanded at most once, so it is **bounded by construction** — it physically
cannot loop — and it is complete (if a grid-aligned orthogonal path exists, it
finds one), with a turn penalty so it prefers few-bend routes.

Obstacles are rasterized into blocked cells using the SAME two-tier clearance
the validator and the legacy router use (2 mm around symbols / labels / text,
:data:`WIRE_VS_WIRE_CLEARANCE_MM` around wires), so a route this finds is a
route the validator agrees is clean. The search is confined to the bounding
box of the endpoints plus a margin, keeping the grid small and the search
fast; callers fall back to the ladder if A* finds nothing in that window.
"""

from __future__ import annotations

import heapq

from zynq_eda.core.layout._constants import (
    KICAD_GRID_MM,
    WIRE_THICKNESS_MM,
    WIRE_VS_WIRE_CLEARANCE_MM,
)
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import PlacedWire

_GRID = KICAD_GRID_MM
# A turn costs this many grid-steps of extra length, so the router prefers
# straight runs and few bends (the hand-drawn look) without refusing to detour.
_TURN_PENALTY_MM = 3.0 * _GRID
# How far outside the endpoints' bounding box the search may roam. Routes
# rarely need to detour further; if they do, the caller's ladder fallback
# handles it. Keeps the grid (and the search) small.
_MARGIN_MM = 40.0
# Page extent clamp (A3 is the largest paper used). Generous; just a backstop.
_PAGE_MAX_MM = 600.0

# Directions: (dx, dy) in cells. 4-connected orthogonal.
_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _blocked_cells(
    occupancy,
    ignore_owners: frozenset[str],
    avoid_kinds: frozenset[str],
    clearance_mm: float,
    ox: float,
    oy: float,
    nx: int,
    ny: int,
) -> set[tuple[int, int]]:
    """Rasterize every obstacle into the set of grid cells a wire centerline
    may not occupy. Per-kind clearance matches the validator's two regimes."""
    blocked: set[tuple[int, int]] = set()
    half_wire = WIRE_THICKNESS_MM / 2.0
    for bbox in occupancy:
        if bbox.kind not in avoid_kinds:
            continue
        if bbox.owner_id in ignore_owners:
            continue
        clr = WIRE_VS_WIRE_CLEARANCE_MM if bbox.kind == "wire" else clearance_mm
        infl = clr + half_wire
        # Cell range whose centre falls within the inflated obstacle.
        ix_lo = max(0, int((bbox.min.x - infl - ox) / _GRID) + 1)
        ix_hi = min(nx - 1, int((bbox.max.x + infl - ox) / _GRID))
        iy_lo = max(0, int((bbox.min.y - infl - oy) / _GRID) + 1)
        iy_hi = min(ny - 1, int((bbox.max.y + infl - oy) / _GRID))
        for ix in range(ix_lo, ix_hi + 1):
            for iy in range(iy_lo, iy_hi + 1):
                blocked.add((ix, iy))
    return blocked


def route_astar(
    start: Point,
    end: Point,
    occupancy,
    *,
    avoid_owners: frozenset[str] = frozenset(),
    avoid_kinds: frozenset[str],
    clearance_mm: float,
    forbidden_traversal_points: frozenset[tuple[float, float]] = frozenset(),
) -> list[PlacedWire] | None:
    """Route ``start → end`` orthogonally on the grid, or ``None`` if no
    clean path exists within the search window. Result is grid-aligned
    PlacedWire segments (maximal straight runs)."""
    sx, sy = snap_to_grid(start.x), snap_to_grid(start.y)
    ex, ey = snap_to_grid(end.x), snap_to_grid(end.y)
    if sx == ex and sy == ey:
        return []

    # Search window: endpoints' bbox + margin, clamped to a sane page extent.
    lo_x = max(0.0, min(sx, ex) - _MARGIN_MM)
    lo_y = max(0.0, min(sy, ey) - _MARGIN_MM)
    hi_x = min(_PAGE_MAX_MM, max(sx, ex) + _MARGIN_MM)
    hi_y = min(_PAGE_MAX_MM, max(sy, ey) + _MARGIN_MM)
    ox = snap_to_grid(lo_x)
    oy = snap_to_grid(lo_y)
    nx = int((hi_x - ox) / _GRID) + 2
    ny = int((hi_y - oy) / _GRID) + 2

    def cell(px: float, py: float) -> tuple[int, int]:
        return (round((px - ox) / _GRID), round((py - oy) / _GRID))

    start_c = cell(sx, sy)
    end_c = cell(ex, ey)
    if not (0 <= start_c[0] < nx and 0 <= start_c[1] < ny):
        return None
    if not (0 <= end_c[0] < nx and 0 <= end_c[1] < ny):
        return None

    blocked = _blocked_cells(
        occupancy, avoid_owners, avoid_kinds, clearance_mm, ox, oy, nx, ny
    )
    # Endpoints are always walkable (a wire legitimately terminates at the pin
    # it connects to, even though that pin's body sits in an obstacle).
    blocked.discard(start_c)
    blocked.discard(end_c)
    for fx, fy in forbidden_traversal_points:
        fc = cell(fx, fy)
        if fc != start_c and fc != end_c:
            blocked.add(fc)

    # A* with state = (cell, incoming_direction_index). Cost in mm.
    start_state = (start_c[0], start_c[1], -1)
    g_best: dict[tuple[int, int, int], float] = {start_state: 0.0}
    heap: list[tuple[float, tuple[int, int, int]]] = []
    h0 = (abs(start_c[0] - end_c[0]) + abs(start_c[1] - end_c[1])) * _GRID
    heapq.heappush(heap, (h0, start_state))
    came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}

    goal_state: tuple[int, int, int] | None = None
    while heap:
        _f, state = heapq.heappop(heap)
        cx, cy, cdir = state
        if (cx, cy) == end_c:
            goal_state = state
            break
        g = g_best[state]
        for di, (dx, dy) in enumerate(_DIRS):
            ncx, ncy = cx + dx, cy + dy
            if not (0 <= ncx < nx and 0 <= ncy < ny):
                continue
            if (ncx, ncy) in blocked:
                continue
            step = _GRID + (_TURN_PENALTY_MM if cdir != -1 and di != cdir else 0.0)
            ng = g + step
            nstate = (ncx, ncy, di)
            if ng < g_best.get(nstate, float("inf")):
                g_best[nstate] = ng
                came_from[nstate] = state
                h = (abs(ncx - end_c[0]) + abs(ncy - end_c[1])) * _GRID
                heapq.heappush(heap, (ng + h, nstate))

    if goal_state is None:
        return None

    # Reconstruct the cell path, then collapse to maximal straight segments.
    cells: list[tuple[int, int]] = []
    s = goal_state
    while True:
        cells.append((s[0], s[1]))
        if s == start_state:
            break
        s = came_from[s]
    cells.reverse()

    pts = [Point(snap_to_grid(ox + ix * _GRID), snap_to_grid(oy + iy * _GRID))
           for ix, iy in cells]
    segments: list[PlacedWire] = []
    run_start = pts[0]
    for i in range(1, len(pts)):
        cur = pts[i]
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        # Close the run at a direction change or the final point.
        turning = nxt is not None and not _collinear(run_start, cur, nxt)
        if nxt is None or turning:
            if run_start.x != cur.x or run_start.y != cur.y:
                segments.append(PlacedWire(start=run_start, end=cur))
            run_start = cur
    return segments


def _collinear(a: Point, b: Point, c: Point) -> bool:
    """True if a→b→c continue in the same orthogonal direction."""
    return (a.x == b.x == c.x) or (a.y == b.y == c.y)
