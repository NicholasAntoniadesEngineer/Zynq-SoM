"""Tests for BoundingBox geometry: containment, intersection, expansion."""

from __future__ import annotations

import pytest

from scripts.carrier.core.geometry import BoundingBox
from scripts.carrier.core.sexpr import Point


def make_box(left: float, top: float, right: float, bottom: float) -> BoundingBox:
    return BoundingBox(Point(left, top), Point(right, bottom))


class TestBoundingBoxConstruction:
    def test_dimensions(self) -> None:
        box = make_box(0.0, 0.0, 10.0, 5.0)
        assert box.width_mm == 10.0
        assert box.height_mm == 5.0
        assert box.center == Point(5.0, 2.5)

    def test_inverted_corners_raises(self) -> None:
        with pytest.raises(ValueError, match="top_left.x"):
            BoundingBox(Point(10.0, 0.0), Point(0.0, 5.0))
        with pytest.raises(ValueError, match="top_left.y"):
            BoundingBox(Point(0.0, 5.0), Point(10.0, 0.0))


class TestBoundingBoxContains:
    def test_interior_point_contained(self) -> None:
        box = make_box(0.0, 0.0, 10.0, 5.0)
        assert box.contains(Point(5.0, 2.5)) is True

    def test_corner_points_contained(self) -> None:
        box = make_box(0.0, 0.0, 10.0, 5.0)
        assert box.contains(Point(0.0, 0.0)) is True
        assert box.contains(Point(10.0, 5.0)) is True

    def test_exterior_point_excluded(self) -> None:
        box = make_box(0.0, 0.0, 10.0, 5.0)
        assert box.contains(Point(15.0, 2.5)) is False
        assert box.contains(Point(-1.0, 2.5)) is False


class TestBoundingBoxExpand:
    def test_expands_outward_uniformly(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        expanded = box.expand(2.0)
        assert expanded == make_box(3.0, 3.0, 12.0, 12.0)

    def test_zero_margin_is_identity(self) -> None:
        box = make_box(0.0, 0.0, 10.0, 10.0)
        assert box.expand(0.0) == box


class TestBoundingBoxIntersectsSegment:
    def test_horizontal_segment_through_interior(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(0.0, 7.5), Point(15.0, 7.5)) is True

    def test_horizontal_segment_clearing_above(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(0.0, 1.0), Point(15.0, 1.0)) is False

    def test_horizontal_segment_clearing_below(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(0.0, 12.0), Point(15.0, 12.0)) is False

    def test_horizontal_segment_touching_top_edge_does_not_count(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(0.0, 5.0), Point(15.0, 5.0)) is False

    def test_vertical_segment_through_interior(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(7.5, 0.0), Point(7.5, 15.0)) is True

    def test_vertical_segment_clearing_left(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(2.0, 0.0), Point(2.0, 15.0)) is False

    def test_vertical_segment_touching_left_edge_does_not_count(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        assert box.intersects_segment(Point(5.0, 0.0), Point(5.0, 15.0)) is False

    def test_diagonal_segment_raises(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        with pytest.raises(ValueError, match="orthogonal"):
            box.intersects_segment(Point(0.0, 0.0), Point(15.0, 15.0))

    def test_float_precision_wobble_tolerated(self) -> None:
        box = make_box(5.0, 5.0, 10.0, 10.0)
        wobbled_y = 7.5 + 1e-9
        assert box.intersects_segment(Point(0.0, 7.5), Point(15.0, wobbled_y)) is True
