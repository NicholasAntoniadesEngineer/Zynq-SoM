"""Shared validation-result types + Markdown reporter.

Every validator returns a list of ``ValidationResult`` instances. The
``ValidationReport`` aggregates them across the pipeline, writes the
``validation_report.md`` artefact, and exposes counts for the build log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationResult:
    """One outcome from one validator rule.

    Attributes:
        rule_id: Stable short ID (e.g. ``"fusb302.cc_caps"``,
            ``"erc.unconnected_input"``).
        severity: ``"error"`` blocks output; ``"warning"`` is reported but
            does not fail the build; ``"info"`` is purely informational.
        message: Human-readable explanation including the offending
            object's identifier.
        location: Optional file path + position (e.g.
            ``"sheets/usb_pd.kicad_sch:42"``).
    """

    rule_id: str
    severity: Severity
    message: str
    location: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("ValidationResult.rule_id must be non-empty")
        if self.severity not in ("error", "warning", "info"):
            raise ValueError(
                "ValidationResult.severity must be error/warning/info, got "
                f"{self.severity!r}"
            )
        if not self.message:
            raise ValueError("ValidationResult.message must be non-empty")


@dataclass
class ValidationReport:
    """Aggregator across all validators."""

    results: list[ValidationResult] = field(default_factory=list)

    def extend(self, new_results: list[ValidationResult]) -> None:
        for result in new_results:
            if not isinstance(result, ValidationResult):
                raise TypeError(
                    "ValidationReport.extend received non-ValidationResult: "
                    f"{type(result).__name__}"
                )
            self.results.append(result)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity == "warning")

    @property
    def is_clean(self) -> bool:
        return self.error_count == 0

    def write_markdown(self, report_path: Path) -> None:
        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        report_lines: list[str] = []
        report_lines.append("# Carrier Generator Validation Report")
        report_lines.append("")
        report_lines.append(f"Generated: {timestamp_iso}")
        report_lines.append("")
        report_lines.append(
            f"**Errors:** {self.error_count}  "
            f"**Warnings:** {self.warning_count}"
        )
        report_lines.append("")
        if not self.results:
            report_lines.append("All validators passed with no findings.")
        else:
            for severity in ("error", "warning", "info"):
                bucket = [r for r in self.results if r.severity == severity]
                if not bucket:
                    continue
                report_lines.append(f"## {severity.title()}s ({len(bucket)})")
                report_lines.append("")
                for result in bucket:
                    location_suffix = (
                        f" _({result.location})_" if result.location else ""
                    )
                    report_lines.append(
                        f"- **{result.rule_id}**: {result.message}{location_suffix}"
                    )
                report_lines.append("")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
