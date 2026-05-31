"""Shared validation-result types + Markdown reporter.

Every validator returns a list of :class:`ValidationResult` instances; the
:class:`ValidationReport` aggregates them across the pipeline, writes the
``validation_report.md`` / ``audit_report.md`` artefacts, and exposes counts
for the build log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationResult:
    """One outcome from one validator rule.

    ``bbox_a`` / ``bbox_b`` optionally carry the two geometric bboxes that
    triggered a spatial finding (overlap / crowding). They are kept as
    opaque objects (avoiding a layout import here) and consumed by the
    render overlay (:mod:`zynq_eda.core.render.overlay`) to draw each
    finding exactly where it sits on the rendered page — the mechanism
    that lets a human confirm the validator matches the eye.
    """

    rule_id: str
    severity: Severity
    message: str
    location: str = ""
    bbox_a: Any | None = None
    bbox_b: Any | None = None

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

    def add(self, result: ValidationResult) -> None:
        self.results.append(result)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for r in self.results if r.severity == "info")

    @property
    def is_clean(self) -> bool:
        return self.error_count == 0

    def write_markdown(self, report_path: Path, title: str) -> None:
        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        report_lines: list[str] = []
        report_lines.append(f"# {title}")
        report_lines.append("")
        report_lines.append(f"Generated: {timestamp_iso}")
        report_lines.append("")
        report_lines.append(
            f"**Errors:** {self.error_count}  "
            f"**Warnings:** {self.warning_count}  "
            f"**Info:** {self.info_count}"
        )
        report_lines.append("")
        if not self.results:
            report_lines.append("All checks passed with no findings.")
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
