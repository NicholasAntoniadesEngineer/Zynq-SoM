"""Permanent regression tests for the label-rotation bbox model.

The validator's ``_label_text_bbox`` / ``_hierarchical_label_text_bbox``
must match KiCad's actual rendering of ``(label "FOO" (at X Y R))`` for
R ∈ {0, 90, 180, 270}. These tests pin down the directional semantics so
future refactors don't silently flip a justify or rotation and start
mis-locating every label on every sheet.

KiCad's convention (verified against KiCad 9.x rendering and the
schematic-editor source ``label_renderer.cpp``):

  * **rotation 0**   — text reads LEFT-TO-RIGHT. Anchor sits at the
    LEFT edge of the rendered text; bbox extends to the RIGHT of the
    anchor.
  * **rotation 90**  — text reads BOTTOM-TO-TOP (rotated 90° CCW). The
    anchor is at the BOTTOM of the rotated text; bbox extends UPWARD
    (smaller Y in KiCad page coords).
  * **rotation 180** — text reads NORMALLY left-to-right but the anchor
    is at the RIGHT edge. Bbox extends to the LEFT of the anchor. KiCad
    does NOT render the text upside-down — it's effectively a
    right-justified label, mirroring rotation 0.
  * **rotation 270** — text reads TOP-TO-BOTTOM (rotated 90° CW). Anchor
    at TOP of rotated text; bbox extends DOWNWARD (larger Y).

The bbox model lives in
:mod:`zynq_eda.core.validate.overlap` (functions
``_label_text_bbox`` and ``_hierarchical_label_text_bbox``) and
:mod:`zynq_eda.core.layout._builder` (functions ``_label_bbox`` and
``_hierarchical_label_bbox``). Both sets must agree.
"""

from __future__ import annotations

import math

import pytest

from zynq_eda.core.layout._builder import (
    _hierarchical_label_bbox as builder_hlabel_bbox,
    _label_bbox as builder_label_bbox,
)
from zynq_eda.core.layout.bbox import (
    DEFAULT_TEXT_HEIGHT_RATIO,
    DEFAULT_TEXT_SIZE_MM,
    DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO,
)
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import (
    PlacedHierarchicalLabel,
    PlacedLabel,
)
from zynq_eda.core.validate.overlap import (
    _hierarchical_label_text_bbox,
    _label_text_bbox,
)


# ---- Constants used in expected-bbox derivation -----------------------------

# Anchor point chosen on the 1.27 mm grid so PlacedLabel's __post_init__
# grid assertion passes.
ANCHOR = Point(100.33, 50.8)

# 5-char label fits the typical net-name density the layout engine emits.
LABEL_TEXT = "VOUT5"


def _expected_width(text: str) -> float:
    return float(len(text)) * DEFAULT_TEXT_SIZE_MM * DEFAULT_TEXT_WIDTH_PER_CHAR_RATIO


def _expected_height() -> float:
    return DEFAULT_TEXT_SIZE_MM * DEFAULT_TEXT_HEIGHT_RATIO


# ---- _label_text_bbox: PlacedLabel by rotation ----------------------------

class TestLabelTextBbox:
    """``rotation`` is the KiCad reading direction — see module docstring."""

    def test_rotation_0_text_extends_right(self) -> None:
        """rotation 0 → bbox extends RIGHT of anchor (text reads L→R)."""
        label = PlacedLabel(net_name=LABEL_TEXT, position=ANCHOR, rotation=0.0)
        box = _label_text_bbox(label)
        width = _expected_width(LABEL_TEXT)
        height = _expected_height()
        assert box.min.x == pytest.approx(ANCHOR.x)
        assert box.max.x == pytest.approx(ANCHOR.x + width)
        assert box.min.y == pytest.approx(ANCHOR.y - height / 2.0)
        assert box.max.y == pytest.approx(ANCHOR.y + height / 2.0)

    def test_rotation_180_text_extends_left(self) -> None:
        """rotation 180 → bbox extends LEFT of anchor (text reads L→R but
        right-justified). This is what causes hier-label arrows to point
        LEFT at left-edge placements — the arrow + text body fall on the
        LEFT of the anchor."""
        label = PlacedLabel(net_name=LABEL_TEXT, position=ANCHOR, rotation=180.0)
        box = _label_text_bbox(label)
        width = _expected_width(LABEL_TEXT)
        height = _expected_height()
        assert box.min.x == pytest.approx(ANCHOR.x - width)
        assert box.max.x == pytest.approx(ANCHOR.x)
        assert box.min.y == pytest.approx(ANCHOR.y - height / 2.0)
        assert box.max.y == pytest.approx(ANCHOR.y + height / 2.0)

    def test_rotation_90_text_extends_upward(self) -> None:
        """rotation 90 → text reads UP. Bbox extends -Y on page (above
        anchor on screen, since +Y is page-down in KiCad)."""
        label = PlacedLabel(net_name=LABEL_TEXT, position=ANCHOR, rotation=90.0)
        box = _label_text_bbox(label)
        width = _expected_width(LABEL_TEXT)
        height = _expected_height()
        assert box.min.x == pytest.approx(ANCHOR.x - height / 2.0)
        assert box.max.x == pytest.approx(ANCHOR.x + height / 2.0)
        assert box.min.y == pytest.approx(ANCHOR.y - width)
        assert box.max.y == pytest.approx(ANCHOR.y)

    def test_rotation_270_text_extends_downward(self) -> None:
        """rotation 270 → text reads DOWN. Bbox extends +Y on page."""
        label = PlacedLabel(net_name=LABEL_TEXT, position=ANCHOR, rotation=270.0)
        box = _label_text_bbox(label)
        width = _expected_width(LABEL_TEXT)
        height = _expected_height()
        assert box.min.x == pytest.approx(ANCHOR.x - height / 2.0)
        assert box.max.x == pytest.approx(ANCHOR.x + height / 2.0)
        assert box.min.y == pytest.approx(ANCHOR.y)
        assert box.max.y == pytest.approx(ANCHOR.y + width)


class TestHierarchicalLabelTextBbox:
    """Hier labels add a leading arrow glyph (one trailing space in the
    text) but otherwise follow the same rotation semantics."""

    def test_rotation_0(self) -> None:
        label = PlacedHierarchicalLabel(
            net_name=LABEL_TEXT, position=ANCHOR, direction="input", rotation=0.0,
        )
        box = _hierarchical_label_text_bbox(label)
        # Decorated text adds one space to net_name.
        width = _expected_width(LABEL_TEXT + " ")
        assert box.min.x == pytest.approx(ANCHOR.x)
        assert box.max.x == pytest.approx(ANCHOR.x + width)

    def test_rotation_180(self) -> None:
        label = PlacedHierarchicalLabel(
            net_name=LABEL_TEXT, position=ANCHOR, direction="input", rotation=180.0,
        )
        box = _hierarchical_label_text_bbox(label)
        width = _expected_width(LABEL_TEXT + " ")
        assert box.min.x == pytest.approx(ANCHOR.x - width)
        assert box.max.x == pytest.approx(ANCHOR.x)


# ---- Cross-check that validator and builder bbox models agree -------------

class TestValidatorAndBuilderAgree:
    """The validator (``_label_text_bbox``) and the live-occupancy builder
    (``_label_bbox``) must produce IDENTICAL bboxes for the same label.
    Drift between the two leads to false-negative validation (the live
    occupancy doesn't see what the validator sees).
    """

    @pytest.mark.parametrize("rotation", [0.0, 90.0, 180.0, 270.0])
    def test_label_bbox_match(self, rotation: float) -> None:
        label = PlacedLabel(net_name=LABEL_TEXT, position=ANCHOR, rotation=rotation)
        validator_box = _label_text_bbox(label)
        builder_box = builder_label_bbox(label)
        assert validator_box.min.x == pytest.approx(builder_box.min.x)
        assert validator_box.max.x == pytest.approx(builder_box.max.x)
        assert validator_box.min.y == pytest.approx(builder_box.min.y)
        assert validator_box.max.y == pytest.approx(builder_box.max.y)

    @pytest.mark.parametrize("rotation", [0.0, 90.0, 180.0, 270.0])
    def test_hlabel_bbox_match(self, rotation: float) -> None:
        label = PlacedHierarchicalLabel(
            net_name=LABEL_TEXT, position=ANCHOR, direction="input", rotation=rotation,
        )
        validator_box = _hierarchical_label_text_bbox(label)
        builder_box = builder_hlabel_bbox(label)
        assert validator_box.min.x == pytest.approx(builder_box.min.x)
        assert validator_box.max.x == pytest.approx(builder_box.max.x)
        assert validator_box.min.y == pytest.approx(builder_box.min.y)
        assert validator_box.max.y == pytest.approx(builder_box.max.y)


# ---- Round-trip via kicad-sch-api ----------------------------------------

class TestKicadRoundTrip:
    """Round-trip a label through ``kicad-sch-api``: write it, parse it
    back, confirm the parsed position + rotation match what we emitted.

    This is a regression guard against accidental sign/unit conversions
    in the s-expression serializer (e.g. a future refactor that converts
    rotation to radians or flips Y at emit time would break this).
    """

    @pytest.mark.parametrize("rotation", [0.0, 90.0, 180.0, 270.0])
    def test_label_roundtrip(self, rotation: float, tmp_path) -> None:
        # Build a minimal sheet with one label, emit it, parse it back.
        from zynq_eda.core.emit.schematic import emit_sheet
        from zynq_eda.core.model.sheet import Sheet

        sheet = Sheet(
            name="rotation_test",
            title="rotation test",
            paper_size="A4",
            symbols=(),
            wires=(),
            labels=(PlacedLabel(
                net_name=LABEL_TEXT,
                position=ANCHOR,
                rotation=rotation,
            ),),
            junctions=(),
            no_connects=(),
            hierarchical_labels=(),
            global_labels=(),
            sheets=(),
            description="",
        )
        out_path = tmp_path / "rotation_test.kicad_sch"
        emit_sheet(sheet, out_path)
        text = out_path.read_text()

        import re
        m = re.search(
            r'\(label "VOUT5"\s*\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)',
            text,
        )
        assert m is not None, f"label not found in emitted sheet:\n{text[:500]}"
        emitted_x = float(m.group(1))
        emitted_y = float(m.group(2))
        emitted_rot = float(m.group(3))
        assert emitted_x == pytest.approx(ANCHOR.x)
        assert emitted_y == pytest.approx(ANCHOR.y)
        assert emitted_rot == pytest.approx(rotation)
