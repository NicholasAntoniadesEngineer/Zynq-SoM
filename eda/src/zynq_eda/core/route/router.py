"""Minimal occupancy-aware orthogonal wire router.

This module produces a sequence of one to three axis-aligned wire
segments connecting two grid-aligned points, attempting to avoid
colliding with bboxes already registered in an
:class:`~zynq_eda.core.layout.occupancy.Occupancy` index. The router
is deliberately simple: it tries a fixed ladder of routing shapes
(direct → single-L → double-L) and returns the first that doesn't
collide. There is no A* search and no rip-up; if every candidate
collides, the router returns a best-effort single-L route and a flag
the caller can log.

Why this design:

  * The cross-cluster wires Wave B targets (power-symbol stubs,
    signal-override stubs, the few GND attachments routed BETWEEN
    clusters rather than INSIDE them) are short. Most fit a direct
    H or V segment; nearly all fit a single L-bend.
  * The occupancy index already classifies bboxes by kind, so the
    router can ignore junctions / labels and only collide-check
    against symbol bodies + other wires.
  * A real router (A*, channel routing) would belong in a separate
    Wave; the current goal is just to stop routing THROUGH symbol
    bodies, not to optimise routing topology.

Public API: :func:`route_orthogonal`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from zynq_eda.core.layout.bbox import BBox, BBoxKind, wire_bbox
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import PlacedWire


# ---- Defaults --------------------------------------------------------------

DEFAULT_AVOID_KINDS: frozenset[BBoxKind] = frozenset(
    {"symbol", "label", "hierarchical_label", "sheet"}
)
"""Bbox kinds the router avoids by default.

Wires (other than this route) are NOT in this set so the router happily
crosses other wires at 90° (which KiCad merges at the crossing point if
a junction is placed). Junctions/no-connects are tiny markers that don't
participate in collision checks.
"""

DEFAULT_CLEARANCE_MM: float = 0.5
"""Default clearance margin when collide-checking each candidate segment."""


# ---- Result type -----------------------------------------------------------

@dataclass(frozen=True)
class RouteResult:
    """Outcome of a routing attempt.

    Attributes:
        segments: Ordered list of placed wires forming the route.
            Always non-empty; even a giveup returns the best-effort
            single-L attempt.
        gave_up: True iff every candidate shape collided with the
            occupancy index and the router returned a best-effort
            fallback. The caller may want to log this for diagnostics.
        shape: Human-readable name of the shape that was picked:
            ``"direct"``, ``"single_l_h"``, ``"single_l_v"``,
            ``"double_l_h"``, ``"double_l_v"``, or ``"giveup"``.
    """

    segments: tuple[PlacedWire, ...]
    gave_up: bool
    shape: str


# ---- Internal helpers ------------------------------------------------------

def _make_wire(start: Point, end: Point) -> PlacedWire | None:
    """Return a PlacedWire iff start != end (filters zero-length segments)."""
    if start.x == end.x and start.y == end.y:
        return None
    return PlacedWire(start=start, end=end)


def _segments_collide(
    segments: Sequence[PlacedWire],
    occupancy: Occupancy,
    ignore_owners: frozenset[str],
    avoid_kinds: frozenset[BBoxKind],
    clearance_mm: float,
) -> bool:
    """True iff any segment's bbox collides with the occupancy index.

    Each segment is widened by its wire-bbox clearance (already baked
    into :func:`wire_bbox`) plus the additional ``clearance_mm`` padding.
    Bboxes whose kind is NOT in ``avoid_kinds`` are skipped wholesale
    (e.g. other wires are crossed freely).
    """
    skip_kinds = frozenset(
        kind for kind in (
            "symbol", "label", "hierarchical_label", "sheet_pin",
            "wire", "no_connect", "junction", "sheet",
        ) if kind not in avoid_kinds
    )
    for segment in segments:
        bbox = wire_bbox(segment.start, segment.end, owner_id="_router_probe")
        hits = occupancy.collides(
            bbox,
            ignore_owners=ignore_owners,
            ignore_kinds=skip_kinds,
            padding_mm=clearance_mm,
        )
        if hits:
            return True
    return False


def _direct(start: Point, end: Point) -> tuple[PlacedWire, ...] | None:
    """Single straight segment if start and end share an axis."""
    if start.x == end.x or start.y == end.y:
        wire = _make_wire(start, end)
        if wire is None:
            return ()
        return (wire,)
    return None


def _single_l(
    start: Point, end: Point, horizontal_first: bool,
) -> tuple[PlacedWire, ...]:
    """Two-segment L-bend.

    ``horizontal_first=True`` → start → (end.x, start.y) → end
    ``horizontal_first=False`` → start → (start.x, end.y) → end
    """
    if horizontal_first:
        corner = Point(end.x, start.y)
    else:
        corner = Point(start.x, end.y)
    segments: list[PlacedWire] = []
    seg_a = _make_wire(start, corner)
    seg_b = _make_wire(corner, end)
    if seg_a is not None:
        segments.append(seg_a)
    if seg_b is not None:
        segments.append(seg_b)
    return tuple(segments)


def _double_l(
    start: Point, end: Point, horizontal_first: bool,
) -> tuple[PlacedWire, ...]:
    """Three-segment double-L (Z) detour through a midpoint.

    ``horizontal_first=True`` → goes H then V then H via mx = (start.x+end.x)/2.
    ``horizontal_first=False`` → goes V then H then V via my = (start.y+end.y)/2.
    """
    if horizontal_first:
        mx = snap_to_grid((start.x + end.x) / 2.0)
        c1 = Point(mx, start.y)
        c2 = Point(mx, end.y)
    else:
        my = snap_to_grid((start.y + end.y) / 2.0)
        c1 = Point(start.x, my)
        c2 = Point(end.x, my)
    segments: list[PlacedWire] = []
    for s, e in ((start, c1), (c1, c2), (c2, end)):
        wire = _make_wire(s, e)
        if wire is not None:
            segments.append(wire)
    return tuple(segments)


# ---- Public entry point ----------------------------------------------------

def route_orthogonal(
    start: Point,
    end: Point,
    occupancy: Occupancy,
    *,
    avoid_owners: frozenset[str] = frozenset(),
    avoid_kinds: frozenset[BBoxKind] = DEFAULT_AVOID_KINDS,
    clearance_mm: float = DEFAULT_CLEARANCE_MM,
) -> list[PlacedWire]:
    """Route ``start → end`` orthogonally avoiding bboxes in ``occupancy``.

    Strategy (first non-colliding shape wins):

      1. **Direct** — if ``start.x == end.x`` (vertical) or
         ``start.y == end.y`` (horizontal), emit one segment.
      2. **Single L-bend, horizontal-first** —
         ``start → (end.x, start.y) → end``.
      3. **Single L-bend, vertical-first** —
         ``start → (start.x, end.y) → end``.
      4. **Double L, horizontal-first** — detour through
         ``mx = (start.x + end.x) / 2``.
      5. **Double L, vertical-first** — detour through
         ``my = (start.y + end.y) / 2``.

    For each candidate shape, every segment's bbox is collide-checked
    against the occupancy index. The first shape whose segments are
    ALL collision-free is returned. If every shape collides, the
    function returns the vertical-first single-L as a best-effort
    fallback — the result is still electrically correct, it just may
    cross a symbol body. Callers wanting to know about giveups should
    use :func:`route_orthogonal_detail` instead.

    Args:
        start: Grid-aligned source point.
        end: Grid-aligned target point.
        occupancy: Live spatial index built up during placement.
        avoid_owners: Owner ids to ignore during collision checks
            (e.g. the source / destination symbol's own bbox — their
            pin stubs would otherwise collide with the new wire).
        avoid_kinds: Bbox kinds to treat as obstacles. Defaults to
            ``DEFAULT_AVOID_KINDS`` (symbols + labels + sheet symbols).
            Wires/junctions/no-connects are crossed freely.
        clearance_mm: Extra clearance applied around each candidate
            segment's bbox during collision checks.

    Returns:
        Ordered list of :class:`PlacedWire` segments forming the
        route. Always non-empty (a same-point query returns ``[]``
        which is treated as a no-op by callers).
    """
    return route_orthogonal_detail(
        start, end, occupancy,
        avoid_owners=avoid_owners,
        avoid_kinds=avoid_kinds,
        clearance_mm=clearance_mm,
    ).segments_as_list()


def route_orthogonal_detail(
    start: Point,
    end: Point,
    occupancy: Occupancy,
    *,
    avoid_owners: frozenset[str] = frozenset(),
    avoid_kinds: frozenset[BBoxKind] = DEFAULT_AVOID_KINDS,
    clearance_mm: float = DEFAULT_CLEARANCE_MM,
) -> "RouteAttempt":
    """Same as :func:`route_orthogonal` but exposes the picked shape.

    Useful for diagnostics — the caller can log which shape was used
    or whether the router gave up. The wire segments are otherwise
    identical to what :func:`route_orthogonal` returns.
    """
    # Trivial: same point.
    if start.x == end.x and start.y == end.y:
        return RouteAttempt(
            segments=(),
            gave_up=False,
            shape="zero_length",
        )

    candidates: list[tuple[str, tuple[PlacedWire, ...]]] = []

    # 1. Direct.
    direct = _direct(start, end)
    if direct is not None:
        candidates.append(("direct", direct))

    # 2-3. Single-L (two variants).
    candidates.append(("single_l_h", _single_l(start, end, horizontal_first=True)))
    candidates.append(("single_l_v", _single_l(start, end, horizontal_first=False)))

    # 4-5. Double-L (two variants).
    candidates.append(("double_l_h", _double_l(start, end, horizontal_first=True)))
    candidates.append(("double_l_v", _double_l(start, end, horizontal_first=False)))

    # Pick the first shape whose every segment is clear.
    for shape, segments in candidates:
        if not segments:
            continue
        if not _segments_collide(
            segments, occupancy, avoid_owners, avoid_kinds, clearance_mm,
        ):
            return RouteAttempt(segments=segments, gave_up=False, shape=shape)

    # Best-effort fallback: vertical-first single-L. Better than
    # nothing — electrically still correct, just may cross a body.
    fallback = _single_l(start, end, horizontal_first=False)
    if not fallback:
        fallback = _single_l(start, end, horizontal_first=True)
    return RouteAttempt(segments=fallback, gave_up=True, shape="giveup")


@dataclass(frozen=True)
class RouteAttempt:
    """Detailed result of a routing attempt.

    Returned by :func:`route_orthogonal_detail` (the public alternative
    to :func:`route_orthogonal` that exposes which shape the router
    chose). For callers that only want the wires,
    :func:`route_orthogonal` returns the segments directly.
    """

    segments: tuple[PlacedWire, ...]
    gave_up: bool
    shape: str

    def segments_as_list(self) -> list[PlacedWire]:
        return list(self.segments)
