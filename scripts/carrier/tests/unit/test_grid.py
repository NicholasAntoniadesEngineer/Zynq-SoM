"""Tests for grid snap and grid-alignment assertions in sexpr.py."""

from __future__ import annotations

import pytest

from scripts.carrier.core.sexpr import (
    KICAD_GRID_MM,
    Point,
    assert_on_grid,
    snap_to_grid,
)


class TestSnapToGrid:
    def test_round_to_nearest_grid_step(self) -> None:
        assert snap_to_grid(0.0) == 0.0
        assert snap_to_grid(1.27) == 1.27
        assert snap_to_grid(2.54) == 2.54

    def test_rounds_below_half_step_down(self) -> None:
        assert snap_to_grid(0.6) == 0.0

    def test_rounds_above_half_step_up(self) -> None:
        assert snap_to_grid(0.7) == 1.27

    def test_negative_values(self) -> None:
        assert snap_to_grid(-1.27) == -1.27
        assert snap_to_grid(-0.6) == 0.0

    def test_custom_grid_step(self) -> None:
        assert snap_to_grid(2.5, grid=1.0) == 2.0  # round-half-to-even
        assert snap_to_grid(2.6, grid=1.0) == 3.0

    def test_zero_grid_raises(self) -> None:
        with pytest.raises(ValueError, match="Grid step must be positive"):
            snap_to_grid(1.0, grid=0.0)


class TestAssertOnGrid:
    def test_grid_aligned_passes(self) -> None:
        assert_on_grid(Point(0.0, 0.0))
        assert_on_grid(Point(1.27, 2.54))
        assert_on_grid(Point(127.0 - 0.0, 5.08))

    def test_off_grid_raises(self) -> None:
        with pytest.raises(ValueError, match="not on .*mm grid"):
            assert_on_grid(Point(1.0, 1.0))

    def test_tuple_input_accepted(self) -> None:
        assert_on_grid((1.27, 0.0))

    def test_tolerance_allows_float_wobble(self) -> None:
        wobbled_x = 1.27 + 1e-9
        assert_on_grid(Point(wobbled_x, 0.0))

    def test_kicad_grid_constant_value(self) -> None:
        assert KICAD_GRID_MM == pytest.approx(1.27)
