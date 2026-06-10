"""Validation: every gate the pipeline must pass before emitting a board."""

from zynq_eda.core.validate.report import (
    Severity,
    ValidationReport,
    ValidationResult,
)


__all__ = ["Severity", "ValidationReport", "ValidationResult"]
