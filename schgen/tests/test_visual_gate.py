from __future__ import annotations

from schgen.verify.visual_gate import (
    Box,
    Junction,
    Seg,
    SheetGeometry,
    _collinear_overlap,
    _cross,
    _foreign_t_touch,
    _point_on_seg,
    check,
)


def test_same_net_junction_passes():
    geo = SheetGeometry(
        wires=[Seg(0, 5, 5, 5, "A"), Seg(5, 5, 10, 5, "A"),
               Seg(5, 5, 5, 10, "A")],
        junctions=[Junction(5.0, 5.0)])
    assert check(geo).ok, check(geo).findings


def test_cross_net_junction_fails():
    geo = SheetGeometry(
        wires=[Seg(0, 5, 5, 5, "A"), Seg(5, 5, 5, 10, "B")],
        junctions=[Junction(5.0, 5.0)])
    r = check(geo)
    assert not r.ok
    assert any("cross-net junction" in f for f in r.findings), r.findings


def test_cross_perpendicular_interior_is_true():
    h = Seg(0.0, 5.0, 10.0, 5.0, "A")
    v = Seg(5.0, 0.0, 5.0, 10.0, "B")
    assert _cross(h, v)
    assert _cross(v, h)


def test_cross_touching_at_endpoint_is_not_a_crossing():
    h = Seg(0.0, 5.0, 10.0, 5.0, "A")
    v = Seg(5.0, 5.0, 5.0, 10.0, "B")
    assert not _cross(h, v)


def test_cross_at_horizontal_endpoint_is_not_a_crossing():
    h = Seg(0.0, 5.0, 10.0, 5.0, "A")
    v = Seg(0.0, 0.0, 0.0, 10.0, "B")
    assert not _cross(h, v)


def test_cross_parallel_segments_never_cross():
    a = Seg(0.0, 5.0, 10.0, 5.0, "A")
    b = Seg(0.0, 7.0, 10.0, 7.0, "B")
    assert not _cross(a, b)


def test_collinear_overlap_horizontal_true():
    a = Seg(0.0, 0.0, 10.0, 0.0, "A")
    b = Seg(5.0, 0.0, 15.0, 0.0, "B")
    assert _collinear_overlap(a, b)


def test_collinear_disjoint_is_false():
    a = Seg(0.0, 0.0, 4.0, 0.0, "A")
    b = Seg(6.0, 0.0, 10.0, 0.0, "B")
    assert not _collinear_overlap(a, b)


def test_collinear_only_touching_endpoint_is_false():
    a = Seg(0.0, 0.0, 4.0, 0.0, "A")
    b = Seg(4.0, 0.0, 8.0, 0.0, "B")
    assert not _collinear_overlap(a, b)


def test_collinear_different_rows_is_false():
    a = Seg(0.0, 0.0, 10.0, 0.0, "A")
    b = Seg(0.0, 1.0, 10.0, 1.0, "B")
    assert not _collinear_overlap(a, b)


def test_point_on_seg_interior_and_endpoint():
    s = Seg(0.0, 0.0, 10.0, 0.0, "A")
    assert _point_on_seg(5.0, 0.0, s, interior_only=True)
    assert _point_on_seg(0.0, 0.0, s, interior_only=False)
    assert not _point_on_seg(0.0, 0.0, s, interior_only=True)
    assert not _point_on_seg(5.0, 1.0, s, interior_only=False)


def test_foreign_t_touch_endpoint_on_interior_flags():
    a = Seg(0.0, 0.0, 10.0, 0.0, "A")
    b = Seg(5.0, 0.0, 5.0, 5.0, "B")
    assert _foreign_t_touch(a, b) == (5.0, 0.0)


def test_foreign_t_touch_endpoint_on_endpoint_flags():
    a = Seg(0.0, 0.0, 10.0, 0.0, "A")
    b = Seg(10.0, 0.0, 10.0, 5.0, "B")
    assert _foreign_t_touch(a, b) == (10.0, 0.0)


def test_same_net_t_touch_is_legal():
    a = Seg(0.0, 0.0, 10.0, 0.0, "A")
    b = Seg(5.0, 0.0, 5.0, 5.0, "A")
    assert _foreign_t_touch(a, b) is None


def test_disjoint_wires_no_t_touch():
    a = Seg(0.0, 0.0, 10.0, 0.0, "A")
    b = Seg(0.0, 5.0, 10.0, 5.0, "B")
    assert _foreign_t_touch(a, b) is None


def test_check_clean_same_net_l_route_passes():
    geo = SheetGeometry(wires=[Seg(0, 0, 10, 0, "A"), Seg(10, 0, 10, 10, "A")])
    res = check(geo)
    assert res.ok and res.findings == []


def test_check_flags_different_net_crossing():
    geo = SheetGeometry(wires=[Seg(0, 5, 10, 5, "A"), Seg(5, 0, 5, 10, "B")])
    res = check(geo)
    assert not res.ok
    assert any("CROSS" in f for f in res.findings)


def test_check_flags_collinear_overlap():
    geo = SheetGeometry(wires=[Seg(0, 0, 10, 0, "A"), Seg(5, 0, 15, 0, "B")])
    res = check(geo)
    assert not res.ok
    assert any("collinear overlap" in f for f in res.findings)


def test_check_flags_foreign_t_touch():
    geo = SheetGeometry(wires=[Seg(0, 0, 10, 0, "A"), Seg(5, 0, 5, 5, "B")])
    res = check(geo)
    assert not res.ok
    assert any("T-touch" in f for f in res.findings)


def test_check_flags_overlapping_text_of_different_owners():
    geo = SheetGeometry(boxes=[
        Box(0, 0, 5, 5, "value", "U1"),
        Box(2, 2, 7, 7, "reference", "U2"),
    ])
    res = check(geo)
    assert not res.ok
    assert any("overlaps" in f for f in res.findings)


def test_check_passes_separated_boxes():
    geo = SheetGeometry(boxes=[
        Box(0, 0, 5, 5, "value", "U1"),
        Box(6, 6, 9, 9, "reference", "U2"),
    ])
    assert check(geo).ok


def test_check_flags_two_overlapping_texts_of_same_owner():
    geo = SheetGeometry(boxes=[
        Box(0, 0, 5, 2, "reference", "U1"),
        Box(1, 0, 6, 2, "value", "U1"),
    ])
    res = check(geo)
    assert not res.ok


def test_check_allows_own_text_over_own_body():
    geo = SheetGeometry(boxes=[
        Box(0, 0, 10, 10, "body", "U1"),
        Box(2, 2, 4, 4, "value", "U1"),
    ])
    assert check(geo).ok


def test_check_flags_wire_over_foreign_label():
    geo = SheetGeometry(
        wires=[Seg(0, 0, 10, 0, "NETA")],
        boxes=[Box(4, -1, 6, 1, "label", "label:NETB")],
    )
    res = check(geo)
    assert not res.ok
    assert any("over label" in f for f in res.findings)


def test_check_allows_wire_touching_its_own_label_anchor():
    geo = SheetGeometry(
        wires=[Seg(0, 0, 10, 0, "NETA")],
        boxes=[Box(10, -0.05, 14, 1, "label", "label:NETA")],
    )
    assert check(geo).ok
