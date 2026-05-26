"""Page-bounds validator: every placed primitive lies inside the paper margins.

Catches the #1 visual failure of the old generator: components/wires/labels
drifting outside the A4 frame.
"""

from __future__ import annotations

from zynq_eda.core.model.sheet import Sheet
from zynq_eda.core.validate.report import ValidationResult


# Acceptable margin between the placed primitive and the paper edge.
DEFAULT_MARGIN_MM = 5.08


def _check_point(
    x: float,
    y: float,
    paper_w: float,
    paper_h: float,
    margin: float,
) -> str | None:
    if x < margin:
        return f"x={x:.2f} < left margin {margin}"
    if x > paper_w - margin:
        return f"x={x:.2f} > right edge {paper_w - margin}"
    if y < margin:
        return f"y={y:.2f} < top margin {margin}"
    if y > paper_h - margin:
        return f"y={y:.2f} > bottom edge {paper_h - margin}"
    return None


def validate_page_bounds(
    sheet: Sheet,
    margin_mm: float = DEFAULT_MARGIN_MM,
) -> list[ValidationResult]:
    """Return errors for any symbol/wire/label outside the paper bounds."""
    results: list[ValidationResult] = []
    # Use the sheet's effective dimensions (honours ``paper_portrait``)
    # rather than the raw landscape entry from :data:`PAPER_DIMENSIONS_MM`.
    paper_w, paper_h = sheet.paper_dimensions

    for symbol in sheet.symbols:
        msg = _check_point(symbol.position.x, symbol.position.y, paper_w, paper_h, margin_mm)
        if msg:
            results.append(ValidationResult(
                rule_id="page_bounds.symbol_outside",
                severity="error",
                message=f"symbol {symbol.reference!r} ({symbol.value!r}) outside page: {msg}",
                location=f"{sheet.name}.kicad_sch",
            ))

    for wire in sheet.wires:
        for point_name, point in (("start", wire.start), ("end", wire.end)):
            msg = _check_point(point.x, point.y, paper_w, paper_h, margin_mm)
            if msg:
                results.append(ValidationResult(
                    rule_id="page_bounds.wire_outside",
                    severity="error",
                    message=f"wire {point_name} outside page: {msg}",
                    location=f"{sheet.name}.kicad_sch",
                ))

    for label in sheet.labels:
        msg = _check_point(label.position.x, label.position.y, paper_w, paper_h, margin_mm)
        if msg:
            results.append(ValidationResult(
                rule_id="page_bounds.label_outside",
                severity="error",
                message=f"label {label.net_name!r} outside page: {msg}",
                location=f"{sheet.name}.kicad_sch",
            ))

    for hlabel in sheet.hierarchical_labels:
        msg = _check_point(hlabel.position.x, hlabel.position.y, paper_w, paper_h, margin_mm)
        if msg:
            results.append(ValidationResult(
                rule_id="page_bounds.hlabel_outside",
                severity="error",
                message=f"hierarchical label {hlabel.net_name!r} outside page: {msg}",
                location=f"{sheet.name}.kicad_sch",
            ))

    return results
