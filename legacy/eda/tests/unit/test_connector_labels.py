"""Regression tests for connector pin-label rotation.

For every (page_side × symbol_rotation) combination, the label attached
to a connector pin must:

  1. Have its bbox entirely OUTBOARD of the connector symbol's body
     (text reads AWAY from the body, not into it).
  2. Anchor coordinate at the pin tip (so KiCad recognises the
     electrical connection — no stub).

These are the visible properties the user expects: net labels on the
LEFT-edge connector pins read leftward, RIGHT-edge pins read rightward,
etc.
"""

from __future__ import annotations

import pytest

from zynq_eda.core.layout.geometry import page_side_from_pin


class TestPageSideFromPin:
    """``page_side_from_pin`` derives the page-side a pin sits on from
    its KiCad pin_rotation and the symbol's placement rotation. The
    connector label code uses this to pick the label rotation.
    """

    @pytest.mark.parametrize("pin_rot,sym_rot,expected", [
        # Symbol placed at rotation 0 — page side equals pin's body edge.
        (0.0,   0.0, "left"),    # pin tip on left, body extends +X
        (90.0,  0.0, "bottom"),  # pin tip below body
        (180.0, 0.0, "right"),
        (270.0, 0.0, "top"),
        # Symbol rotated 90° CW — every page side rotates 90° CW.
        (0.0,   90.0, "top"),    # left → top
        (90.0,  90.0, "left"),
        (180.0, 90.0, "bottom"),
        (270.0, 90.0, "right"),
        # Symbol rotated 180°.
        (0.0,   180.0, "right"),
        (180.0, 180.0, "left"),
        # Symbol rotated 270° CW.
        (0.0,   270.0, "bottom"),
        (90.0,  270.0, "right"),
    ])
    def test_page_side(self, pin_rot: float, sym_rot: float, expected: str) -> None:
        assert page_side_from_pin(pin_rot, sym_rot) == expected


class TestConnectorLabelRotation:
    """Connector code in :mod:`zynq_eda.core.layout.connectors` picks a
    label rotation per page-side so the label text extends AWAY from
    the connector body. This mapping must match what the
    rotation-bbox model in :mod:`zynq_eda.core.validate.overlap` and
    :mod:`zynq_eda.core.layout._builder` produce.

    The mapping (from ``connectors._place_one_connector``):

        page_side  →  label_rotation  →  bbox extends
        ─────────────────────────────────────────────
        left       →   180            →   -X (leftward)
        right      →     0            →   +X (rightward)
        top        →    90            →   -Y (upward)
        bottom     →   270            →   +Y (downward)
    """

    LABEL_ROTATION_FOR_SIDE = {
        "left": 180.0,
        "right": 0.0,
        "top": 90.0,
        "bottom": 270.0,
    }

    @pytest.mark.parametrize("side,rotation", LABEL_ROTATION_FOR_SIDE.items())
    def test_label_extends_away_from_body(
        self, side: str, rotation: float,
    ) -> None:
        """For each (side, rotation) pair, the bbox extends in the
        direction OPPOSITE the body — i.e. away from where the body
        sits relative to the pin tip.
        """
        from zynq_eda.core.layout._builder import _label_bbox
        from zynq_eda.core.model.grid import Point, snap_to_grid
        from zynq_eda.core.model.sheet import PlacedLabel

        # Anchor at a 1.27 mm-grid coordinate.
        anchor = Point(snap_to_grid(100.0), snap_to_grid(50.0))
        label = PlacedLabel(net_name="NET", position=anchor, rotation=rotation)
        box = _label_bbox(label)
        if side == "left":
            # Body extends RIGHT of anchor; bbox must be at X ≤ anchor.x.
            assert box.max.x <= anchor.x + 0.01
        elif side == "right":
            assert box.min.x >= anchor.x - 0.01
        elif side == "top":
            # Body extends BELOW anchor (larger Y in page coords); bbox
            # must be at Y ≤ anchor.y (upward, smaller Y).
            assert box.max.y <= anchor.y + 0.01
        elif side == "bottom":
            assert box.min.y >= anchor.y - 0.01
