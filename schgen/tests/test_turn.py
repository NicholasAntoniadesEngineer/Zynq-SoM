from __future__ import annotations

import math

import pytest

from schgen.generate.pcb.footprint import _footprint_bbox, resolve_mod
from schgen.generate.pcb.mating_face import _rot_pad_bbox
from schgen.generate.pcb.turn import (
    FULL_TURN_DEG,
    QUADRANT_DEG,
    pad_half_extent,
    turn_box,
    turn_point,
)

QUADRANTS = (0.0, 90.0, 180.0, 270.0)
ASYMMETRIC_BOX = (-14.64, -3.0, 0.0, 3.0)
ASYMMETRIC_CONNECTORS = ("DS1024-2x6R2", "XT60PW-M", "TF-01A", "HDMI-019S",
                         "SFW15R-1STE1LF", "TYPE-C-31-M-12")
MOUTH_OUTSIDE_COURTYARD = "TYPE-C-31-M-12"
BBOX_ROUNDING_SLACK = 1e-3


def _corner_hull(box, deg):
    pts = [turn_point(px, py, deg)
           for px in (box[0], box[2]) for py in (box[1], box[3])]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def _inverse_hull(box, deg):
    return _corner_hull(box, FULL_TURN_DEG - deg)


@pytest.mark.parametrize("deg", QUADRANTS)
def test_turn_box_and_turn_point_share_one_handedness(deg):
    assert turn_box(ASYMMETRIC_BOX, deg) == _corner_hull(ASYMMETRIC_BOX, deg)


@pytest.mark.parametrize("deg", (QUADRANT_DEG, 3 * QUADRANT_DEG))
def test_the_two_handednesses_are_distinguishable_on_an_asymmetric_box(deg):
    assert turn_box(ASYMMETRIC_BOX, deg) != _inverse_hull(ASYMMETRIC_BOX, deg)


def test_quarter_turn_transposes_a_box_with_unequal_extents():
    box = (1.0, -2.0, 9.0, 2.0)
    turned = turn_box(box, QUADRANT_DEG)
    assert turned == (-2.0, -9.0, 2.0, -1.0)
    assert (turned[2] - turned[0], turned[3] - turned[1]) == \
           (box[3] - box[1], box[2] - box[0])


def _holds(outer, inner):
    return (outer[0] <= inner[0] + BBOX_ROUNDING_SLACK
            and outer[1] <= inner[1] + BBOX_ROUNDING_SLACK
            and outer[2] >= inner[2] - BBOX_ROUNDING_SLACK
            and outer[3] >= inner[3] - BBOX_ROUNDING_SLACK)


@pytest.mark.parametrize("mpn", ASYMMETRIC_CONNECTORS)
@pytest.mark.parametrize("deg", QUADRANTS)
def test_turned_courtyard_holds_the_turned_pads_of_a_real_connector(mpn, deg):
    mod = resolve_mod(f"{mpn}:{mpn}")
    assert mod is not None, mpn
    court = turn_box(_footprint_bbox(mod), deg)
    pads = _rot_pad_bbox(mod, deg)
    assert pads is not None, mpn
    assert _holds(court, pads), \
        f"{mpn} at {deg}: courtyard {court} does not hold pad hull {pads}"


@pytest.mark.parametrize("deg", (QUADRANT_DEG, 3 * QUADRANT_DEG))
def test_the_inverse_handedness_loses_the_pads_of_a_real_connector(deg):
    mod = resolve_mod(f"{MOUTH_OUTSIDE_COURTYARD}:{MOUTH_OUTSIDE_COURTYARD}")
    assert mod is not None
    wrong = _inverse_hull(_footprint_bbox(mod), deg)
    pads = _rot_pad_bbox(mod, deg)
    assert pads is not None
    assert not _holds(wrong, pads), \
        f"an inverse-handed courtyard {wrong} still held the pads {pads} — " \
        f"this board can no longer tell the two rotation conventions apart"


@pytest.mark.parametrize("deg", QUADRANTS)
def test_pad_half_extent_swaps_only_on_the_odd_quadrants(deg):
    hx, hy = pad_half_extent(2.0, 1.0, deg)
    swapped = round(deg / QUADRANT_DEG) % 2 == 1
    assert (round(hx, 9), round(hy, 9)) == ((0.5, 1.0) if swapped else (1.0, 0.5))


def test_pad_half_extent_of_a_diagonal_pad_is_the_true_rotated_extent():
    size_w, size_h, deg = 2.0, 1.0, 45.0
    hx, hy = pad_half_extent(size_w, size_h, deg)
    diag = math.cos(math.radians(deg)) * (size_w + size_h) / 2
    assert hx == pytest.approx(diag)
    assert hy == pytest.approx(diag)
    assert hx > size_w / 2 and hy > size_h / 2


def test_footprint_bbox_measures_a_diagonal_pad(tmp_path):
    mod = tmp_path / "diagonal_pad.kicad_mod"
    mod.write_text(
        '(footprint "diagonal_pad" (layer "F.Cu")\n'
        '  (pad "1" smd rect (at 0 0 45) (size 2 1) (layers "F.Cu"))\n'
        ')\n')
    x0, y0, x1, y1 = _footprint_bbox(mod)
    half = math.cos(math.radians(45.0)) * (2.0 + 1.0) / 2
    assert (x0, y0, x1, y1) == pytest.approx((-half, -half, half, half),
                                             abs=BBOX_ROUNDING_SLACK)
    assert y1 - y0 > 1.0


def test_footprint_with_no_courtyard_and_no_pads_is_refused(tmp_path):
    mod = tmp_path / "no_geometry.kicad_mod"
    mod.write_text('(footprint "no_geometry" (layer "F.Cu")\n'
                   '  (fp_text reference "REF**" (at 0 0) (layer "F.SilkS"))\n'
                   ')\n')
    with pytest.raises(AssertionError, match="no measurable extent"):
        _footprint_bbox(mod)
