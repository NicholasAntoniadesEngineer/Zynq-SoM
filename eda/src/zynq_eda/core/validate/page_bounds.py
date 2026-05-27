"""Page-bounds validator: every placed primitive's FULL BBOX lies inside
the paper margin.

The previous version checked only the anchor point of each primitive, so
a label with its anchor on-page but text extending off-page passed. The
new check uses each primitive's bbox (same bboxes the overlap validator
uses) and reports any primitive whose bbox is not fully inside the
margin-shrunken paper.

Catches the #1 visual failure of the old generator: components/wires/
labels drifting outside the A4 frame.

User rule (Wave F):
    "all wires, label symbols must absolutely must be within page bounds"

The check covers every primitive type the schematic emits: symbol bodies,
wires, local labels, hierarchical labels, global labels, sheet symbols,
no-connects, junctions.
"""

from __future__ import annotations

from zynq_eda.core.layout.bbox import (
    BBox,
    placeholder_symbol_bbox,
    symbol_bbox,
    text_bbox,
    wire_bbox,
)
from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import Sheet
from zynq_eda.core.validate.report import ValidationResult


# Acceptable margin between every placed bbox and the paper edge. A
# generous 5.08 mm (= 200 mil) keeps the KiCad title-block frame clear.
DEFAULT_MARGIN_MM = 5.08


def _bbox_off_page(
    bbox: BBox,
    paper_w: float,
    paper_h: float,
    margin: float,
) -> str | None:
    """Return a human-readable reason if ``bbox`` exits the page, else None."""
    if bbox.min.x < margin:
        return f"min.x={bbox.min.x:.2f} < left margin {margin:.2f}"
    if bbox.min.y < margin:
        return f"min.y={bbox.min.y:.2f} < top margin {margin:.2f}"
    if bbox.max.x > paper_w - margin:
        return f"max.x={bbox.max.x:.2f} > right margin {paper_w - margin:.2f}"
    if bbox.max.y > paper_h - margin:
        return f"max.y={bbox.max.y:.2f} > bottom margin {paper_h - margin:.2f}"
    return None


def validate_page_bounds(
    sheet: Sheet,
    margin_mm: float = DEFAULT_MARGIN_MM,
    *,
    geometry: SymbolGeometryCache | None = None,
) -> list[ValidationResult]:
    """Return errors for any primitive whose BBOX exits the page margin.

    Categories checked:
      1. symbol bodies (full bbox, not just anchor)
      2. wire segments (segment bbox with clearance)
      3. local labels (text bbox)
      4. hierarchical labels (text bbox)
      5. global labels (text bbox)
      6. sheet-symbol rectangles (root sheet's sub-sheet placeholders)
      7. junctions (small disc — anchor check is enough)
      8. no-connects (small X — anchor check is enough)
    """
    results: list[ValidationResult] = []
    paper_w, paper_h = sheet.paper_dimensions

    # --- 1. Symbols (full body bbox) ---
    for sym in sheet.symbols:
        if geometry is not None:
            try:
                bbox = symbol_bbox(
                    lib_id=sym.lib_id,
                    anchor=sym.position,
                    rotation=sym.rotation,
                    cache=geometry,
                    owner_id=f"symbol:{sym.reference}",
                )
            except Exception:
                bbox = placeholder_symbol_bbox(sym.position, owner_id=sym.reference)
        else:
            bbox = placeholder_symbol_bbox(sym.position, owner_id=sym.reference)
        reason = _bbox_off_page(bbox, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.symbol_outside",
                severity="error",
                message=(
                    f"symbol {sym.reference!r} ({sym.value!r}) bbox outside page: "
                    f"{reason}"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 2. Wires (full segment bbox) ---
    for index, wire in enumerate(sheet.wires):
        bbox = wire_bbox(
            start=wire.start,
            end=wire.end,
            owner_id=f"wire_{index}",
        )
        reason = _bbox_off_page(bbox, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.wire_outside",
                severity="error",
                message=(
                    f"wire #{index} ({wire.start.as_tuple()} → "
                    f"{wire.end.as_tuple()}) bbox outside page: {reason}"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 3. Local labels (text bbox) ---
    for label in sheet.labels:
        justify = "right" if label.rotation in (180.0,) else "left"
        bbox = text_bbox(
            text=label.net_name,
            anchor=label.position,
            rotation=label.rotation,
            justify=justify,
            owner_id=f"label:{label.net_name}",
        )
        reason = _bbox_off_page(bbox, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.label_outside",
                severity="error",
                message=(
                    f"label {label.net_name!r} bbox outside page: {reason}"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 4. Hierarchical labels (text bbox + arrow glyph) ---
    for hlabel in sheet.hierarchical_labels:
        justify = "right" if hlabel.rotation in (180.0,) else "left"
        bbox = text_bbox(
            text=hlabel.net_name,
            anchor=hlabel.position,
            rotation=hlabel.rotation,
            justify=justify,
            owner_id=f"hlabel:{hlabel.net_name}",
            kind="hierarchical_label",
        )
        reason = _bbox_off_page(bbox, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.hlabel_outside",
                severity="error",
                message=(
                    f"hierarchical label {hlabel.net_name!r} bbox outside page: {reason}"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 5. Global labels (text bbox) ---
    for glabel in getattr(sheet, "global_labels", ()):
        justify = "right" if glabel.rotation in (180.0,) else "left"
        bbox = text_bbox(
            text=glabel.net_name,
            anchor=glabel.position,
            rotation=glabel.rotation,
            justify=justify,
            owner_id=f"glabel:{glabel.net_name}",
            kind="hierarchical_label",  # similar shape, reuse padding
        )
        reason = _bbox_off_page(bbox, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.glabel_outside",
                severity="error",
                message=(
                    f"global label {glabel.net_name!r} bbox outside page: {reason}"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 6. Sub-sheet symbols (root index) ---
    for sub in sheet.sheets:
        w, h = sub.size
        bbox = BBox(
            min=Point(sub.position.x, sub.position.y),
            max=Point(sub.position.x + w, sub.position.y + h),
            kind="sheet",
            owner_id=f"sheet:{sub.name}",
        )
        reason = _bbox_off_page(bbox, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.sheet_outside",
                severity="error",
                message=(
                    f"sub-sheet {sub.name!r} bbox outside page: {reason}"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 7. Junctions (anchor check — tiny disc) ---
    for j in sheet.junctions:
        reason = _anchor_check(j.position, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.junction_outside",
                severity="error",
                message=f"junction at {j.position.as_tuple()} outside page: {reason}",
                location=f"{sheet.name}.kicad_sch",
            ))

    # --- 8. No-connects (anchor check — small X glyph) ---
    for nc in sheet.no_connects:
        reason = _anchor_check(nc.position, paper_w, paper_h, margin_mm)
        if reason:
            results.append(ValidationResult(
                rule_id="page_bounds.no_connect_outside",
                severity="error",
                message=f"no-connect at {nc.position.as_tuple()} outside page: {reason}",
                location=f"{sheet.name}.kicad_sch",
            ))

    return results


def _anchor_check(
    p: Point,
    paper_w: float,
    paper_h: float,
    margin: float,
) -> str | None:
    if p.x < margin:
        return f"x={p.x:.2f} < left margin {margin}"
    if p.y < margin:
        return f"y={p.y:.2f} < top margin {margin}"
    if p.x > paper_w - margin:
        return f"x={p.x:.2f} > right margin {paper_w - margin}"
    if p.y > paper_h - margin:
        return f"y={p.y:.2f} > bottom margin {paper_h - margin}"
    return None
