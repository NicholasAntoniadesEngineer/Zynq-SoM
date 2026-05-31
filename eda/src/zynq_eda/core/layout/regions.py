"""Region-partition placement: spread units across the whole page.

The chronic crowding came from packing every IC + its passives into a tight
left column and connectors into edge columns, leaving most of the A3 empty.
This module replaces that with a spread-to-fill partition: the usable page is
divided into a coarse grid of regions, one per *unit* (an IC together with its
supporting passives, or a connector), and each unit is given a whole region to
breathe in. Components fill the page uniformly with generous separation, which
is what makes zero-crowding achievable — density is solved by using the page,
never by tolerating closeness.

This module is pure geometry (no planner imports): it takes the units' required
footprint sizes and returns a :class:`Region` box per unit. The planner
(:func:`zynq_eda.core.layout.plan.plan_anchors`) computes the footprints from
real symbol/lane geometry, calls :func:`partition_and_assign`, and positions
each anchor inside its region.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    """An axis-aligned page region (mm) a unit is laid out within."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


@dataclass(frozen=True)
class Unit:
    """One placeable unit: an IC+cluster or a connector.

    ``w`` / ``h`` are the unit's required footprint (body + its outboard lane
    extents) in mm. ``edge`` biases a connector to the left/right side of the
    page (``"left"`` / ``"right"``); ICs use ``None``.
    """

    ref: str
    w: float
    h: float
    edge: str | None = None


def _choose_grid(n: int, uw: float, uh: float, max_w: float, max_h: float) -> tuple[int, int]:
    """Pick (cols, rows) that hold ``n`` units, each region >= the largest
    footprint, biased to the page aspect so the grid fills the page."""
    if n <= 1:
        return (1, 1)
    max_cols = max(1, int(uw / max_w)) if max_w > 0 else n
    max_rows = max(1, int(uh / max_h)) if max_h > 0 else n
    # Aspect-biased square-ish target.
    cols = max(1, min(max_cols, round(math.sqrt(n * uw / uh)))) if uh > 0 else n
    rows = math.ceil(n / cols)
    if rows > max_rows:
        rows = max_rows
        cols = math.ceil(n / rows)
    cols = max(1, cols)
    rows = max(1, rows)
    # Guarantee capacity, growing whichever dimension still has page room.
    while cols * rows < n:
        if cols < max_cols:
            cols += 1
        elif rows < max_rows:
            rows += 1
        else:
            cols += 1  # last resort: overflow (caller's footprints too big)
    return (cols, rows)


def partition_and_assign(
    units: list[Unit],
    paper_w: float,
    paper_h: float,
    margin: float,
) -> dict[str, Region]:
    """Return a :class:`Region` per unit, spreading them to fill the page.

    Units are ordered left-edge connectors → ICs → right-edge connectors and
    filled column-major, so connectors land on their declared side and ICs in
    between. Each region is identical in size (page-filling); the planner
    centres each unit's footprint within its region.
    """
    if not units:
        return {}

    ux0, uy0 = margin, margin
    uw = paper_w - 2.0 * margin
    uh = paper_h - 2.0 * margin
    n = len(units)
    max_w = max(u.w for u in units)
    max_h = max(u.h for u in units)
    cols, rows = _choose_grid(n, uw, uh, max_w, max_h)

    region_w = uw / cols
    region_h = uh / rows

    left = [u for u in units if u.edge == "left"]
    right = [u for u in units if u.edge == "right"]
    middle = [u for u in units if u.edge not in ("left", "right")]
    ordered = left + middle + right

    assignment: dict[str, Region] = {}
    for idx, unit in enumerate(ordered):
        c = min(idx // rows, cols - 1)
        r = idx % rows
        x0 = ux0 + c * region_w
        y0 = uy0 + r * region_h
        assignment[unit.ref] = Region(x0, y0, x0 + region_w, y0 + region_h)
    return assignment
