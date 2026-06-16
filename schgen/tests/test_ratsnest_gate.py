"""LAW-5 ratsnest gate — the TOPOLOGY-AWARE cross-airwire budget.

The budget allows the INHERENT SoM-star airwire (every subsystem must reach the
centered DF40 mezzanine; cabled connectors are pinned to the board edges) and
bounds only the AVOIDABLE peripheral<->peripheral remainder by
``CROSS_K * sqrt(area) * n``. These tests prove the gate still KILLS a hairball
(LAW 4: a changed gate lands with a mutant that proves the kill) — the star
floor is only ADDED, so it can never mask peripheral scatter.
"""

from __future__ import annotations

from schgen.verify.ratsnest_gate import (CROSS_K, RatsnestResult, cross_budget)


def _allowance(bw: float, bh: float, n: int) -> float:
    return CROSS_K * (bw * bh) ** 0.5 * n


def test_som_star_is_allowed_but_peripheral_scatter_is_bounded():
    bw, bh, n = 200.0, 185.0, 30
    allow = _allowance(bw, bh, n)
    som = 11000.0                       # inherent central-SoM star, however large
    budget = cross_budget(som, bw, bh, n)

    # a layout whose AVOIDABLE (non-star) cross is within the allowance PASSES,
    # no matter how big the inherent star is.
    ok = RatsnestResult(cross_mm=round(som + allow - 100, 1), som_cross_mm=som,
                        cross_budget_mm=budget)
    assert ok.cross_ok
    assert ok.avoidable_cross_mm <= allow

    # a HAIRBALL: same star, but peripherals flung apart so the avoidable cross
    # blows the allowance -> the gate FAILS it (the star floor cannot rescue it).
    bad = RatsnestResult(cross_mm=round(som + allow + 5000, 1), som_cross_mm=som,
                         cross_budget_mm=budget)
    assert not bad.cross_ok
    assert bad.avoidable_cross_mm > allow


def test_star_floor_is_added_not_multiplied():
    # raising the inherent star raises the budget exactly 1:1 (it is ALLOWED),
    # so a fixed avoidable margin stays exactly as tight regardless of the star.
    bw, bh, n = 200.0, 185.0, 30
    b_lo = cross_budget(1000.0, bw, bh, n)
    b_hi = cross_budget(9000.0, bw, bh, n)
    assert round(b_hi - b_lo, 1) == 8000.0      # pure addition of the star delta
