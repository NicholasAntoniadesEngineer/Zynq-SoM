"""Manhattan wire helpers for in-block connectivity."""

from __future__ import annotations

from scripts.carrier.model.block import Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid


def manhattan_wires(start: Point, end: Point) -> tuple[Wire, ...]:
    """Emit one or two orthogonal segments connecting *start* to *end*."""
    if start == end:
        raise ValueError(f"manhattan_wires: start == end ({start})")
    if abs(start.x - end.x) < KICAD_GRID_MM / 2:
        return (Wire(start=start, end=end),)
    if abs(start.y - end.y) < KICAD_GRID_MM / 2:
        return (Wire(start=start, end=end),)
    corner = Point(snap_to_grid(end.x), snap_to_grid(start.y))
    if corner == start or corner == end:
        return (Wire(start=start, end=end),)
    return (
        Wire(start=start, end=corner),
        Wire(start=corner, end=end),
    )


def stub_to_x(start: Point, target_x: float) -> tuple[Wire, ...]:
    """Horizontal stub from *start* to ``target_x`` at the same Y."""
    end = Point(snap_to_grid(target_x), start.y)
    return manhattan_wires(start, end)


def route_horizontal(start: Point, end_x: float) -> tuple[Wire, ...]:
    """Single horizontal run at *start* Y to ``end_x``."""
    end = Point(snap_to_grid(end_x), snap_to_grid(start.y))
    return manhattan_wires(start, end)


def route_channel(start: Point, channel_x: float, dest: Point) -> tuple[Wire, ...]:
    """Route pin to destination via a vertical channel at ``channel_x``."""
    channel_x = snap_to_grid(channel_x)
    if abs(start.y - dest.y) < KICAD_GRID_MM / 2:
        return route_horizontal(start, dest.x)
    wires: list[Wire] = []
    wires.extend(route_horizontal(start, channel_x))
    channel_top = Point(channel_x, start.y)
    channel_bottom = Point(channel_x, dest.y)
    if channel_top != channel_bottom:
        wires.append(Wire(start=channel_top, end=channel_bottom))
    if abs(channel_x - dest.x) >= KICAD_GRID_MM / 2:
        wires.extend(route_horizontal(channel_bottom, dest.x))
    return tuple(wires)


def route_with_jog(start: Point, dest: Point, jog_x: float) -> tuple[Wire, ...]:
    """Break colinear runs with a vertical segment at ``jog_x``."""
    jog_x = snap_to_grid(jog_x)
    if abs(start.y - dest.y) < KICAD_GRID_MM / 2:
        mid_a = Point(jog_x, start.y)
        mid_b = Point(jog_x, snap_to_grid(start.y + KICAD_GRID_MM))
        return (
            Wire(start=start, end=mid_a),
            Wire(start=mid_a, end=mid_b),
            Wire(start=mid_b, end=Point(jog_x, dest.y)),
            Wire(start=Point(jog_x, dest.y), end=dest),
        )
    return manhattan_wires(start, dest)
