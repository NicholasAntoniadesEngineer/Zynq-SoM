from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from schgen.core import fallbacks as fb
from schgen.generate import floorplan as fp
from schgen.generate.floorplan import (
    OCC_BOTTOM,
    OCC_PUNCH,
    OCC_TOP,
    Block,
    _edge_components,
    _Occupancy,
    _side_mask,
)
from schgen.generate.pcb.footprint import has_thru_pads, resolve_mod
from schgen.generate.pcb.mating_face import (
    _footprint_bbox,
    _rot_pad_bbox,
    thru_pad_boxes,
)
from schgen.generate.pcb.placement import (
    SOM_DECOUPLING_INSET,
    som_decoupling_cells,
)

_XT60 = "XT60PW-M:XT60PW-M"
_USBC = "TYPE-C-31-M-12:TYPE-C-31-M-12"
_MH = "MountingHole:MountingHole_3.2mm_M3_Pad"


def _mod(footprint: str) -> Path:
    m = resolve_mod(footprint)
    assert m is not None, footprint
    return m


def test_thru_pad_boxes_are_only_the_through_hole_pads():
    xt = _mod(_XT60)
    assert has_thru_pads(xt)
    boxes = thru_pad_boxes(xt, 0.0)
    assert boxes
    pb = _rot_pad_bbox(xt, 0.0)
    assert pb is not None
    for x0, y0, x1, y1 in boxes:
        assert x1 > x0 and y1 > y0
        assert pb[0] - 1e-9 <= x0 and x1 <= pb[2] + 1e-9
        assert pb[1] - 1e-9 <= y0 and y1 <= pb[3] + 1e-9
    bb = _footprint_bbox(xt)
    pad_area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in boxes)
    assert pad_area < 0.5 * (bb[2] - bb[0]) * (bb[3] - bb[1])

    smd = _mod("Capacitor_SMD:C_0603_1608Metric")
    assert not has_thru_pads(smd)
    assert thru_pad_boxes(smd, 0.0) == []
    sb = _footprint_bbox(smd)
    assert (sb[2] - sb[0]) > 0 and (sb[3] - sb[1]) > 0


def test_thru_pad_boxes_agree_with_has_thru_pads_on_every_live_footprint():
    from schgen.generate.pcb.footprint import board_parts
    seen: set[str] = set()
    n_thru = 0
    for _ref, (_sh, footprint, _v, _l) in sorted(board_parts().items()):
        if footprint in seen:
            continue
        seen.add(footprint)
        m = resolve_mod(footprint)
        if m is None:
            continue
        for rot in (0.0, 90.0, 180.0, 270.0):
            assert bool(thru_pad_boxes(m, rot)) == has_thru_pads(m), footprint
        n_thru += bool(has_thru_pads(m))
    assert n_thru >= 5


def test_rot_pad_bbox_is_the_hull_of_the_shared_pad_kernel():
    from schgen.generate.pcb.mating_face import _pad_boxes_local
    for fpname in (_XT60, _USBC, _MH):
        m = resolve_mod(fpname)
        if m is None:
            continue
        for rot in (0.0, 37.0, 90.0, 270.0):
            boxes = _pad_boxes_local(m, rot)
            hull = _rot_pad_bbox(m, rot)
            assert hull is not None and boxes
            assert hull == (min(b[1] for b in boxes), min(b[2] for b in boxes),
                            max(b[3] for b in boxes), max(b[4] for b in boxes))


def test_a_thru_pad_still_blocks_the_opposite_face():
    occ = _Occupancy()
    pad = (5.0, 5.0, 2.0, 2.0, OCC_PUNCH)
    occ.add(0.0, 0.0, 30.0, 30.0, mask=OCC_TOP, comps=(pad,))
    assert not occ.fits(4.0, 4.0, 4.0, 4.0, mask=OCC_BOTTOM)
    assert occ.fits(12.0, 12.0, 8.0, 8.0, mask=OCC_BOTTOM)
    assert not occ.fits(12.0, 12.0, 8.0, 8.0, mask=OCC_TOP)


def test_mounting_hole_corner_keepouts_still_pierce():
    src = inspect.getsource(fp._attempt_pack)
    assert "occ.add(cx, cy, MH_CORNER_KO, MH_CORNER_KO)" in src
    occ = _Occupancy()
    occ.add(0.0, 0.0, fp.MH_CORNER_KO, fp.MH_CORNER_KO)
    for m in (OCC_TOP, OCC_BOTTOM):
        assert not occ.fits(5.0, 5.0, 8.0, 8.0, mask=m)
    mh = _mod(_MH)
    assert has_thru_pads(mh) and thru_pad_boxes(mh, 0.0)


def test_bottom_block_may_sit_under_an_edge_zone():
    occ = _Occupancy()
    occ.add(0.0, 0.0, 40.0, 20.0, mask=OCC_TOP)
    assert occ.fits(10.0, 5.0, 10.0, 10.0, mask=OCC_BOTTOM)
    occ_old = _Occupancy()
    occ_old.add(0.0, 0.0, 40.0, 20.0, mask=OCC_PUNCH)
    assert not occ_old.fits(10.0, 5.0, 10.0, 10.0, mask=OCC_BOTTOM)


def test_bottom_block_may_sit_under_the_som():
    occ = _Occupancy()
    occ.add(50.0, 50.0, 53.0, 45.0, mask=OCC_TOP,
            comps=((10.0, 10.0, 6.0, 6.0, OCC_BOTTOM),))
    assert occ.fits(80.0, 60.0, 15.0, 15.0, mask=OCC_BOTTOM)
    assert not occ.fits(58.0, 58.0, 6.0, 6.0, mask=OCC_BOTTOM)
    assert not occ.fits(80.0, 60.0, 15.0, 15.0, mask=OCC_TOP)


def test_edge_punch_is_swept_out_to_the_board_edge():
    saved = (fp.BOARD_W, fp.BOARD_H)
    try:
        fp.BOARD_W, fp.BOARD_H = 200.0, 150.0
        comps = ((4.0, 4.0, 3.0, 3.0, OCC_PUNCH),
                 (1.0, 1.0, 2.0, 2.0, OCC_BOTTOM))
        cases = {"N": (30.0, 2.0), "S": (30.0, 130.0),
                 "W": (2.0, 30.0), "E": (180.0, 30.0)}
        for edge, (bx, by) in cases.items():
            b = Block(name="t", kind="edge", x=bx, y=by, w=15.0, h=15.0,
                      edge=edge)
            out = _edge_components(b, comps)
            assert out[1] == comps[1]
            dx, dy, cw, ch, cm = out[0]
            assert cm == OCC_PUNCH
            x0, y0 = bx + dx, by + dy
            x1, y1 = x0 + cw, y0 + ch
            assert x0 <= bx + 4.0 + 1e-9 and y0 <= by + 4.0 + 1e-9
            assert x1 >= bx + 7.0 - 1e-9 and y1 >= by + 7.0 - 1e-9
            if edge == "N":
                assert y0 == pytest.approx(0.0)
                assert y1 == pytest.approx(by + 7.0)
            elif edge == "S":
                assert y1 == pytest.approx(fp.BOARD_H)
            elif edge == "W":
                assert x0 == pytest.approx(0.0)
                assert x1 == pytest.approx(bx + 7.0)
            else:
                assert x1 == pytest.approx(fp.BOARD_W)
    finally:
        fp.BOARD_W, fp.BOARD_H = saved


def test_som_decoupling_cells_are_the_single_emission_oracle():
    src = inspect.getsource(
        __import__("schgen.generate.pcb.placement", fromlist=["x"]).build_model)
    assert "som_decoupling_cells(" in src
    cells = som_decoupling_cells(10.0, 20.0, 50.0, 42.0, 18)
    assert len(cells) == 18
    assert len(set(cells)) == 18
    m = SOM_DECOUPLING_INSET
    for cx, cy in cells:
        assert 10.0 + m <= cx <= 10.0 + 50.0 - m
        assert 20.0 + m <= cy <= 20.0 + 42.0 - m
    assert som_decoupling_cells(10.0, 20.0, 50.0, 42.0, 0) == []
    assert cells == som_decoupling_cells(10.0, 20.0, 50.0, 42.0, 18)


def test_monotonicity_guard_is_wired_and_registered():
    assert "punch_free_plan_rejected" in fb.REGISTRY
    assert fb.REGISTRY["punch_free_plan_rejected"].stage == "plan_lattice"
    src = inspect.getsource(fp.build_plan)
    assert "_search(False)" in src and "_guarded(_search)" in src
    assert "_fixed_pack(False)" in src and "_guarded(_fixed_pack)" in src
    assert src.count('_fb.record("punch_free_plan_rejected")') == 2
    assert "_plan_restore(cons_snap)" in src
    assert "except RuntimeError:" in src
    ev = fb.snapshot()
    try:
        fb.restore(())
        fb.record("punch_free_plan_rejected")
        assert fb.census()["punch_free_plan_rejected"] == 1
        fb.restore(())
        assert fb.census()["punch_free_plan_rejected"] == 0
    finally:
        fb.restore(ev)


def test_conservative_policy_reserves_the_superset():
    src = inspect.getsource(fp._attempt_pack)
    assert "free = plan.punch_free" in src
    assert "som_mask = OCC_TOP if free else OCC_PUNCH" in src
    assert "edge_mask = OCC_TOP if free else OCC_PUNCH" in src
    occ_free = _Occupancy()
    occ_free.add(0.0, 0.0, 40.0, 20.0, mask=OCC_TOP)
    occ_cons = _Occupancy()
    occ_cons.add(0.0, 0.0, 40.0, 20.0, mask=OCC_PUNCH)
    for m in (OCC_TOP, OCC_BOTTOM):
        for x, y in ((10.0, 5.0), (25.0, 3.0), (50.0, 5.0)):
            if occ_cons.fits(x, y, 8.0, 8.0, mask=m):
                assert occ_free.fits(x, y, 8.0, 8.0, mask=m)
    assert _side_mask("bottom") == OCC_BOTTOM
