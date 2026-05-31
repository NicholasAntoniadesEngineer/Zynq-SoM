"""Per-symbol footprint: the union of its body bbox and all its text bboxes.

Any placement that must guarantee the Laws' clearance needs the COMPLETE
extent a symbol draws — body plus Reference / Value / pin-name / pin-number
text — not just the body rectangle. Crowding is overwhelmingly text-driven
(a cap's ``100n`` value label is wider than the cap body), so separating
bare bodies leaves the text colliding.

Using the union of exactly the bboxes the overlap validator measures
(:func:`symbol_bbox` + :func:`collect_text_bboxes`) means separating
footprints to ``>= VISUAL_CLEARANCE_MM`` guarantees body *and* text
clearance — planner-clean becomes validator-clean by construction.
"""

from __future__ import annotations

from zynq_eda.core.layout.bbox import BBox, placeholder_symbol_bbox, symbol_bbox
from zynq_eda.core.layout.separate import Rect
from zynq_eda.core.layout.text_obstacles import collect_text_bboxes
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import PlacedSymbol


def symbol_footprint(sym: PlacedSymbol, geometry) -> BBox:
    """Return the union bbox of ``sym``'s body and every text it draws.

    The body bbox falls back to a placeholder if geometry can't build it
    (mirroring the validator); the text harvest fails loud (never silently
    drops text) — so the footprint is never an under-estimate that would
    let crowding slip through.
    """
    owner_id = f"symbol:{sym.reference}"
    try:
        body = symbol_bbox(
            lib_id=sym.lib_id,
            anchor=sym.position,
            rotation=sym.rotation,
            cache=geometry,
            owner_id=owner_id,
        )
    except Exception:
        body = placeholder_symbol_bbox(sym.position, owner_id=owner_id)

    boxes = [body, *collect_text_bboxes(sym, geometry, owner_id=owner_id)]
    return BBox(
        min=Point(min(b.min.x for b in boxes), min(b.min.y for b in boxes)),
        max=Point(max(b.max.x for b in boxes), max(b.max.y for b in boxes)),
        kind="symbol",
        owner_id=owner_id,
    )


def bbox_to_rect(bbox: BBox) -> Rect:
    """Convert a :class:`BBox` to a separator :class:`Rect` (centre + size)."""
    return Rect(
        cx=(bbox.min.x + bbox.max.x) / 2.0,
        cy=(bbox.min.y + bbox.max.y) / 2.0,
        w=bbox.max.x - bbox.min.x,
        h=bbox.max.y - bbox.min.y,
    )
