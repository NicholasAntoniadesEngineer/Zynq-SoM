"""Bottom-side P2 — the EST-DRIVEN SIDE CHOICE (_pick_sided) + the restricted
estimator it consumes. The distance chooser was measured side-blind (P1:
top/bottom tie at 0.403, tie-break keeps top); P2 judges cross-face finalists
by the sizing estimator (cross-airwire + registered est_via_cost). Board-level
controls live in the build ladder: zero-opt-in byte-identity on both projects,
and the judged live probe (126 firings, 0 dishonest flips)."""

from __future__ import annotations

import dataclasses

import pytest

from schgen.generate import floorplan as fp
from schgen.generate.floorplan import (
    Block,
    Plan,
    _nets_by_sheet,
    _pick_sided,
    extract_som,
    load_floorplan_spec,
)
from schgen.generate.pcb.placement import subsystem_zone_geometry


def _cand(k: int, side: str) -> tuple:
    return (k, (10.0 * k, 5.0, 8.0, 6.0), (0.0,) * 4, (0.0,) * 4, side, ())


def _finalists(d0: float, d1: float) -> list[tuple]:
    return sorted([((round(d0, 4), 0), _cand(0, "top")),
                   ((round(d1, 4), 4), _cand(4, "bottom"))])


def test_pick_sided_strict_improvement_deterministic():
    ests = {"top": 100.0, "bottom": 99.9}
    for _ in range(3):
        got = _pick_sided(_finalists(0.4, 0.4), lambda c: ests[c[4]])
        assert got[4] == "bottom"
    ests = {"top": 100.0, "bottom": 100.1}
    for _ in range(3):
        got = _pick_sided(_finalists(0.4, 0.4), lambda c: ests[c[4]])
        assert got[4] == "top"


def test_pick_sided_tie_and_margin_keep_incumbent():
    ests = {"top": 100.0, "bottom": 100.0}
    assert _pick_sided(_finalists(0.4, 0.4), lambda c: ests[c[4]])[4] == "top"
    ests = {"top": 100.0, "bottom": 100.0 - 1e-6}
    assert _pick_sided(_finalists(0.4, 0.4), lambda c: ests[c[4]])[4] == "top"
    ests = {"top": 100.0, "bottom": 200.0}
    got = _pick_sided(_finalists(9.0, 0.4), lambda c: ests[c[4]])
    assert got[4] == "top"


def test_pick_sided_requires_judge():
    with pytest.raises(AssertionError, match="no estimator judge"):
        _pick_sided(_finalists(0.4, 0.4), None)


def test_nets_by_sheet_deterministic_and_complete():
    net_pts = {
        "B_NET": [("R2", "sh_b", ((0.0, 0.0),)), ("R1", "sh_a", ((0.0, 0.0),))],
        "A_NET": [("R1", "sh_a", ((0.0, 0.0),)), ("R3", "sh_c", ((0.0, 0.0),))],
    }
    got = _nets_by_sheet(net_pts)
    assert got == {"sh_a": ("A_NET", "B_NET"), "sh_b": ("B_NET",),
                   "sh_c": ("A_NET",)}
    assert got == _nets_by_sheet(dict(reversed(list(net_pts.items()))))


@pytest.fixture(scope="module")
def either_ctx():
    spec = load_floorplan_spec()
    spec2 = dataclasses.replace(
        spec, interior={**spec.interior,
                        "hdmi_rx_term": {"side": "either"}})
    zg = subsystem_zone_geometry(two_side=True, spec=spec2)
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    return zg, sheets


def test_restricted_estimator_delta_equals_full(either_ctx, monkeypatch):
    """The side judge consumes evaluate(..., only_sheet=SHEET): between two
    candidate poses/shapes of that sheet's block the restricted difference
    must equal the full-kernel difference EXACTLY (no other net moves), and
    every evaluation must be deterministic."""
    zg, sheets = either_ctx
    monkeypatch.setattr(fp, "BOARD_W", 185.0)
    monkeypatch.setattr(fp, "BOARD_H", 166.0)
    plan = Plan(extract_som())
    ev = fp._cross_estimator(plan, zg, sheets)
    k_bot = next(i for i, s in enumerate(zg.shapes["hdmi_rx_term"])
                 if s.side == "bottom")

    def blocks(x: float, y: float, k: int) -> list[Block]:
        b = Block(name="hdmi_rx_term", kind="interior")
        b.x, b.y, b.shape_idx = x, y, k
        w, h = zg.zone_box["hdmi_rx"]
        eb = Block(name="hdmi_rx", kind="edge")
        eb.x, eb.y, eb.w, eb.h = 60.0, 150.0, w, h
        return [eb, b]

    a, b_ = blocks(70.0, 110.0, 0), blocks(90.0, 120.0, k_bot)
    full_a, full_b = ev(a), ev(b_)
    rest_a = ev(a, only_sheet="hdmi_rx_term")
    rest_b = ev(b_, only_sheet="hdmi_rx_term")
    assert full_a > rest_a > 0.0
    assert full_a - full_b == pytest.approx(rest_a - rest_b, abs=1e-9)
    assert ev(a) == full_a
    assert ev(a, only_sheet="hdmi_rx_term") == rest_a
    assert ev(a, only_sheet="no_such_sheet") == 0.0
