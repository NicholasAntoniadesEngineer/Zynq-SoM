from __future__ import annotations

import pytest

from schgen.core.symbols import GRID
from schgen.layout.route import (
    Grid,
    RouteError,
    _components,
    _NetGeom,
    cell_of,
    cells_between,
    point_of,
    snap_ok,
)

U = GRID


def test_snap_ok_on_and_off_grid():
    assert snap_ok(0.0)
    assert snap_ok(U)
    assert snap_ok(3 * U)
    assert not snap_ok(1.0)
    assert not snap_ok(U / 2)


def test_cell_of_round_trips_through_point_of():
    p = (3 * U, 5 * U)
    c = cell_of(p)
    assert c == (3, 5)
    assert point_of(c) == (round(3 * U, 3), round(5 * U, 3))


def test_cell_of_off_grid_raises():
    with pytest.raises(RouteError):
        cell_of((0.5, 0.0))


def test_cells_between_vertical_inclusive():
    cells = cells_between((0.0, 0.0), (0.0, 2 * U))
    assert cells == [(0, 0), (0, 1), (0, 2)]


def test_cells_between_horizontal_inclusive():
    cells = cells_between((0.0, U), (3 * U, U))
    assert cells == [(0, 1), (1, 1), (2, 1), (3, 1)]


def test_cells_between_non_orthogonal_raises():
    with pytest.raises(RouteError):
        cells_between((0.0, 0.0), (U, U))


def test_two_same_net_legs_share_a_cell_legally():
    g = Grid()
    g.claim("NETA", cells_between((0.0, 0.0), (2 * U, 0.0)))
    g.claim("NETA", cells_between((2 * U, 0.0), (2 * U, 2 * U)))
    assert g.owner[(2, 0)] == "NETA"


def test_two_different_nets_crossing_is_a_short():
    g = Grid()
    g.claim("NETA", cells_between((0.0, 5 * U), (4 * U, 5 * U)))
    with pytest.raises(RouteError, match="contested"):
        g.claim("NETB", cells_between((2 * U, 0.0), (2 * U, 8 * U)))


def test_free_or_allows_own_and_unowned_only():
    g = Grid()
    g.claim("NETA", [(0, 0)])
    assert g.free_or("NETA", (0, 0))
    assert g.free_or("NETA", (9, 9))
    assert not g.free_or("NETB", (0, 0))


def test_block_box_marks_interior_cells():
    g = Grid()
    g.block_box((0.0, 0.0, 3 * U, 3 * U))
    assert g.owner.get((1, 1)) == "#blocked"
    assert g.owner.get((2, 2)) == "#blocked"
    g2 = Grid()
    g2.claim("NETA", [(1, 1)])
    g2.block_box((0.0, 0.0, 3 * U, 3 * U))
    assert g2.owner[(1, 1)] == "NETA"


def _geom(legs, pin_parts):
    g = _NetGeom()
    g.legs = list(legs)
    g.pin_parts = dict(pin_parts)
    return g


def test_clean_l_route_is_one_component():
    A, B, C = (0.0, 0.0), (2 * U, 0.0), (2 * U, 2 * U)
    g = _geom([(A, B), (B, C)], {A: {"U1"}, C: {"U2"}})
    comps = _components(g)
    assert len(comps) == 1
    assert A in comps[0] and C in comps[0]


def test_two_disjoint_legs_are_an_open():
    g = _geom(
        [((0.0, 0.0), (2 * U, 0.0)), ((6 * U, 6 * U), (8 * U, 6 * U))],
        {(0.0, 0.0): {"U1"}, (2 * U, 0.0): {"U2"},
         (6 * U, 6 * U): {"U3"}, (8 * U, 6 * U): {"U4"}},
    )
    assert len(_components(g)) == 2


def test_trunk_with_two_taps_is_one_component():
    trunk_l, mid, trunk_r = (0.0, 0.0), (2 * U, 0.0), (4 * U, 0.0)
    tap_a, tap_b = (2 * U, 3 * U), (4 * U, 3 * U)
    g = _geom(
        [(trunk_l, mid), (mid, trunk_r), (mid, tap_a), (trunk_r, tap_b)],
        {trunk_l: {"U1"}, tap_a: {"U2"}, tap_b: {"U3"}},
    )
    assert len(_components(g)) == 1


def test_bonds_merge_duplicate_pad_points():
    p1, p2 = (0.0, 0.0), (5 * U, 5 * U)
    g = _NetGeom()
    g.pin_parts = {p1: {"U1"}, p2: {"U1"}}
    g.bonds = [(p1, p2)]
    assert len(_components(g)) == 1


def _degree_map(g: _NetGeom):
    deg: dict = {}
    for a, b in g.legs:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    for pt, parts in g.pin_parts.items():
        deg[pt] = deg.get(pt, 0) + len(parts)
    for pt in g.power_pts:
        deg[pt] = deg.get(pt, 0) + 1
    return deg


def test_l_route_has_no_junction():
    A, B, C = (0.0, 0.0), (2 * U, 0.0), (2 * U, 2 * U)
    g = _geom([(A, B), (B, C)], {A: {"U1"}, C: {"U2"}})
    deg = _degree_map(g)
    assert max(deg.values()) < 3


def test_tee_tap_creates_one_junction_at_degree_three():
    center = (2 * U, 0.0)
    left, right, down = (0.0, 0.0), (4 * U, 0.0), (2 * U, 2 * U)
    g = _geom(
        [(left, center), (center, right), (center, down)],
        {left: {"U1"}, right: {"U2"}, down: {"U3"}},
    )
    deg = _degree_map(g)
    junctions = [pt for pt, d in deg.items() if d >= 3]
    assert junctions == [center]
