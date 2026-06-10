"""Unit tests for the bounded grid A* router.

Assert the properties that make A* the right replacement for the
shape-ladder: it connects endpoints, detours around obstacles while
respecting clearance, reports honest failure (None) when boxed in, and —
being a grid search — terminates fast on long routes (bounded by
construction; these tests would hang under the old ladder's candidate
explosion if it regressed back in).
"""

from __future__ import annotations

from zynq_eda.core.layout.bbox import BBox
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.grid import Point
from zynq_eda.core.route.astar import route_astar

KINDS = frozenset({"symbol"})


def _occ(*bboxes: BBox) -> Occupancy:
    o = Occupancy()
    for b in bboxes:
        o.add(b)
    return o


def _sym(x0: float, y0: float, x1: float, y1: float, owner: str = "symbol:X") -> BBox:
    return BBox(min=Point(x0, y0), max=Point(x1, y1), kind="symbol", owner_id=owner)


def _connected(segs, start: Point, end: Point) -> bool:
    if not segs:
        return False
    if (segs[0].start.x, segs[0].start.y) != (start.x, start.y):
        return False
    if (segs[-1].end.x, segs[-1].end.y) != (end.x, end.y):
        return False
    for a, b in zip(segs, segs[1:]):
        if (a.end.x, a.end.y) != (b.start.x, b.start.y):
            return False
    return True


def test_clear_horizontal_route_connects() -> None:
    segs = route_astar(
        Point(0, 0), Point(20.32, 0), _occ(),
        avoid_kinds=KINDS, clearance_mm=2.0,
    )
    assert segs is not None
    assert _connected(segs, Point(0, 0), Point(20.32, 0))


def test_detours_around_blocking_symbol() -> None:
    # A body straddling the straight y=0 path between the endpoints.
    occ = _occ(_sym(7.62, -5.08, 12.7, 5.08))
    start, end = Point(0, 0), Point(20.32, 0)
    segs = route_astar(start, end, occ, avoid_kinds=KINDS, clearance_mm=2.0)
    assert segs is not None
    assert _connected(segs, start, end)
    # It had to leave the straight line ⇒ at least one vertical segment.
    assert any(s.start.x == s.end.x for s in segs)
    # No vertex sits within the body+clearance band (2 mm).
    for s in segs:
        for p in (s.start, s.end):
            inside = (7.62 - 2.0) < p.x < (12.7 + 2.0) and (-5.08 - 2.0) < p.y < (5.08 + 2.0)
            assert not inside, f"vertex {p} sits inside the obstacle clearance band"


def test_boxed_in_returns_none() -> None:
    # A wall spanning the whole search-window height between the endpoints.
    occ = _occ(_sym(63.5, -10.0, 66.04, 160.0))
    segs = route_astar(
        Point(50.8, 50.8), Point(81.28, 50.8), occ,
        avoid_kinds=KINDS, clearance_mm=2.0,
    )
    assert segs is None


def test_long_route_is_bounded_and_fast() -> None:
    # Would explode the old ladder; A* returns quickly (test would time out
    # if it looped). Just assert it connects.
    segs = route_astar(
        Point(0, 0), Point(203.2, 152.4), _occ(),
        avoid_kinds=KINDS, clearance_mm=2.0,
    )
    assert segs is not None
    assert _connected(segs, Point(0, 0), Point(203.2, 152.4))


def test_same_point_returns_empty() -> None:
    segs = route_astar(
        Point(10.16, 10.16), Point(10.16, 10.16), _occ(),
        avoid_kinds=KINDS, clearance_mm=2.0,
    )
    assert segs == []
