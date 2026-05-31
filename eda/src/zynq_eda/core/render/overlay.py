"""Draw validator findings onto a rendered schematic PNG.

This closes the loop the Laws demand — "the render is the supreme judge,"
and "a check that reports clean while the page shows a collision is a
broken check." Each spatial finding carries the two bboxes that triggered
it (:attr:`ValidationResult.bbox_a` / ``bbox_b``); here we draw them on the
exact pixels KiCad plotted, via the :class:`PageRaster` mm→pixel transform.
A human (or agent) then confirms every drawn box sits on a real visual
collision, and — by eye against the same render — that every visible crowd
carries a box. Where they disagree, the check is fixed to match the eye.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw

from zynq_eda.core.render.raster import PageRaster

_OVERLAP_COLOR = (220, 30, 30)  # red — true overlap
_CROWD_COLOR = (240, 140, 0)  # amber — sub-clearance crowding


def _is_crowding(finding) -> bool:
    """True if the finding is a near-touch (boxes don't actually intersect)."""
    a = getattr(finding, "bbox_a", None)
    b = getattr(finding, "bbox_b", None)
    if a is None or b is None:
        return False
    # Disjoint-but-close ⇒ crowding; actually-intersecting ⇒ overlap.
    return not a.intersects(b)


def overlay_findings(
    raster: PageRaster,
    findings: Iterable,
    out_path: Path,
    *,
    box_width: int = 3,
) -> Path:
    """Draw each finding's bbox pair on ``raster``'s PNG → ``out_path``.

    True overlaps are outlined in red, sub-clearance crowding in amber, so
    the two failure modes are distinguishable at a glance. Returns the
    written path.
    """
    img = Image.open(raster.png_path).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    for finding in findings:
        color = _CROWD_COLOR if _is_crowding(finding) else _OVERLAP_COLOR
        fill = (*color, 38)
        for box in (getattr(finding, "bbox_a", None), getattr(finding, "bbox_b", None)):
            if box is None:
                continue
            x0, y0 = raster.mm_to_px(box.min.x, box.min.y)
            x1, y1 = raster.mm_to_px(box.max.x, box.max.y)
            # Pad a hair so zero-area / hairline (wire) boxes stay visible.
            draw.rectangle(
                [x0 - 1, y0 - 1, x1 + 1, y1 + 1],
                outline=color,
                width=box_width,
                fill=fill,
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
