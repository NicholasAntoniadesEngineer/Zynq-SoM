"""Overlap validator: no two placed symbols share the same anchor.

This is a minimum check; Stage 5 will extend it to full bounding-box
overlap detection via the geometry cache.
"""

from __future__ import annotations

from zynq_eda.core.model.sheet import Sheet
from zynq_eda.core.validate.report import ValidationResult


COINCIDENT_TOLERANCE_MM = 0.05


def validate_overlap(sheet: Sheet) -> list[ValidationResult]:
    """Return errors for any two symbols / labels at the same coordinate."""
    results: list[ValidationResult] = []

    # Symbols: coincident anchor (except for power symbols, which legitimately
    # cluster at GND-symbol positions for each cap).
    placed = [
        (symbol.reference, symbol.value, symbol.position)
        for symbol in sheet.symbols
        if not symbol.reference.startswith("#PWR")
    ]
    for left_index, (left_ref, _, left_pos) in enumerate(placed):
        for right_ref, _, right_pos in placed[left_index + 1:]:
            if (
                abs(left_pos.x - right_pos.x) < COINCIDENT_TOLERANCE_MM
                and abs(left_pos.y - right_pos.y) < COINCIDENT_TOLERANCE_MM
            ):
                results.append(ValidationResult(
                    rule_id="overlap.coincident_symbol",
                    severity="error",
                    message=(
                        f"symbols {left_ref!r} and {right_ref!r} share the same anchor "
                        f"({left_pos.x}, {left_pos.y})"
                    ),
                    location=f"{sheet.name}.kicad_sch",
                ))

    # Labels: coincident position
    label_positions = [(label.net_name, label.position) for label in sheet.labels]
    for left_index, (left_name, left_pos) in enumerate(label_positions):
        for right_name, right_pos in label_positions[left_index + 1:]:
            if (
                abs(left_pos.x - right_pos.x) < COINCIDENT_TOLERANCE_MM
                and abs(left_pos.y - right_pos.y) < COINCIDENT_TOLERANCE_MM
            ):
                results.append(ValidationResult(
                    rule_id="overlap.coincident_label",
                    severity="warning",
                    message=(
                        f"labels {left_name!r} and {right_name!r} at same position"
                    ),
                    location=f"{sheet.name}.kicad_sch",
                ))

    return results
