"""KiCad schematic grid primitives.

The generator works exclusively in KiCad-native millimetres on the 50 mil
(1.27 mm) grid. Off-grid coordinates cause silent KiCad connectivity failures
— every coordinate that reaches the emitter is asserted on grid via
:func:`assert_on_grid`.

KiCad schematic space has +Y pointing visually downward on the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Union


KICAD_GRID_MM: float = 1.27
"""KiCad default schematic grid (50 mil / 1.27 mm)."""

GRID_TOLERANCE_MM: float = 1e-4
"""Numeric tolerance for grid-alignment checks (0.0001 mm)."""


@dataclass(frozen=True)
class Point:
    """A 2D coordinate in KiCad schematic space (millimetres)."""

    x: float
    y: float

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y

    def offset(self, dx: float = 0.0, dy: float = 0.0) -> "Point":
        return Point(self.x + dx, self.y + dy)

    def snap(self, grid: float = KICAD_GRID_MM) -> "Point":
        return Point(snap_to_grid(self.x, grid), snap_to_grid(self.y, grid))

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


PointLike = Union[Point, tuple[float, float]]


def to_point(value: PointLike) -> Point:
    """Coerce a ``(x, y)`` tuple or ``Point`` into a ``Point``."""
    if isinstance(value, Point):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return Point(float(value[0]), float(value[1]))
    raise TypeError(
        "Expected Point or (x, y) tuple, got "
        f"{type(value).__name__}: {value!r}"
    )


def snap_to_grid(value: float, grid: float = KICAD_GRID_MM) -> float:
    """Round a coordinate to the nearest grid increment."""
    if grid <= 0:
        raise ValueError(f"Grid step must be positive, got {grid}")
    return round(value / grid) * grid


def assert_on_grid(
    position: PointLike,
    grid: float = KICAD_GRID_MM,
    tolerance: float = GRID_TOLERANCE_MM,
) -> None:
    """Fail hard if a point is not on the given grid."""
    point = to_point(position)
    snapped_x = snap_to_grid(point.x, grid)
    snapped_y = snap_to_grid(point.y, grid)
    if (
        abs(point.x - snapped_x) > tolerance
        or abs(point.y - snapped_y) > tolerance
    ):
        raise ValueError(
            f"Point ({point.x}, {point.y}) is not on {grid}mm grid; "
            f"would snap to ({snapped_x}, {snapped_y})"
        )
