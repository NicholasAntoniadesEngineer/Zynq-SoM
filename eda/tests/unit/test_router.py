"""Unit tests for the occupancy-aware orthogonal router.

The router lives in :mod:`zynq_eda.core.route.router`. Tests cover
the three shape categories (direct / single-L / double-L), the
occupancy-aware avoidance behaviour, and the best-effort fallback.
"""

from __future__ import annotations

import pytest

from zynq_eda.core.layout.bbox import BBox
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.grid import Point
from zynq_eda.core.route.router import (
    route_orthogonal,
    route_orthogonal_detail,
)


def _symbol_bbox(min_x: float, min_y: float, max_x: float, max_y: float, owner: str = "obstacle") -> BBox:
    """Construct a fake symbol bbox for collision testing."""
    return BBox(
        min=Point(min_x, min_y),
        max=Point(max_x, max_y),
        kind="symbol",
        owner_id=owner,
    )


# ---- Shape selection -------------------------------------------------------


def test_direct_horizontal_returns_one_segment() -> None:
    """Same-y start/end → single horizontal segment."""
    occupancy = Occupancy()
    result = route_orthogonal_detail(
        Point(10.16, 50.8), Point(50.8, 50.8), occupancy,
    )
    assert result.shape == "direct"
    assert len(result.segments) == 1
    assert result.segments[0].start == Point(10.16, 50.8)
    assert result.segments[0].end == Point(50.8, 50.8)
    assert not result.gave_up


def test_direct_vertical_returns_one_segment() -> None:
    """Same-x start/end → single vertical segment."""
    occupancy = Occupancy()
    result = route_orthogonal_detail(
        Point(50.8, 10.16), Point(50.8, 50.8), occupancy,
    )
    assert result.shape == "direct"
    assert len(result.segments) == 1


def test_single_l_h_when_path_clear() -> None:
    """Diagonal start/end with clear corridor → horizontal-first L-bend."""
    occupancy = Occupancy()
    result = route_orthogonal_detail(
        Point(10.16, 20.32), Point(50.8, 60.96), occupancy,
    )
    assert result.shape == "single_l_h"
    assert len(result.segments) == 2
    # Path: (10.16, 20.32) → (50.8, 20.32) → (50.8, 60.96)
    assert result.segments[0].start == Point(10.16, 20.32)
    assert result.segments[0].end == Point(50.8, 20.32)
    assert result.segments[1].start == Point(50.8, 20.32)
    assert result.segments[1].end == Point(50.8, 60.96)


def test_single_l_v_when_h_blocked() -> None:
    """H-first L-bend blocked by a symbol → vertical-first L-bend chosen."""
    occupancy = Occupancy()
    # Block the horizontal-first corner (50.8, 20.32) — place a symbol
    # whose body sits on the horizontal segment at y=20.32 between
    # x=10.16 and x=50.8.
    occupancy.add(_symbol_bbox(20.0, 18.0, 40.0, 22.0))
    result = route_orthogonal_detail(
        Point(10.16, 20.32), Point(50.8, 60.96), occupancy,
    )
    assert result.shape == "single_l_v"
    assert len(result.segments) == 2
    # Path: (10.16, 20.32) → (10.16, 60.96) → (50.8, 60.96)
    assert result.segments[0].end == Point(10.16, 60.96)


def test_double_l_when_both_single_l_blocked() -> None:
    """Both single-L variants blocked but mid-detour clear → double-L chosen.

    Place obstacles AT both single-L corners (around the source corner
    of each L-bend variant) but leave the midline clear. The double-L
    detours through the midpoint, which sits in the centre of the
    routing area away from the corner obstacles.
    """
    occupancy = Occupancy()
    # Block h-first horizontal segment near the destination corner
    # (the segment y=20.32 from x=10 to 50 passes through x near 50.8).
    occupancy.add(_symbol_bbox(45.0, 18.0, 55.0, 22.0))
    # Block v-first vertical segment near the source corner (x=10.16
    # from y=20 to 60 passes through y near 60).
    occupancy.add(_symbol_bbox(8.0, 55.0, 12.0, 65.0))
    result = route_orthogonal_detail(
        Point(10.16, 20.32), Point(50.8, 60.96), occupancy,
    )
    # Either shape "double_l_h" or "double_l_v" is acceptable — the
    # router tries h-first first.
    assert result.shape in ("double_l_h", "double_l_v")
    assert len(result.segments) >= 2  # may collapse to fewer when a segment is zero-length


def test_giveup_when_everything_blocks() -> None:
    """Pathologically blocked path → router gives up and returns fallback."""
    occupancy = Occupancy()
    # Surround the whole path with obstacles.
    occupancy.add(_symbol_bbox(0.0, 0.0, 100.0, 100.0))
    result = route_orthogonal_detail(
        Point(10.16, 20.32), Point(50.8, 60.96), occupancy,
    )
    assert result.gave_up is True
    assert result.shape == "giveup"
    assert len(result.segments) > 0


# ---- ignore_owners / ignore_kinds ----------------------------------------


def test_ignore_owners_lets_route_through_own_symbol() -> None:
    """Owner ids in avoid_owners are excluded from collision checks."""
    occupancy = Occupancy()
    # A symbol "myself" that would otherwise block the path.
    occupancy.add(_symbol_bbox(20.0, 18.0, 40.0, 22.0, owner="myself"))
    result = route_orthogonal_detail(
        Point(10.16, 20.32), Point(50.8, 60.96), occupancy,
        avoid_owners=frozenset({"myself"}),
    )
    # The h-first L should work because we ignore "myself".
    assert result.shape == "single_l_h"


def test_avoid_kinds_lets_route_through_wire() -> None:
    """Bbox kinds outside avoid_kinds are not obstacles."""
    occupancy = Occupancy()
    # A wire bbox in the path — by default it's not in avoid_kinds.
    wire_bbox = BBox(
        min=Point(20.0, 18.0),
        max=Point(40.0, 22.0),
        kind="wire",
        owner_id="prior_wire",
    )
    occupancy.add(wire_bbox)
    result = route_orthogonal_detail(
        Point(10.16, 20.32), Point(50.8, 60.96), occupancy,
    )
    # Wires don't block the h-first L (wires are in skip-kinds).
    assert result.shape == "single_l_h"


# ---- Trivial cases --------------------------------------------------------


def test_same_point_returns_empty_segments() -> None:
    """start == end → zero-length route returns empty segments."""
    occupancy = Occupancy()
    result = route_orthogonal_detail(
        Point(50.8, 50.8), Point(50.8, 50.8), occupancy,
    )
    assert result.shape == "zero_length"
    assert result.segments == ()


def test_public_route_orthogonal_returns_list() -> None:
    """The simpler :func:`route_orthogonal` returns the same segments as a list."""
    occupancy = Occupancy()
    segments = route_orthogonal(
        Point(10.16, 50.8), Point(50.8, 50.8), occupancy,
    )
    assert isinstance(segments, list)
    assert len(segments) == 1
    assert segments[0].start == Point(10.16, 50.8)
