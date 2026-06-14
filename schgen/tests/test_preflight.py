"""Unit tests for the preflight stock policy (SRC-2) — pure, offline, fast.

assess_stock is the network-free verdict the live preflight wraps; testing it
here locks the procurement-floor + sufficiency logic without hitting JLC.
"""

from __future__ import annotations

from schgen.verify.preflight import STOCK_FLOOR, assess_stock


def test_ok_high_stock():
    assert assess_stock(1000, 5, floor=50)[0] == "ok"


def test_low_below_floor_but_enough_for_need():
    # stock >= need but below the procurement floor -> 'low' (WARN, not fatal)
    status, flag = assess_stock(10, 5, floor=50)
    assert status == "low"
    assert "LOW STOCK" in flag


def test_insufficient_below_need():
    status, flag = assess_stock(3, 5, floor=50)
    assert status == "insufficient"
    assert "INSUFFICIENT" in flag


def test_out_of_stock():
    assert assess_stock(0, 5)[0] == "out"
    assert assess_stock(-1, 5)[0] == "out"


def test_floor_boundary_is_inclusive():
    assert assess_stock(50, 5, floor=50)[0] == "ok"    # exactly at the floor
    assert assess_stock(49, 5, floor=50)[0] == "low"


def test_need_dominates_floor_when_higher():
    # a large order: the effective threshold is need, not the floor
    assert assess_stock(80, 100, floor=50)[0] == "insufficient"
    assert assess_stock(120, 100, floor=50)[0] == "ok"


def test_hx5008_landmine_is_caught():
    # the real motivating case: C962544 @ stock 10, need 1 — must NOT pass clean
    assert assess_stock(10, 1, floor=STOCK_FLOOR)[0] == "low"
