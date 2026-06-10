"""Phase 1 regression guards: render transform + clearance validator.

These lock in the two pillars of the render-truthful feedback loop:

  * :class:`PageRaster` maps KiCad page mm to render pixels with a uniform
    scale and no offset (so a finding's bbox lands exactly on the rendered
    page in the overlay).
  * The overlap validator now enforces *breathing room*: two visible
    primitives closer than ``VISUAL_CLEARANCE_MM`` are a finding even when
    their bboxes do not actually intersect ("tight-but-passing is a
    FAILURE"), while well-separated primitives stay clean.

They use ``geometry=None`` / raw bboxes so they run in milliseconds with no
KiCad library registration.
"""

from __future__ import annotations

from pathlib import Path

from zynq_eda.core.layout.bbox import BBox
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import PlacedLabel, Sheet
from zynq_eda.core.render.raster import PageRaster
from zynq_eda.core.validate.overlap import (
    VISUAL_CLEARANCE_MM,
    _overlap_is_significant,
    validate_overlap,
)


# ---- PageRaster transform -------------------------------------------------

def _a3_raster() -> PageRaster:
    return PageRaster(
        png_path=Path("/dev/null"),
        width_px=4961,
        height_px=3508,
        page_w_mm=420.0,
        page_h_mm=297.0,
        dpi=300.0,
    )


def test_pageraster_origin_maps_to_pixel_origin() -> None:
    assert _a3_raster().mm_to_px(0.0, 0.0) == (0.0, 0.0)


def test_pageraster_corner_maps_to_pixel_extent() -> None:
    x, y = _a3_raster().mm_to_px(420.0, 297.0)
    assert abs(x - 4961.0) < 1e-6
    assert abs(y - 3508.0) < 1e-6


def test_pageraster_is_uniform_scale() -> None:
    r = _a3_raster()
    x, y = r.mm_to_px(210.0, 148.5)
    assert abs(x - 2480.5) < 1e-6
    assert abs(y - 1754.0) < 1e-6


# ---- clearance gate -------------------------------------------------------

def _box(x0: float, y0: float, x1: float, y1: float) -> BBox:
    return BBox(min=Point(x0, y0), max=Point(x1, y1), kind="label", owner_id="t")


def test_gate_overlap_only_ignores_near_miss() -> None:
    """With no clearance, a 1mm gap is NOT a collision (pure overlap)."""
    a = _box(0, 0, 10, 2)
    b = _box(0, 3, 10, 5)  # 1mm vertical gap
    assert not _overlap_is_significant(a, b)


def test_gate_clearance_flags_near_miss() -> None:
    """With the 2mm clearance, that same 1mm gap IS a finding (crowding)."""
    a = _box(0, 0, 10, 2)
    b = _box(0, 3, 10, 5)
    assert _overlap_is_significant(a, b, VISUAL_CLEARANCE_MM)


def test_gate_clearance_passes_well_separated() -> None:
    """A 3mm gap clears the 2mm breathing-room requirement."""
    a = _box(0, 0, 10, 2)
    b = _box(0, 5, 10, 7)  # 3mm vertical gap
    assert not _overlap_is_significant(a, b, VISUAL_CLEARANCE_MM)


# ---- end-to-end: crowded labels flagged, spaced labels clean --------------

def _sheet(labels: tuple[PlacedLabel, ...]) -> Sheet:
    return Sheet(
        name="test",
        title="Test Sheet",
        paper_size="A4",
        labels=labels,
    )


def test_validate_overlap_flags_crowded_labels() -> None:
    """Two labels one grid step apart (1.27mm) crowd → label_label finding."""
    sheet = _sheet(
        (
            PlacedLabel(net_name="NETA", position=Point(50.8, 50.8)),
            PlacedLabel(net_name="NETB", position=Point(50.8, 52.07)),
        )
    )
    results = validate_overlap(sheet, strict=True)
    assert any(r.rule_id == "overlap.label_label" for r in results)


def test_validate_overlap_passes_spaced_labels() -> None:
    """Labels 15mm apart have clear breathing room → no finding."""
    sheet = _sheet(
        (
            PlacedLabel(net_name="NETA", position=Point(50.8, 50.8)),
            PlacedLabel(net_name="NETB", position=Point(50.8, 69.85)),
        )
    )
    results = validate_overlap(sheet, strict=True)
    assert not any(r.rule_id == "overlap.label_label" for r in results)
