"""Unit tests for bbox + occupancy primitives and the overlap validator.

These tests exercise the spatial-awareness foundation that subsequent
placement work will build on. They deliberately avoid registering real
KiCad symbol libraries — every symbol-related test uses the
``placeholder_symbol_bbox`` fallback so the suite runs in milliseconds.
"""

from __future__ import annotations

import math

import pytest

from zynq_eda.core.layout.bbox import (
    BBox,
    DEFAULT_TEXT_HEIGHT_RATIO,
    DEFAULT_TEXT_SIZE_MM,
    DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO,
    DEFAULT_WIRE_CLEARANCE_MM,
    _rotate_bbox,
    placeholder_symbol_bbox,
    text_bbox,
    wire_bbox,
)
from zynq_eda.core.layout.occupancy import Occupancy
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedLabel,
    PlacedSymbol,
    PlacedWire,
    Sheet,
)
from zynq_eda.core.validate.overlap import validate_overlap


# ---- BBox.intersects -----------------------------------------------------

def _box(x1: float, y1: float, x2: float, y2: float, owner: str = "t") -> BBox:
    return BBox(min=Point(x1, y1), max=Point(x2, y2), kind="symbol", owner_id=owner)


def test_bbox_intersects_overlap_simple() -> None:
    """Two clearly overlapping boxes intersect."""
    a = _box(0.0, 0.0, 10.0, 10.0)
    b = _box(5.0, 5.0, 15.0, 15.0)
    assert a.intersects(b) is True
    assert b.intersects(a) is True


def test_bbox_intersects_disjoint() -> None:
    """Two clearly separated boxes do not intersect."""
    a = _box(0.0, 0.0, 5.0, 5.0)
    b = _box(10.0, 10.0, 15.0, 15.0)
    assert a.intersects(b) is False


def test_bbox_intersects_edge_touch() -> None:
    """Boxes sharing exactly one edge do NOT intersect (KiCad convention)."""
    a = _box(0.0, 0.0, 10.0, 10.0)
    b = _box(10.0, 0.0, 20.0, 10.0)  # right edge of a == left edge of b
    assert a.intersects(b) is False


def test_bbox_intersects_with_padding() -> None:
    """Padding turns near-misses into intersections."""
    a = _box(0.0, 0.0, 10.0, 10.0)
    b = _box(11.0, 0.0, 20.0, 10.0)  # 1 mm gap on the x axis
    assert a.intersects(b) is False
    assert a.intersects(b, padding_mm=1.5) is True


def test_bbox_intersection_returns_overlap_box() -> None:
    """``intersection`` returns the geometric overlap rectangle."""
    a = _box(0.0, 0.0, 10.0, 10.0)
    b = _box(5.0, 5.0, 15.0, 15.0)
    overlap = a.intersection(b)
    assert overlap is not None
    assert overlap.min == Point(5.0, 5.0)
    assert overlap.max == Point(10.0, 10.0)


def test_bbox_intersection_disjoint_returns_none() -> None:
    """``intersection`` is None for disjoint boxes."""
    a = _box(0.0, 0.0, 5.0, 5.0)
    b = _box(10.0, 10.0, 15.0, 15.0)
    assert a.intersection(b) is None


def test_bbox_contains_point_inside() -> None:
    a = _box(0.0, 0.0, 10.0, 10.0)
    assert a.contains_point(Point(5.0, 5.0)) is True
    assert a.contains_point(Point(0.0, 0.0)) is True  # edge is inclusive
    assert a.contains_point(Point(11.0, 5.0)) is False


def test_bbox_expand_grows_outward() -> None:
    a = _box(10.0, 20.0, 30.0, 40.0)
    grown = a.expand(2.0)
    assert grown.min == Point(8.0, 18.0)
    assert grown.max == Point(32.0, 42.0)
    assert grown.kind == a.kind
    assert grown.owner_id == a.owner_id


def test_bbox_translate_shifts_box() -> None:
    a = _box(0.0, 0.0, 10.0, 10.0)
    shifted = a.translate(5.0, -3.0)
    assert shifted.min == Point(5.0, -3.0)
    assert shifted.max == Point(15.0, 7.0)


def test_bbox_rejects_inverted_corners() -> None:
    """min must be <= max on both axes."""
    with pytest.raises(ValueError):
        BBox(min=Point(10.0, 0.0), max=Point(0.0, 10.0), kind="symbol", owner_id="x")


# ---- text_bbox -----------------------------------------------------------

EXPECTED_TEXT_HEIGHT = DEFAULT_TEXT_SIZE_MM * DEFAULT_TEXT_HEIGHT_RATIO


def _expected_text_width(text: str) -> float:
    return float(len(text)) * DEFAULT_TEXT_SIZE_MM * DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO


def test_text_bbox_left_justify_puts_anchor_at_left_edge() -> None:
    """justify='left' anchors text at its left edge."""
    anchor = Point(100.0, 100.0)
    text = "VBUS"
    box = text_bbox(text, anchor, justify="left")
    assert box.min.x == anchor.x
    assert math.isclose(box.max.x - box.min.x, _expected_text_width(text))
    # Vertical centring around the anchor: anchor.y is halfway between min/max.
    assert math.isclose(box.min.y, anchor.y - EXPECTED_TEXT_HEIGHT / 2.0)
    assert math.isclose(box.max.y, anchor.y + EXPECTED_TEXT_HEIGHT / 2.0)


def test_text_bbox_right_justify_puts_anchor_at_right_edge() -> None:
    """justify='right' anchors text at its right edge."""
    anchor = Point(100.0, 100.0)
    text = "GND"
    box = text_bbox(text, anchor, justify="right")
    assert box.max.x == anchor.x
    assert math.isclose(box.min.x, anchor.x - _expected_text_width(text))


def test_text_bbox_center_justify_centres_on_anchor() -> None:
    """justify='center' centres the box horizontally on the anchor."""
    anchor = Point(100.0, 100.0)
    text = "VDD"
    box = text_bbox(text, anchor, justify="center")
    half_width = _expected_text_width(text) / 2.0
    assert math.isclose(box.min.x, anchor.x - half_width)
    assert math.isclose(box.max.x, anchor.x + half_width)


def test_text_bbox_rotation_90_swaps_width_and_height() -> None:
    """A 90° rotation swaps the bbox's apparent width and height."""
    anchor = Point(50.0, 50.0)
    text = "ABCDEFGH"  # 8 characters
    horizontal = text_bbox(text, anchor, justify="left", rotation=0.0)
    rotated = text_bbox(text, anchor, justify="left", rotation=90.0)
    # The rotated bbox's width should equal the horizontal's height
    # (within rounding) and vice versa.
    assert math.isclose(rotated.width, horizontal.height)
    assert math.isclose(rotated.height, horizontal.width)


def test_text_bbox_rotation_invalid_raises() -> None:
    with pytest.raises(ValueError):
        text_bbox("x", Point(0.0, 0.0), rotation=45.0)


def test_text_bbox_invalid_justify_raises() -> None:
    with pytest.raises(ValueError):
        text_bbox("x", Point(0.0, 0.0), justify="middle")  # type: ignore[arg-type]


def test_text_bbox_empty_text_zero_width() -> None:
    """An empty string produces a zero-width box at the anchor."""
    box = text_bbox("", Point(10.0, 10.0))
    assert box.width == 0.0
    assert box.height > 0.0  # still tall enough to be a real text row


# ---- _rotate_bbox internal helper ----------------------------------------

def test_rotate_bbox_zero_is_identity() -> None:
    a = _box(0.0, 0.0, 10.0, 5.0)
    rotated = _rotate_bbox(a, Point(0.0, 0.0), 0.0)
    assert rotated.min == a.min
    assert rotated.max == a.max


def test_rotate_bbox_180_around_origin() -> None:
    a = _box(2.0, 3.0, 8.0, 6.0)
    rotated = _rotate_bbox(a, Point(0.0, 0.0), 180.0)
    # 180° flip around origin: (x, y) → (-x, -y), so the new min/max
    # come from the negated corners.
    assert rotated.min == Point(-8.0, -6.0)
    assert rotated.max == Point(-2.0, -3.0)


def test_rotate_bbox_unsupported_angle_raises() -> None:
    with pytest.raises(ValueError):
        _rotate_bbox(_box(0.0, 0.0, 1.0, 1.0), Point(0.0, 0.0), 30.0)


# ---- wire_bbox ----------------------------------------------------------

def test_wire_bbox_horizontal() -> None:
    """A horizontal wire produces a thin horizontal rectangle."""
    box = wire_bbox(start=Point(10.0, 50.0), end=Point(20.0, 50.0))
    # The box should be wider than it is tall.
    assert box.width > box.height
    # Width should be at least the wire length minus the clearance.
    assert box.width >= 10.0
    # Height should be at most ~ 2 * clearance + thickness.
    expected_height = 2 * DEFAULT_WIRE_CLEARANCE_MM + 0.254
    assert math.isclose(box.height, expected_height, rel_tol=0.0, abs_tol=0.01)


def test_wire_bbox_vertical() -> None:
    """A vertical wire produces a thin vertical rectangle."""
    box = wire_bbox(start=Point(50.0, 10.0), end=Point(50.0, 30.0))
    assert box.height > box.width
    assert box.height >= 20.0


def test_wire_bbox_centred_on_segment_midpoint() -> None:
    """The bbox centre lies on the wire's midpoint."""
    start = Point(0.0, 0.0)
    end = Point(20.0, 0.0)
    box = wire_bbox(start, end)
    midpoint = Point(10.0, 0.0)
    assert math.isclose(box.center.x, midpoint.x)
    assert math.isclose(box.center.y, midpoint.y)


# ---- Occupancy ----------------------------------------------------------

def test_occupancy_starts_empty() -> None:
    occupancy = Occupancy()
    assert len(occupancy) == 0
    assert list(occupancy) == []


def test_occupancy_add_grows_index() -> None:
    occupancy = Occupancy()
    box = _box(0.0, 0.0, 5.0, 5.0)
    occupancy.add(box)
    assert len(occupancy) == 1
    assert box in occupancy


def test_occupancy_collides_returns_overlapping_boxes() -> None:
    occupancy = Occupancy()
    a = _box(0.0, 0.0, 5.0, 5.0, owner="a")
    b = _box(10.0, 10.0, 15.0, 15.0, owner="b")
    occupancy.add(a)
    occupancy.add(b)
    candidate = _box(3.0, 3.0, 12.0, 12.0, owner="c")
    hits = occupancy.collides(candidate)
    assert len(hits) == 2
    owners = {h.owner_id for h in hits}
    assert owners == {"a", "b"}


def test_occupancy_collides_respects_ignore_owners() -> None:
    occupancy = Occupancy()
    occupancy.add(_box(0.0, 0.0, 10.0, 10.0, owner="self"))
    candidate = _box(5.0, 5.0, 15.0, 15.0, owner="other")
    assert occupancy.collides(candidate) != []
    assert occupancy.collides(candidate, ignore_owners={"self"}) == []


def test_occupancy_collides_respects_ignore_kinds() -> None:
    occupancy = Occupancy()
    occupancy.add(
        BBox(
            min=Point(0.0, 0.0),
            max=Point(10.0, 10.0),
            kind="junction",
            owner_id="j1",
        )
    )
    candidate = _box(5.0, 5.0, 15.0, 15.0)
    assert occupancy.collides(candidate) != []
    assert occupancy.collides(candidate, ignore_kinds={"junction"}) == []


def test_occupancy_find_free_offset_first_candidate_works() -> None:
    """When the first offset doesn't collide, it's returned immediately."""
    occupancy = Occupancy()
    occupancy.add(_box(0.0, 0.0, 5.0, 5.0))
    candidate = _box(20.0, 20.0, 25.0, 25.0)
    offset = occupancy.find_free_offset(candidate, [(0.0, 0.0), (10.0, 0.0)])
    assert offset == (0.0, 0.0)


def test_occupancy_find_free_offset_skips_colliding_offsets() -> None:
    """The first non-colliding offset wins; earlier collisions are skipped."""
    occupancy = Occupancy()
    occupancy.add(_box(0.0, 0.0, 10.0, 10.0))
    # Candidate starts colliding; offsets (0,0), (5,0), (15,0).
    # (0,0) → still inside, (5,0) → still overlapping, (15,0) → clear.
    candidate = _box(0.0, 0.0, 5.0, 5.0)
    offset = occupancy.find_free_offset(
        candidate,
        [(0.0, 0.0), (5.0, 0.0), (15.0, 0.0)],
    )
    assert offset == (15.0, 0.0)


def test_occupancy_find_free_offset_all_colliding_returns_none() -> None:
    occupancy = Occupancy()
    occupancy.add(_box(0.0, 0.0, 100.0, 100.0))
    candidate = _box(0.0, 0.0, 5.0, 5.0)
    offset = occupancy.find_free_offset(
        candidate,
        [(0.0, 0.0), (10.0, 10.0), (50.0, 50.0)],
    )
    assert offset is None


# ---- validate_overlap ---------------------------------------------------

def _tiny_sheet(
    *,
    symbols: tuple[PlacedSymbol, ...] = (),
    wires: tuple[PlacedWire, ...] = (),
    labels: tuple[PlacedLabel, ...] = (),
    hierarchical_labels: tuple[PlacedHierarchicalLabel, ...] = (),
) -> Sheet:
    return Sheet(
        name="test",
        title="Test Sheet",
        paper_size="A4",
        symbols=symbols,
        wires=wires,
        labels=labels,
        hierarchical_labels=hierarchical_labels,
    )


def test_validate_overlap_empty_sheet_no_results() -> None:
    sheet = _tiny_sheet()
    assert validate_overlap(sheet) == []


def test_validate_overlap_detects_symbol_label_collision() -> None:
    """A label whose bbox sits on top of a symbol's body is flagged."""
    # All Sheet positions must lie on the 1.27mm KiCad grid.
    # Placeholder symbol bbox is 12.7 × 12.7 mm centred on the anchor,
    # so a symbol at (101.6, 101.6) spans (95.25, 95.25) → (107.95, 107.95).
    # A label at (96.52, 101.6) reads to the right; it sits inside.
    symbol = PlacedSymbol(
        lib_id="Device:R",
        reference="R1",
        value="10k",
        position=Point(101.6, 101.6),
        footprint="Resistor_SMD:R_0402_1005Metric",
    )
    label = PlacedLabel(
        net_name="OVERLAPPING_LABEL",
        position=Point(96.52, 101.6),
    )
    sheet = _tiny_sheet(symbols=(symbol,), labels=(label,))
    results = validate_overlap(sheet)
    assert results, "expected at least one overlap result"
    # At least one result should mention both R1 and the label name.
    matches = [
        r for r in results
        if "R1" in r.message and "OVERLAPPING_LABEL" in r.message
    ]
    assert matches, f"expected R1/label collision in results, got: {[r.message for r in results]}"
    # Default severity is warning.
    assert matches[0].severity == "warning"


def test_validate_overlap_strict_flag_changes_severity() -> None:
    """strict=True elevates every overlap to error severity."""
    symbol = PlacedSymbol(
        lib_id="Device:R",
        reference="R1",
        value="10k",
        position=Point(101.6, 101.6),
        footprint="Resistor_SMD:R_0402_1005Metric",
    )
    label = PlacedLabel(
        net_name="OVERLAP",
        position=Point(99.06, 101.6),
    )
    sheet = _tiny_sheet(symbols=(symbol,), labels=(label,))
    results = validate_overlap(sheet, strict=True)
    assert results, "expected at least one overlap"
    assert all(r.severity == "error" for r in results)


def test_validate_overlap_power_symbol_exempt_from_symbol_symbol() -> None:
    """Two #PWR symbols at the same anchor are allowed."""
    pwr_a = PlacedSymbol(
        lib_id="power:GND",
        reference="#PWR001",
        value="GND",
        position=Point(50.8, 50.8),
        footprint="",
    )
    pwr_b = PlacedSymbol(
        lib_id="power:GND",
        reference="#PWR002",
        value="GND",
        position=Point(50.8, 50.8),
        footprint="",
    )
    sheet = _tiny_sheet(symbols=(pwr_a, pwr_b))
    results = validate_overlap(sheet)
    symbol_symbol = [r for r in results if r.rule_id == "overlap.symbol_symbol"]
    assert symbol_symbol == []


def test_validate_overlap_label_label_collision_flagged() -> None:
    """Two labels at the same anchor produce a label×label overlap."""
    label_a = PlacedLabel(net_name="VBUS", position=Point(101.6, 101.6))
    label_b = PlacedLabel(net_name="VCC", position=Point(101.6, 101.6))
    sheet = _tiny_sheet(labels=(label_a, label_b))
    results = validate_overlap(sheet)
    label_label = [r for r in results if r.rule_id == "overlap.label_label"]
    assert label_label, "expected label×label overlap"
    assert "VBUS" in label_label[0].message and "VCC" in label_label[0].message


def test_validate_overlap_disjoint_primitives_no_results() -> None:
    """Well-separated primitives produce zero overlaps."""
    symbol = PlacedSymbol(
        lib_id="Device:R",
        reference="R1",
        value="10k",
        position=Point(50.8, 50.8),
        footprint="Resistor_SMD:R_0402_1005Metric",
    )
    label = PlacedLabel(
        net_name="FAR_AWAY",
        position=Point(200.66, 149.86),
    )
    sheet = _tiny_sheet(symbols=(symbol,), labels=(label,))
    assert validate_overlap(sheet) == []


def test_validate_overlap_uses_placeholder_when_geometry_missing() -> None:
    """Without a geometry cache, the validator falls back to 12.7 mm boxes."""
    symbol_a = PlacedSymbol(
        lib_id="Device:R",
        reference="R1",
        value="10k",
        position=Point(50.8, 50.8),
        footprint="Resistor_SMD:R_0402_1005Metric",
    )
    symbol_b = PlacedSymbol(
        lib_id="Device:R",
        reference="R2",
        value="10k",
        # Within 12.7mm placeholder bbox of R1 (gap of 5.08mm)
        position=Point(55.88, 50.8),
        footprint="Resistor_SMD:R_0402_1005Metric",
    )
    sheet = _tiny_sheet(symbols=(symbol_a, symbol_b))
    results = validate_overlap(sheet, geometry=None)
    sym_sym = [r for r in results if r.rule_id == "overlap.symbol_symbol"]
    assert sym_sym, "placeholder symbol bboxes should overlap when anchors are close"


def test_validate_overlap_placeholder_bbox_helper() -> None:
    """The placeholder helper returns a centred 12.7mm box."""
    box = placeholder_symbol_bbox(Point(100.0, 100.0), owner_id="x", side_mm=12.7)
    assert math.isclose(box.width, 12.7)
    assert math.isclose(box.height, 12.7)
    assert math.isclose(box.center.x, 100.0)
    assert math.isclose(box.center.y, 100.0)
