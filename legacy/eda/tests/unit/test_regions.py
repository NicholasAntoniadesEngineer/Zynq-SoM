"""Unit tests for region-partition placement geometry."""

from __future__ import annotations

from zynq_eda.core.layout.regions import Region, Unit, partition_and_assign

A3_W, A3_H, MARGIN = 420.0, 297.0, 12.7


def _overlap(a: Region, b: Region) -> bool:
    return a.x0 < b.x1 and a.x1 > b.x0 and a.y0 < b.y1 and a.y1 > b.y0


def test_regions_are_disjoint_and_in_page() -> None:
    units = [Unit(f"U{i}", 40.0, 30.0) for i in range(6)]
    regs = partition_and_assign(units, A3_W, A3_H, MARGIN)
    assert len(regs) == 6
    boxes = list(regs.values())
    for r in boxes:
        assert r.x0 >= MARGIN - 1e-6 and r.x1 <= A3_W - MARGIN + 1e-6
        assert r.y0 >= MARGIN - 1e-6 and r.y1 <= A3_H - MARGIN + 1e-6
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not _overlap(boxes[i], boxes[j]), "regions must not overlap"


def test_single_unit_gets_full_page() -> None:
    regs = partition_and_assign([Unit("U1", 50.0, 50.0)], A3_W, A3_H, MARGIN)
    r = regs["U1"]
    assert abs(r.width - (A3_W - 2 * MARGIN)) < 1e-6
    assert abs(r.height - (A3_H - 2 * MARGIN)) < 1e-6


def test_left_and_right_connectors_land_on_their_side() -> None:
    units = [
        Unit("JL", 30.0, 40.0, edge="left"),
        Unit("U1", 40.0, 40.0),
        Unit("U2", 40.0, 40.0),
        Unit("JR", 30.0, 40.0, edge="right"),
    ]
    regs = partition_and_assign(units, A3_W, A3_H, MARGIN)
    # Left connector's region centre is left of the right connector's.
    assert regs["JL"].cx < regs["JR"].cx


def test_regions_large_enough_for_footprint() -> None:
    units = [Unit(f"U{i}", 60.0, 45.0) for i in range(4)]
    regs = partition_and_assign(units, A3_W, A3_H, MARGIN)
    for u in units:
        r = regs[u.ref]
        assert r.width >= u.w - 1e-6
        assert r.height >= u.h - 1e-6
