from __future__ import annotations

import pytest

from schgen.core.symbols import GRID
from schgen.layout.place import Spacing, gceil, gfloor, gsnap

U = GRID


def _on_grid(v: float) -> bool:
    return abs(v / U - round(v / U)) < 1e-6


@pytest.mark.parametrize("fn", [gsnap, gceil, gfloor])
@pytest.mark.parametrize("v", [0.0, 1.0, 1.27, 1.9, 2.54, 5.0, 10.16, -2.6, 3.81])
def test_helpers_land_on_grid(fn, v):
    assert _on_grid(fn(v))


def test_gsnap_rounds_to_nearest():
    assert gsnap(0.6) == 0.0
    assert gsnap(0.7) == U
    assert gsnap(U) == U
    assert gsnap(1.9) == U


def test_gceil_rounds_up_and_is_idempotent_on_grid():
    assert gceil(1.3) == 2 * U
    assert gceil(U) == U
    assert gceil(0.0) == 0.0


def test_gfloor_rounds_down_and_is_idempotent_on_grid():
    assert gfloor(1.3) == U
    assert gfloor(2 * U) == 2 * U
    assert gfloor(2.6) == 2 * U


def test_gfloor_le_v_le_gceil():
    for v in [0.3, 1.0, 1.9, 5.5, 9.1]:
        assert gfloor(v) <= v + 1e-9
        assert gceil(v) >= v - 1e-9
        assert gfloor(v) <= gceil(v)


def test_snap_ceil_floor_agree_on_grid_points():
    for k in range(0, 6):
        v = round(k * U, 3)
        assert gsnap(v) == v == gceil(v) == gfloor(v)


def test_expanded_grows_port_run_and_stays_on_grid():
    s = Spacing()
    e = s.expanded()
    assert e.port_run > s.port_run
    assert _on_grid(e.port_run)
    assert e.cluster_dx > s.cluster_dx
    assert _on_grid(e.cluster_dx)


def test_expanded_preserves_fixed_attachment_gaps():
    s = Spacing()
    e = s.expanded()
    assert e.label_tap_gap == s.label_tap_gap
    assert e.hang_stub == s.hang_stub


def test_expanded_is_monotonic_under_repeat():
    s = Spacing()
    e1 = s.expanded()
    e2 = e1.expanded()
    assert e2.port_run >= e1.port_run > s.port_run
