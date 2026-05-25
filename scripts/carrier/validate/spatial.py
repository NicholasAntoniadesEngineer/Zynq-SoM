"""Spatial overlap checks powered by kicad-skip."""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.validate.report import ValidationResult


def run_spatial_validation(schematic_paths: tuple[Path, ...]) -> list[ValidationResult]:
    try:
        import skip
    except ImportError as import_error:
        raise RuntimeError(
            "kicad-skip is required for spatial validation; "
            "install scripts/requirements.txt"
        ) from import_error

    results: list[ValidationResult] = []
    for schematic_path in schematic_paths:
        if not schematic_path.exists():
            results.append(
                ValidationResult(
                    rule_id="spatial.missing_file",
                    severity="error",
                    message=f"Schematic file not found: {schematic_path}",
                    location=str(schematic_path),
                )
            )
            continue

        try:
            schematic = skip.Schematic(str(schematic_path))
        except Exception as load_error:
            results.append(
                ValidationResult(
                    rule_id="spatial.load_failed",
                    severity="error",
                    message=f"Failed to load {schematic_path.name}: {load_error}",
                    location=str(schematic_path),
                )
            )
            continue

        symbol_list = list(schematic.symbol)
        if len(symbol_list) == 0:
            results.append(
                ValidationResult(
                    rule_id="spatial.zero_symbols",
                    severity="error",
                    message=f"Block {schematic_path.stem!r} emitted zero symbols",
                    location=str(schematic_path),
                )
            )

        for symbol in symbol_list:
            try:
                value_text = str(symbol.property.get("Value", "")).strip()
                if value_text.startswith("MIGRATE:"):
                    results.append(
                        ValidationResult(
                            rule_id="spatial.migrate_placeholder",
                            severity="error",
                            message=(
                                f"Placeholder symbol {value_text!r} on "
                                f"{schematic_path.name}"
                            ),
                            location=str(schematic_path),
                        )
                    )
            except Exception:
                continue

        anchor_positions: list[tuple[str, float, float]] = []
        for symbol in symbol_list:
            try:
                reference = str(symbol.property["Reference"]).strip()
                anchor = symbol.at
                anchor_positions.append(
                    (reference, float(anchor[0]), float(anchor[1]))
                )
            except Exception:
                continue

        label_positions: list[tuple[str, float, float]] = []
        for label in getattr(schematic, "label", []):
            try:
                label_positions.append(
                    (str(label.name), float(label.at[0]), float(label.at[1]))
                )
            except Exception:
                continue

        for left_index, (left_ref, left_x, left_y) in enumerate(anchor_positions):
            for right_ref, right_x, right_y in anchor_positions[left_index + 1:]:
                if abs(left_x - right_x) < 0.05 and abs(left_y - right_y) < 0.05:
                    results.append(
                        ValidationResult(
                            rule_id="spatial.coincident_anchors",
                            severity="error",
                            message=(
                                f"Symbols {left_ref!r} and {right_ref!r} share the "
                                f"same anchor on {schematic_path.name}"
                            ),
                            location=str(schematic_path),
                        )
                    )

        for left_index, (left_name, left_x, left_y) in enumerate(label_positions):
            for right_name, right_x, right_y in label_positions[left_index + 1:]:
                if abs(left_x - right_x) < 0.05 and abs(left_y - right_y) < 0.05:
                    results.append(
                        ValidationResult(
                            rule_id="spatial.label_overlap",
                            severity="error",
                            message=(
                                f"Labels {left_name!r} and {right_name!r} overlap on "
                                f"{schematic_path.name}"
                            ),
                            location=str(schematic_path),
                        )
                    )

    return results
