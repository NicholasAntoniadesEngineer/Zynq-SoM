"""Trace-differential harness for the _Occupancy spatial neighborhood index
(schgen/generate/floorplan.py): the exhaustive separation scan and the
uniform-grid hashed scan must return IDENTICAL accept/reject booleans on
every query — dense-pack and sparse-spread stress layouts, add/remove churn,
place_near first-fit equivalence, and the loud static-bound raises. The same
traced kernel is selectable on a live build via SCHGEN_SPATIAL_TRACE=1."""

from __future__ import annotations

import pytest

from schgen.generate import floorplan as fp
from schgen.generate.floorplan import _Occupancy, _spatial_bounds

_REACHES = (
    (0.0, 0.0, 0.0, 0.0),
    (1.5, 0.3, 0.0, 2.2),
    (3.32, 3.32, 3.32, 3.32),
    (0.0, 1.48, 0.5, 0.0),
)


def _sweep(occ: _Occupancy, w: float, h: float, step: float) -> list[bool]:
    out = []
    for k, reach in enumerate(_REACHES):
        x = 0.0
        while x < fp.BOARD_W:
            y = float(k)
            while y < fp.BOARD_H:
                ref = occ._fits_exhaustive(x, y, w, h, reach)
                new = occ._fits_hashed(x, y, w, h, reach)
                traced = occ._fits_traced(x, y, w, h, reach)
                assert ref is new is traced
                out.append(new)
                y += step
            x += step
    return out


def test_static_bounds_derivation():
    reach_bound, envelope = _spatial_bounds(far_ceil=10.0)
    assert reach_bound == pytest.approx(2.05)
    assert envelope >= fp.CABLE_NEIGHBOR_GAP
    big_bound, big_env = _spatial_bounds(far_ceil=10.0, max_reach=11.331)
    assert big_bound == pytest.approx(11.331)
    assert big_env == pytest.approx(2 * 11.331)


def test_dense_pack_trace_differential(monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 200.0)
    monkeypatch.setattr(fp, "BOARD_H", 180.0)
    occ = _Occupancy(far_ceil=10.0, max_reach=3.32)
    added = []
    k = 0
    for i in range(12):
        for j in range(10):
            r = (3.0 + i * 16.0, 2.5 + j * 17.5, 9.0, 7.5, _REACHES[k % 4])
            occ.add(*r)
            added.append(r)
            k += 1
    results = _sweep(occ, 10.0, 8.0, 3.5)
    assert True in results and False in results
    for r in added[::3]:
        occ.remove(*r)
    results = _sweep(occ, 10.0, 8.0, 3.5)
    assert True in results and False in results


def test_sparse_spread_trace_differential(monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 400.0)
    monkeypatch.setattr(fp, "BOARD_H", 400.0)
    occ = _Occupancy(max_reach=3.32)
    for i in range(3):
        for j in range(3):
            occ.add(30.0 + i * 130.0, 25.0 + j * 140.0, 22.0, 18.0,
                    _REACHES[(i + j) % 4])
    results = _sweep(occ, 26.0, 21.0, 11.0)
    assert True in results and False in results


def test_place_near_first_fit_identical_to_exhaustive(monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 160.0)
    monkeypatch.setattr(fp, "BOARD_H", 140.0)

    def _fill(occ: _Occupancy) -> None:
        occ.add(55.0, 45.0, 50.0, 50.0)
        occ.add(10.0, 10.0, 30.0, 12.0, _REACHES[1])
        occ.add(110.0, 100.0, 24.0, 20.0, _REACHES[3])
        occ.add(20.0, 90.0, 18.0, 26.0, _REACHES[2])
    hashed = _Occupancy(far_ceil=10.0, max_reach=3.32)
    exhaustive = _Occupancy(far_ceil=10.0, max_reach=3.32)
    exhaustive.fits = exhaustive._fits_exhaustive
    _fill(hashed)
    _fill(exhaustive)
    for ax, ay, w, h, reach in (
            (80.0, 70.0, 20.0, 15.0, _REACHES[1]),
            (12.0, 12.0, 16.0, 10.0, _REACHES[0]),
            (150.0, 20.0, 25.0, 22.0, _REACHES[2]),
            (80.0, 135.0, 40.0, 12.0, _REACHES[3])):
        got = hashed.place_near(ax, ay, w, h, reach)
        want = exhaustive.place_near(ax, ay, w, h, reach)
        assert got == want
        assert got is not None
        hashed.add(*got, reach)
        exhaustive.add(*want, reach)


def test_overhang_reaches_beyond_tier_floor(monkeypatch):
    monkeypatch.setattr(fp, "BOARD_W", 220.0)
    monkeypatch.setattr(fp, "BOARD_H", 200.0)
    occ = _Occupancy(far_ceil=10.0, max_reach=11.331)
    occ.add(90.0, 80.0, 42.0, 15.0, (0.665, 0.0, 0.0, 11.331))
    occ.add(30.0, 120.0, 34.0, 22.0, (1.27, 0.0, 2.25, 11.331))
    occ.add(140.0, 30.0, 17.0, 30.0, (2.86, 1.473, 0.5885, 0.0))
    occ.add(60.0, 20.0, 24.0, 22.0, (0.4449, 2.02, 3.6399, 0.0))
    results = _sweep(occ, 20.0, 16.0, 4.5)
    assert True in results and False in results


def test_reach_bound_raises_loud():
    occ = _Occupancy()
    with pytest.raises(AssertionError, match="static reach bound"):
        occ.add(5.0, 5.0, 10.0, 10.0, (0.0, 99.0, 0.0, 0.0))


def test_trace_kernel_selected_by_env():
    expect = (_Occupancy._fits_traced if fp._SPATIAL_TRACE
              else _Occupancy._fits_hashed)
    assert _Occupancy.fits is expect
    src = fp.Path(fp.__file__).read_text()
    assert "fits = _fits_traced if _SPATIAL_TRACE else _fits_hashed" in src
