"""Run all validators and write ``validation_report.md``."""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.validate.bom import run_bom_validation
from scripts.carrier.validate.canonical import run_canonical_validation
from scripts.carrier.validate.erc import run_erc
from scripts.carrier.validate.refcircuit import run_refcircuit_validation
from scripts.carrier.validate.report import ValidationReport, ValidationResult
from scripts.carrier.validate.spatial import run_spatial_validation


def run_all(
    schematic_paths: tuple[Path, ...],
    root_schematic_path: Path,
    report_path: Path,
    *,
    skip_erc: bool = False,
) -> tuple[int, int]:
    """Execute every validator and write the Markdown report.

    Returns:
        ``(strict_failures, warning_count)`` where strict_failures counts
        ``severity == "error"`` results across all validators including ERC.
    """
    report = ValidationReport()
    report.extend(run_canonical_validation())
    report.extend(run_bom_validation())
    report.extend(run_refcircuit_validation())
    report.extend(run_spatial_validation(schematic_paths))

    if not skip_erc:
        erc_results, _erc_errors, _erc_warnings = run_erc(root_schematic_path)
        report.extend(erc_results)

    report.write_markdown(report_path)
    return report.error_count, report.warning_count


__all__ = [
    "ValidationReport",
    "ValidationResult",
    "run_all",
]
