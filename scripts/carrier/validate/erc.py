"""Shell out to ``kicad-cli sch erc`` and fail hard on errors."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.carrier.validate.report import ValidationResult


def run_erc(schematic_path: Path) -> tuple[list[ValidationResult], int, int]:
    """Run KiCad ERC on *schematic_path*.

    Returns:
        (validation_results, error_count, warning_count)
    """
    if not schematic_path.exists():
        raise FileNotFoundError(f"ERC schematic not found: {schematic_path}")

    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli is None:
        raise RuntimeError(
            "kicad-cli not found on PATH; install KiCad 9 to run schematic ERC"
        )

    with tempfile.TemporaryDirectory(prefix="carrier_erc_") as temp_dir:
        report_path = Path(temp_dir) / "erc_report.json"
        command = [
            kicad_cli,
            "sch",
            "erc",
            str(schematic_path),
            "--format",
            "json",
            "--output",
            str(report_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exec_error:
            raise RuntimeError(
                f"Failed to execute kicad-cli sch erc: {exec_error}"
            ) from exec_error

        if completed.returncode != 0 and not report_path.exists():
            raise RuntimeError(
                "kicad-cli sch erc failed before writing a report: "
                f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
            )

        if not report_path.exists():
            return [], 0, 0

        report_data = json.loads(report_path.read_text(encoding="utf-8"))

    results: list[ValidationResult] = []
    error_count = 0
    warning_count = 0

    violations = report_data.get("violations", report_data.get("messages", []))
    if isinstance(violations, dict):
        violations = violations.get("items", [])

    for violation in violations:
        severity_raw = str(violation.get("severity", violation.get("type", "error"))).lower()
        if severity_raw in {"warning", "warn"}:
            severity = "warning"
            warning_count += 1
        else:
            severity = "error"
            error_count += 1
        results.append(
            ValidationResult(
                rule_id=f"erc.{violation.get('code', 'violation')}",
                severity=severity,
                message=violation.get("description", violation.get("message", str(violation))),
                location=str(violation.get("location", schematic_path.name)),
            )
        )

    return results, error_count, warning_count
