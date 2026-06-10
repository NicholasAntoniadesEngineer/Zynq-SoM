"""Unit tests for the exact overlap-removal solver (separate.py).

The Laws require a hard guarantee: after separation no two rectangles sit
within the clearance gap on BOTH axes (the same proximity test the overlap
validator uses). These tests assert that guarantee on adversarial and
random inputs, plus grid-alignment and centroid stability.
"""

from __future__ import annotations

import random

from zynq_eda.core.layout._constants import KICAD_GRID_MM
from zynq_eda.core.layout.separate import Rect, remove_overlaps

GAP = 2.0


def _crowded(a: tuple[float, float, float, float], b: tuple[float, float, float, float], gap: float) -> bool:
    """True if rects (cx,cy,w,h) are within ``gap`` on BOTH axes (validator semantics)."""
    (ax, ay, aw, ah), (bx, by, bw, bh) = a, b
    dx = abs(ax - bx) - (aw + bw) / 2.0
    dy = abs(ay - by) - (ah + bh) / 2.0
    return dx < gap and dy < gap


def _assert_no_crowding(rects: list[Rect], centers: list[tuple[float, float]], gap: float) -> None:
    placed = [(centers[i][0], centers[i][1], rects[i].w, rects[i].h) for i in range(len(rects))]
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            assert not _crowded(placed[i], placed[j], gap), (
                f"rects {i} and {j} still crowded: {placed[i]} vs {placed[j]}"
            )


def test_two_overlapping_rects_separated() -> None:
    rects = [Rect(0, 0, 4, 4), Rect(1, 0, 4, 4)]  # heavily overlapping
    out = remove_overlaps(rects, gap=GAP)
    _assert_no_crowding(rects, out, GAP)


def test_stack_of_coincident_rects_separated() -> None:
    rects = [Rect(0, 0, 4, 4) for _ in range(6)]  # all on top of each other
    out = remove_overlaps(rects, gap=GAP)
    _assert_no_crowding(rects, out, GAP)


def test_random_clouds_have_no_crowding() -> None:
    rng = random.Random(1234)
    for _ in range(40):
        n = rng.randint(2, 25)
        rects = [
            Rect(
                cx=rng.uniform(-30, 30),
                cy=rng.uniform(-30, 30),
                w=rng.uniform(1, 8),
                h=rng.uniform(1, 8),
            )
            for _ in range(n)
        ]
        out = remove_overlaps(rects, gap=GAP)
        _assert_no_crowding(rects, out, GAP)


def test_output_is_grid_aligned_when_input_is() -> None:
    g = KICAD_GRID_MM
    rects = [Rect(0, 0, 3 * g, 3 * g), Rect(g, 0, 3 * g, 3 * g), Rect(0, g, 3 * g, 3 * g)]
    out = remove_overlaps(rects, gap=GAP)
    for cx, cy in out:
        assert abs(cx / g - round(cx / g)) < 1e-6, f"cx {cx} off grid"
        assert abs(cy / g - round(cy / g)) < 1e-6, f"cy {cy} off grid"


def test_already_separated_layout_is_untouched() -> None:
    rects = [Rect(0, 0, 2, 2), Rect(20, 0, 2, 2), Rect(0, 20, 2, 2)]
    out = remove_overlaps(rects, gap=GAP)
    for r, (cx, cy) in zip(rects, out):
        assert abs(cx - r.cx) < 1e-6 and abs(cy - r.cy) < 1e-6


def test_fixed_rect_does_not_move() -> None:
    rects = [Rect(0, 0, 4, 4), Rect(1, 0, 4, 4)]
    out = remove_overlaps(rects, gap=GAP, movable=[False, True])
    assert out[0] == (0.0, 0.0)  # fixed stays put
    _assert_no_crowding(rects, out, GAP)
