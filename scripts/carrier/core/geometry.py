"""Geometric primitives and Manhattan routing for KiCad schematic generation.

Provides:
    BoundingBox        - axis-aligned rectangle with intersection helpers
    CornerDirection    - L-shape corner placement preference
    RoutingResult      - segments + junctions + corner from a routing call
    create_orthogonal_routing(...)
                       - L-shaped (or U-shaped fallback) Manhattan route
                         between two grid-aligned points, optionally avoiding
                         a list of BoundingBox obstacles, with a junction
                         emitted at every corner
    validate_routing_result(...)
                       - asserts the result is purely orthogonal, segments
                         connect end-to-end, and the corner (if any) matches
                         the segment endpoints
    detect_t_intersections(...)
                       - given a flat list of wire segments, return the set
                         of points where one wire's endpoint sits mid-segment
                         of another (these need junctions per Rule J4)

Coordinate system: KiCad schematic space (millimetres, +Y is visually DOWN).
All positions must be on the 1.27 mm grid; ``create_orthogonal_routing``
asserts this on entry and emits only grid-aligned segments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from scripts.carrier.core.sexpr import (
    GRID_TOLERANCE_MM,
    KICAD_GRID_MM,
    Point,
    PointLike,
    assert_on_grid,
    to_point,
)


# ---------------------------------------------------------------------------
# BoundingBox
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned rectangle in KiCad schematic space.

    ``top_left`` is the visually-upper-left corner (smaller X, smaller Y).
    ``bottom_right`` is the visually-lower-right corner (larger X, larger Y).
    Y-axis is inverted in KiCad, so "upper" means smaller Y here.
    """

    top_left: Point
    bottom_right: Point

    def __post_init__(self) -> None:
        if self.top_left.x > self.bottom_right.x:
            raise ValueError(
                f"BoundingBox top_left.x ({self.top_left.x}) must be <= "
                f"bottom_right.x ({self.bottom_right.x})"
            )
        if self.top_left.y > self.bottom_right.y:
            raise ValueError(
                f"BoundingBox top_left.y ({self.top_left.y}) must be <= "
                f"bottom_right.y ({self.bottom_right.y})"
            )

    @property
    def width_mm(self) -> float:
        return self.bottom_right.x - self.top_left.x

    @property
    def height_mm(self) -> float:
        return self.bottom_right.y - self.top_left.y

    @property
    def center(self) -> Point:
        return Point(
            (self.top_left.x + self.bottom_right.x) / 2.0,
            (self.top_left.y + self.bottom_right.y) / 2.0,
        )

    def expand(self, margin_mm: float) -> "BoundingBox":
        return BoundingBox(
            Point(self.top_left.x - margin_mm, self.top_left.y - margin_mm),
            Point(self.bottom_right.x + margin_mm, self.bottom_right.y + margin_mm),
        )

    def contains(self, position: PointLike) -> bool:
        point = to_point(position)
        return (
            self.top_left.x <= point.x <= self.bottom_right.x
            and self.top_left.y <= point.y <= self.bottom_right.y
        )

    def intersects_segment(self, start: PointLike, end: PointLike) -> bool:
        """Return True if the orthogonal segment ``start->end`` crosses or
        enters the rectangle interior (touching the edge does not count).
        Tolerates float-precision wobble up to ``GRID_TOLERANCE_MM``.
        """
        start_point = to_point(start)
        end_point = to_point(end)
        if abs(start_point.x - end_point.x) <= GRID_TOLERANCE_MM:
            shared_x = (start_point.x + end_point.x) / 2.0
            return self._intersects_vertical(
                shared_x, start_point.y, end_point.y,
            )
        if abs(start_point.y - end_point.y) <= GRID_TOLERANCE_MM:
            shared_y = (start_point.y + end_point.y) / 2.0
            return self._intersects_horizontal(
                shared_y, start_point.x, end_point.x,
            )
        raise ValueError(
            f"intersects_segment requires an orthogonal segment, got "
            f"{start_point} -> {end_point}"
        )

    def _intersects_vertical(self, x_value: float, y_a: float, y_b: float) -> bool:
        if x_value <= self.top_left.x or x_value >= self.bottom_right.x:
            return False
        y_low, y_high = (y_a, y_b) if y_a <= y_b else (y_b, y_a)
        return y_low < self.bottom_right.y and y_high > self.top_left.y

    def _intersects_horizontal(self, y_value: float, x_a: float, x_b: float) -> bool:
        if y_value <= self.top_left.y or y_value >= self.bottom_right.y:
            return False
        x_low, x_high = (x_a, x_b) if x_a <= x_b else (x_b, x_a)
        return x_low < self.bottom_right.x and x_high > self.top_left.x


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class CornerDirection(Enum):
    AUTO = "auto"
    HORIZONTAL_FIRST = "horizontal_first"
    VERTICAL_FIRST = "vertical_first"


WireSegment = tuple[Point, Point]


@dataclass(frozen=True)
class RoutingResult:
    """Result of an orthogonal routing call.

    ``segments`` is a tuple of (start, end) Point pairs, in route order.
    ``junctions`` lists every interior corner point (every place where two
    segments meet). The schematic generator emits a (junction ...) at each.
    ``is_direct`` is True iff there is exactly one segment.
    ``corner`` is the single L-corner for two-segment routes, else None.
    """

    segments: tuple[WireSegment, ...]
    junctions: tuple[Point, ...] = field(default_factory=tuple)
    corner: Point | None = None
    is_direct: bool = False


def create_orthogonal_routing(
    from_pos: PointLike,
    to_pos: PointLike,
    direction: CornerDirection = CornerDirection.AUTO,
    obstacles: Iterable[BoundingBox] = (),
) -> RoutingResult:
    """Build an orthogonal (Manhattan) route between two grid points.

    Strategy:
        1. If the two points share X or Y, emit a single straight segment.
        2. Else try the requested L-shape (or AUTO heuristic). If no obstacle
           intersects either segment, return that L-route with a junction
           at the corner.
        3. Else try the other L-shape orientation.
        4. Else fall back to a U-shape (3 segments) routed around the
           obstacle bounding-box union along an outer corridor.
    """
    start_point = to_point(from_pos)
    end_point = to_point(to_pos)
    assert_on_grid(start_point)
    assert_on_grid(end_point)
    obstacle_list = tuple(obstacles)

    if (
        _approx_equal(start_point.x, end_point.x)
        or _approx_equal(start_point.y, end_point.y)
    ):
        direct_segments: tuple[WireSegment, ...] = ((start_point, end_point),)
        if not _route_collides(direct_segments, obstacle_list):
            return RoutingResult(
                segments=direct_segments,
                junctions=(),
                corner=None,
                is_direct=True,
            )
        fallback_route = _u_shape_route(start_point, end_point, obstacle_list)
        if _route_collides(fallback_route.segments, obstacle_list):
            raise RuntimeError(
                f"create_orthogonal_routing: cannot route {start_point} -> "
                f"{end_point} around {len(obstacle_list)} obstacle(s) "
                "(direct route collides; U-shape detours all collide too)"
            )
        return fallback_route

    primary_route = _l_shape_route(
        start_point, end_point,
        _resolve_direction(start_point, end_point, direction),
    )
    if not _route_collides(primary_route.segments, obstacle_list):
        return primary_route

    secondary_direction = _opposite_direction(
        _resolve_direction(start_point, end_point, direction)
    )
    secondary_route = _l_shape_route(start_point, end_point, secondary_direction)
    if not _route_collides(secondary_route.segments, obstacle_list):
        return secondary_route

    fallback_route = _u_shape_route(start_point, end_point, obstacle_list)
    if _route_collides(fallback_route.segments, obstacle_list):
        raise RuntimeError(
            f"create_orthogonal_routing: cannot route {start_point} -> "
            f"{end_point} around {len(obstacle_list)} obstacle(s); "
            "manual placement adjustment required"
        )
    return fallback_route


def _resolve_direction(
    start: Point, end: Point, requested: CornerDirection
) -> CornerDirection:
    if requested != CornerDirection.AUTO:
        return requested
    delta_x = abs(end.x - start.x)
    delta_y = abs(end.y - start.y)
    return (
        CornerDirection.HORIZONTAL_FIRST
        if delta_x >= delta_y
        else CornerDirection.VERTICAL_FIRST
    )


def _opposite_direction(direction: CornerDirection) -> CornerDirection:
    if direction == CornerDirection.HORIZONTAL_FIRST:
        return CornerDirection.VERTICAL_FIRST
    if direction == CornerDirection.VERTICAL_FIRST:
        return CornerDirection.HORIZONTAL_FIRST
    raise ValueError(f"_opposite_direction: AUTO is not a concrete direction")


def _l_shape_route(
    start: Point, end: Point, direction: CornerDirection
) -> RoutingResult:
    if direction == CornerDirection.HORIZONTAL_FIRST:
        corner_point = Point(end.x, start.y)
    elif direction == CornerDirection.VERTICAL_FIRST:
        corner_point = Point(start.x, end.y)
    else:
        raise ValueError(f"_l_shape_route requires concrete direction, got {direction}")
    first_segment: WireSegment = (start, corner_point)
    second_segment: WireSegment = (corner_point, end)
    return RoutingResult(
        segments=(first_segment, second_segment),
        junctions=(corner_point,),
        corner=corner_point,
        is_direct=False,
    )


def _u_shape_route(
    start: Point, end: Point, obstacles: tuple[BoundingBox, ...]
) -> RoutingResult:
    """Route around obstacles by detouring through an outside corridor.

    Tries detours both above and below (then left and right) the union of
    obstacle bounding boxes, in order of total path length, and returns the
    first non-colliding option.
    """
    obstacle_min_x = min(box.top_left.x for box in obstacles)
    obstacle_max_x = max(box.bottom_right.x for box in obstacles)
    obstacle_min_y = min(box.top_left.y for box in obstacles)
    obstacle_max_y = max(box.bottom_right.y for box in obstacles)
    margin_mm = KICAD_GRID_MM * 2
    detour_above_y = _snap_above(obstacle_min_y - margin_mm)
    detour_below_y = _snap_below(obstacle_max_y + margin_mm)
    detour_left_x = _snap_above(obstacle_min_x - margin_mm)
    detour_right_x = _snap_below(obstacle_max_x + margin_mm)

    candidates: list[RoutingResult] = []
    for detour_y in (detour_above_y, detour_below_y):
        first_corner = Point(start.x, detour_y)
        second_corner = Point(end.x, detour_y)
        candidates.append(RoutingResult(
            segments=(
                (start, first_corner),
                (first_corner, second_corner),
                (second_corner, end),
            ),
            junctions=(first_corner, second_corner),
            corner=None,
            is_direct=False,
        ))
    for detour_x in (detour_left_x, detour_right_x):
        first_corner = Point(detour_x, start.y)
        second_corner = Point(detour_x, end.y)
        candidates.append(RoutingResult(
            segments=(
                (start, first_corner),
                (first_corner, second_corner),
                (second_corner, end),
            ),
            junctions=(first_corner, second_corner),
            corner=None,
            is_direct=False,
        ))

    candidates.sort(key=lambda result: _total_segment_length(result.segments))
    for candidate in candidates:
        if not _route_collides(candidate.segments, obstacles):
            return candidate
    return candidates[0]


def _route_collides(
    segments: tuple[WireSegment, ...], obstacles: tuple[BoundingBox, ...]
) -> bool:
    for segment_start, segment_end in segments:
        for box in obstacles:
            if box.intersects_segment(segment_start, segment_end):
                return True
    return False


def _total_segment_length(segments: tuple[WireSegment, ...]) -> float:
    total = 0.0
    for segment_start, segment_end in segments:
        total += abs(segment_end.x - segment_start.x)
        total += abs(segment_end.y - segment_start.y)
    return total


def _snap_above(value: float) -> float:
    """Snap to grid in the negative-Y direction (visually upward)."""
    snapped = round(value / KICAD_GRID_MM) * KICAD_GRID_MM
    if snapped > value:
        snapped -= KICAD_GRID_MM
    return snapped


def _snap_below(value: float) -> float:
    """Snap to grid in the positive direction (visually downward / rightward)."""
    snapped = round(value / KICAD_GRID_MM) * KICAD_GRID_MM
    if snapped < value:
        snapped += KICAD_GRID_MM
    return snapped


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_routing_result(result: RoutingResult) -> None:
    """Assert the routing result is structurally well-formed.

    Raises ValueError on any of:
        - Empty segment list
        - A segment that is not orthogonal (start.x != end.x and start.y != end.y)
        - Two consecutive segments that don't share an endpoint
        - The recorded ``corner`` (if not None) doesn't match the segment seam
        - is_direct is True but len(segments) != 1
    """
    if not result.segments:
        raise ValueError("RoutingResult has no segments")
    for segment_index, (segment_start, segment_end) in enumerate(result.segments):
        if not (
            _approx_equal(segment_start.x, segment_end.x)
            or _approx_equal(segment_start.y, segment_end.y)
        ):
            raise ValueError(
                f"Segment {segment_index} is not orthogonal: "
                f"{segment_start} -> {segment_end}"
            )
    for segment_index in range(len(result.segments) - 1):
        previous_end = result.segments[segment_index][1]
        next_start = result.segments[segment_index + 1][0]
        if not (
            _approx_equal(previous_end.x, next_start.x)
            and _approx_equal(previous_end.y, next_start.y)
        ):
            raise ValueError(
                f"Segments {segment_index} and {segment_index + 1} "
                f"do not connect end-to-end: {previous_end} != {next_start}"
            )
    if result.is_direct and len(result.segments) != 1:
        raise ValueError(
            f"RoutingResult.is_direct is True but len(segments) is {len(result.segments)}"
        )
    if result.corner is not None and len(result.segments) == 2:
        seam_point = result.segments[0][1]
        if not (
            _approx_equal(seam_point.x, result.corner.x)
            and _approx_equal(seam_point.y, result.corner.y)
        ):
            raise ValueError(
                f"RoutingResult.corner {result.corner} does not match segment "
                f"seam {seam_point}"
            )


# ---------------------------------------------------------------------------
# T-intersection detection (for junction emission post-processing)
# ---------------------------------------------------------------------------


def detect_t_intersections(segments: Iterable[WireSegment]) -> tuple[Point, ...]:
    """Find every endpoint that lies strictly between another segment's endpoints.

    Used after all wires for a sheet are emitted: any T-intersection without
    a junction is a Rule J4 violation. Returns the deduplicated set of such
    points, sorted by (x, y) for stable iteration.
    """
    segment_list = [(to_point(start), to_point(end)) for start, end in segments]
    intersections: set[tuple[float, float]] = set()
    for outer_start, outer_end in segment_list:
        for inner_start, inner_end in segment_list:
            if (outer_start, outer_end) == (inner_start, inner_end):
                continue
            for endpoint in (inner_start, inner_end):
                if _point_strictly_inside(endpoint, outer_start, outer_end):
                    intersections.add((endpoint.x, endpoint.y))
    return tuple(
        Point(x, y) for x, y in sorted(intersections)
    )


def _point_strictly_inside(point: Point, segment_start: Point, segment_end: Point) -> bool:
    """True if ``point`` is on the open segment (not at either endpoint)."""
    if _approx_equal(segment_start.x, segment_end.x):
        if not _approx_equal(point.x, segment_start.x):
            return False
        y_low, y_high = (
            (segment_start.y, segment_end.y)
            if segment_start.y <= segment_end.y
            else (segment_end.y, segment_start.y)
        )
        return y_low + GRID_TOLERANCE_MM < point.y < y_high - GRID_TOLERANCE_MM
    if _approx_equal(segment_start.y, segment_end.y):
        if not _approx_equal(point.y, segment_start.y):
            return False
        x_low, x_high = (
            (segment_start.x, segment_end.x)
            if segment_start.x <= segment_end.x
            else (segment_end.x, segment_start.x)
        )
        return x_low + GRID_TOLERANCE_MM < point.x < x_high - GRID_TOLERANCE_MM
    return False


def _approx_equal(value_a: float, value_b: float) -> bool:
    return abs(value_a - value_b) <= GRID_TOLERANCE_MM
