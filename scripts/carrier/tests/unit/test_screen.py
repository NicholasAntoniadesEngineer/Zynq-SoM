"""Tests for Y-axis-aware screen direction helpers.

KiCad schematic space has +Y pointing visually DOWN. The screen_above /
screen_below / screen_left / screen_right helpers must encode this so
call sites read naturally regardless of how the underlying axis is
oriented.
"""

from __future__ import annotations

from scripts.carrier.core.sexpr import (
    Point,
    screen_above,
    screen_below,
    screen_left,
    screen_right,
)


def test_screen_above_decreases_y() -> None:
    moved = screen_above(Point(10.0, 50.0), 5.08)
    assert moved.y == 50.0 - 5.08
    assert moved.x == 10.0


def test_screen_below_increases_y() -> None:
    moved = screen_below(Point(10.0, 50.0), 5.08)
    assert moved.y == 50.0 + 5.08
    assert moved.x == 10.0


def test_screen_left_decreases_x() -> None:
    moved = screen_left(Point(20.0, 30.0), 7.62)
    assert moved.x == 20.0 - 7.62
    assert moved.y == 30.0


def test_screen_right_increases_x() -> None:
    moved = screen_right(Point(20.0, 30.0), 7.62)
    assert moved.x == 20.0 + 7.62
    assert moved.y == 30.0


def test_screen_helpers_accept_tuple_input() -> None:
    above_via_tuple = screen_above((10.0, 50.0), 2.54)
    assert above_via_tuple == Point(10.0, 50.0 - 2.54)


def test_screen_helpers_compose() -> None:
    origin_position = Point(100.0, 100.0)
    upper_left = screen_left(screen_above(origin_position, 10.16), 5.08)
    assert upper_left == Point(100.0 - 5.08, 100.0 - 10.16)


def test_screen_above_zero_distance_is_identity() -> None:
    point = Point(1.27, 2.54)
    assert screen_above(point, 0.0) == point
    assert screen_below(point, 0.0) == point
    assert screen_left(point, 0.0) == point
    assert screen_right(point, 0.0) == point
