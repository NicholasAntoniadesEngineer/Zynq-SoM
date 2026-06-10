"""Exact node-overlap removal for axis-aligned rectangles.

Schematic placement must guarantee ZERO overlap and at least
``VISUAL_CLEARANCE_MM`` of breathing room between every pair of drawn
rectangles — a hard Law, no tolerance, and density is solved by spreading
out, never by relaxing the rule. This module is the spreading primitive.

Algorithm (Dwyer, Marriott & Stuckey 2005, "Fast Node Overlap Removal"):

  1. Generate separation constraints only between rectangles that overlap
     (within the gap) on the *other* axis, oriented by current centre order
     so the constraint graph is a DAG (i is left/above j ⇒ ``c_j >= c_i + sep``).
  2. Satisfy them EXACTLY with a topological (centre-order) sweep: visiting
     nodes in order, each is pushed just past its already-placed
     predecessors. This is the longest-path solution — feasible by
     construction in a single pass, no iteration, no tolerance.

X is resolved first; Y constraints are then generated only for pairs that
still overlap horizontally, biasing toward small horizontal nudges. The
result is re-centred on the original centroid (overlap-invariant) so the
layout doesn't drift, and every centre is snapped to the KiCad grid with
separations rounded UP so grid-snapping can never reintroduce crowding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from zynq_eda.core.layout._constants import KICAD_GRID_MM, VISUAL_CLEARANCE_MM


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle by centre + full width/height."""

    cx: float
    cy: float
    w: float
    h: float


def _round_up_to_grid(value: float, grid: float = KICAD_GRID_MM) -> float:
    """Round a (positive) separation UP to a grid multiple."""
    return math.ceil(value / grid - 1e-9) * grid


def _solve_axis(
    centers: list[float],
    half: list[float],
    cross_centers: list[float],
    cross_half: list[float],
    movable: list[bool],
    gap: float,
    cross_gap: float,
) -> list[float]:
    """Resolve overlaps along ONE axis.

    ``centers``/``half`` are the working axis; ``cross_*`` the other axis,
    used only to decide which pairs actually overlap (and therefore need a
    constraint). Returns new centres on the working axis. Fixed nodes
    (``movable[i] is False``) are never moved; their movable neighbours are
    pushed instead.
    """
    n = len(centers)
    order = sorted(range(n), key=lambda i: (centers[i], i))
    pos = list(centers)
    # Process in centre order; each node is pushed past every earlier node it
    # would overlap. Constraints are oriented by this order ⇒ acyclic, so one
    # forward sweep satisfies them all.
    for a in range(n):
        j = order[a]
        for b in range(a):
            i = order[b]
            # Do these two overlap on the CROSS axis (within the cross gap)?
            cross_sep = cross_half[i] + cross_half[j] + cross_gap
            if abs(cross_centers[i] - cross_centers[j]) >= cross_sep:
                continue  # clear on the other axis ⇒ no working-axis constraint
            need = half[i] + half[j] + gap
            need = _round_up_to_grid(need)
            if pos[j] - pos[i] >= need:
                continue
            # Push j right (past i). If j is fixed, push i left instead; if
            # both fixed, they cannot be separated on this axis (the caller's
            # other-axis pass must handle them).
            deficit = need - (pos[j] - pos[i])
            if movable[j]:
                pos[j] += deficit
            elif movable[i]:
                pos[i] -= deficit
            # both fixed: leave to the other axis.
    return pos


def remove_overlaps(
    rects: list[Rect],
    *,
    gap: float = VISUAL_CLEARANCE_MM,
    movable: list[bool] | None = None,
) -> list[tuple[float, float]]:
    """Return new ``(cx, cy)`` centres so no two rects are within ``gap``.

    ``gap`` is the required edge-to-edge clearance (the Laws' breathing
    room). The returned layout is re-centred on the input centroid so it
    does not drift, and every centre lies on the KiCad grid. Fixed rects
    (``movable[i] is False``) keep their centres.
    """
    n = len(rects)
    if n <= 1:
        return [(r.cx, r.cy) for r in rects]
    if movable is None:
        movable = [True] * n

    cx = [r.cx for r in rects]
    cy = [r.cy for r in rects]
    hw = [r.w / 2.0 for r in rects]
    hh = [r.h / 2.0 for r in rects]

    # X first, then Y (Y only matters for pairs still overlapping in X).
    new_cx = _solve_axis(cx, hw, cy, hh, movable, gap, gap)
    new_cy = _solve_axis(cy, hh, new_cx, hw, movable, gap, gap)

    # Re-centre on the original centroid (overlap-invariant uniform
    # translation) to undo the forward sweep's global +x/+y drift, so the
    # spread stays put on the page. ONLY when every node is movable — any
    # fixed node already anchors the frame, and re-centring would drag the
    # movable nodes back onto it.
    if all(movable):
        for axis_old, axis_new in ((cx, new_cx), (cy, new_cy)):
            old_c = sum(axis_old) / n
            cur_c = sum(axis_new) / n
            # snap the shift to grid so re-centred coords stay on-grid
            shift = round((old_c - cur_c) / KICAD_GRID_MM) * KICAD_GRID_MM
            for i in range(n):
                axis_new[i] += shift

    return [(new_cx[i], new_cy[i]) for i in range(n)]
