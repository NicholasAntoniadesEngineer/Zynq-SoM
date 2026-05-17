"""Tests for Manhattan routing in core/geometry.py.

Covers:
    - Direct (single-segment) routing for aligned points
    - L-shaped routing with the AUTO heuristic and explicit direction modes
    - Junction emission at the corner
    - Obstacle avoidance via L-shape secondary direction and U-shape fallback
    - validate_routing_result rejects non-orthogonal / disconnected results
    - detect_t_intersections finds the right interior endpoints
"""

from __future__ import annotations

import pytest

from scripts.carrier.core.geometry import (
    BoundingBox,
    CornerDirection,
    create_orthogonal_routing,
    detect_t_intersections,
    validate_routing_result,
)
from scripts.carrier.core.sexpr import Point


def make_box(left: float, top: float, right: float, bottom: float) -> BoundingBox:
    return BoundingBox(Point(left, top), Point(right, bottom))


class TestDirectRouting:
    def test_horizontal_alignment_yields_single_segment(self) -> None:
        result = create_orthogonal_routing(Point(0.0, 0.0), Point(10.16, 0.0))
        assert len(result.segments) == 1
        assert result.is_direct is True
        assert result.corner is None
        assert result.junctions == ()

    def test_vertical_alignment_yields_single_segment(self) -> None:
        result = create_orthogonal_routing(Point(0.0, 0.0), Point(0.0, 5.08))
        assert len(result.segments) == 1
        assert result.is_direct is True


class TestLShapeRouting:
    def test_auto_chooses_horizontal_when_dx_geq_dy(self) -> None:
        result = create_orthogonal_routing(
            Point(0.0, 0.0), Point(20.32, 5.08),
            direction=CornerDirection.AUTO,
        )
        assert result.is_direct is False
        assert result.corner == Point(20.32, 0.0)
        assert len(result.segments) == 2
        assert len(result.junctions) == 1
        assert result.junctions[0] == Point(20.32, 0.0)

    def test_auto_chooses_vertical_when_dy_gt_dx(self) -> None:
        result = create_orthogonal_routing(
            Point(0.0, 0.0), Point(5.08, 20.32),
            direction=CornerDirection.AUTO,
        )
        assert result.corner == Point(0.0, 20.32)

    def test_explicit_horizontal_first(self) -> None:
        result = create_orthogonal_routing(
            Point(0.0, 0.0), Point(10.16, 5.08),
            direction=CornerDirection.HORIZONTAL_FIRST,
        )
        assert result.corner == Point(10.16, 0.0)

    def test_explicit_vertical_first(self) -> None:
        result = create_orthogonal_routing(
            Point(0.0, 0.0), Point(10.16, 5.08),
            direction=CornerDirection.VERTICAL_FIRST,
        )
        assert result.corner == Point(0.0, 5.08)


class TestObstacleAvoidance:
    def test_l_shape_picks_secondary_direction_when_primary_collides(self) -> None:
        obstacle_box = make_box(2.54, -2.54, 7.62, 2.54)
        result = create_orthogonal_routing(
            Point(0.0, 0.0), Point(10.16, 5.08),
            direction=CornerDirection.HORIZONTAL_FIRST,
            obstacles=(obstacle_box,),
        )
        assert result.corner == Point(0.0, 5.08)

    def test_direct_route_falls_back_to_u_shape_when_blocked(self) -> None:
        obstacle_box = make_box(-1.27, 1.27, 1.27, 5.08)
        result = create_orthogonal_routing(
            Point(0.0, 0.0), Point(0.0, 7.62),
            obstacles=(obstacle_box,),
        )
        assert result.is_direct is False
        assert len(result.segments) == 3

    def test_unroutable_raises(self) -> None:
        big_box = make_box(-100.0, -100.0, 100.0, 100.0)
        with pytest.raises(RuntimeError, match="cannot route"):
            create_orthogonal_routing(
                Point(0.0, 0.0), Point(10.16, 5.08),
                obstacles=(big_box,),
            )


class TestValidateRoutingResult:
    def test_passes_on_valid_l_shape(self) -> None:
        result = create_orthogonal_routing(Point(0.0, 0.0), Point(10.16, 5.08))
        validate_routing_result(result)

    def test_raises_on_diagonal_segment(self) -> None:
        from scripts.carrier.core.geometry import RoutingResult
        bad = RoutingResult(
            segments=((Point(0.0, 0.0), Point(5.08, 5.08)),),
            junctions=(),
            corner=None,
            is_direct=False,
        )
        with pytest.raises(ValueError, match="not orthogonal"):
            validate_routing_result(bad)

    def test_raises_on_disconnected_segments(self) -> None:
        from scripts.carrier.core.geometry import RoutingResult
        bad = RoutingResult(
            segments=(
                (Point(0.0, 0.0), Point(5.08, 0.0)),
                (Point(7.62, 0.0), Point(7.62, 5.08)),
            ),
            junctions=(),
            corner=None,
            is_direct=False,
        )
        with pytest.raises(ValueError, match="do not connect"):
            validate_routing_result(bad)

    def test_raises_on_empty_segments(self) -> None:
        from scripts.carrier.core.geometry import RoutingResult
        with pytest.raises(ValueError, match="no segments"):
            validate_routing_result(RoutingResult(
                segments=(), junctions=(), corner=None, is_direct=False,
            ))


class TestTIntersectionDetection:
    def test_endpoint_in_interior_of_other_segment_detected(self) -> None:
        segments = [
            (Point(0.0, 0.0), Point(10.16, 0.0)),
            (Point(5.08, 0.0), Point(5.08, 5.08)),
        ]
        intersections = detect_t_intersections(segments)
        assert Point(5.08, 0.0) in intersections

    def test_endpoint_at_segment_endpoint_not_a_t(self) -> None:
        segments = [
            (Point(0.0, 0.0), Point(10.16, 0.0)),
            (Point(0.0, 0.0), Point(0.0, 5.08)),
        ]
        intersections = detect_t_intersections(segments)
        assert intersections == ()

    def test_disjoint_segments_yield_no_intersections(self) -> None:
        segments = [
            (Point(0.0, 0.0), Point(5.08, 0.0)),
            (Point(20.32, 5.08), Point(25.4, 5.08)),
        ]
        assert detect_t_intersections(segments) == ()
