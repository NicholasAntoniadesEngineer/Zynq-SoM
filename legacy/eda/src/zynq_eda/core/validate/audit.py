"""Stage 0 component-completeness audit.

Runs *before* any layout work. Verifies that the catalog has every piece
of information the generator will need so the rewrite never silently
produces a half-assembled schematic.

Checks (each emits a :class:`ValidationResult` on failure):

    A1. Every refcircuit has a non-empty, existing ``local_datasheet_path``
        pointing at a PDF that starts with ``%PDF-``.
    A2. Every refcircuit has ``minimum_circuit_verified=True``.
    A3. Every refcircuit has at least one ``ExternalPart`` (except those
        on the allow-list of pure-passive connectors with no externals).
    A4. Every refcircuit has at least one ``LayoutNote``.
    A5. Every ``ExternalPart.part_token`` referenced anywhere in the
        catalog resolves in ``zynq_eda.catalog.registry``.
    A6. Every catalog part has a non-empty footprint string.
    A7. ``IC_INSTANCE_COUNT`` keys match ``REFCIRCUITS`` keys exactly.
    A8. Every catalog part has a non-empty LCSC code matching ``^C\\d+$``.
"""

from __future__ import annotations

from pathlib import Path

from zynq_eda.catalog.components import IC_INSTANCE_COUNT, REFCIRCUITS
from zynq_eda.catalog.registry import REGISTRY
from zynq_eda.core.validate.report import ValidationReport, ValidationResult


# Connectors and passive parts that legitimately have zero external_parts
# (the connector body IS the circuit; no supporting passives).
_ZERO_EXTERNAL_ALLOWED: frozenset[str] = frozenset({
    "PM254R-12-08-H85",       # PMOD header (passive)
    "ZX-PM2.54-2-7PY",        # JTAG header
    "HX-PZ1.27-2x5P-TP",      # SWD header
    "FX10A-168P-SV(91)",      # SoM mate connector (signals only)
    "YLED0603G",              # User LED (driver in parent block)
    "TS-1002S-06026C",        # Tactile switch (debouncing in parent block)
    "DS-04P",                 # DIP switch (debouncing in parent block)
})


_CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog"


def _resolve_datasheet_path(rel_path: str) -> Path:
    """Resolve a refcircuit's ``local_datasheet_path`` against ``catalog/``.

    Modern path: ``components/<part>/datasheet.pdf`` (per-component folder).
    Legacy path (for any refcircuit still using the flat layout):
    ``datasheets/<MPN>.pdf`` — resolved by stripping the prefix.
    """
    candidate = rel_path.lstrip("/")
    if candidate.startswith("datasheets/"):
        # legacy flat layout
        return _CATALOG_DIR / candidate
    return _CATALOG_DIR / candidate


def _check_pdf_magic(pdf_path: Path) -> bool:
    try:
        with pdf_path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def audit_refcircuits(report: ValidationReport) -> None:
    """A1-A4: datasheet presence, verification flag, externals, layout notes."""
    for mpn, refcircuit in sorted(REFCIRCUITS.items()):
        # A1: datasheet path + existence + magic bytes
        if not refcircuit.local_datasheet_path:
            report.add(ValidationResult(
                rule_id="audit.A1.no_local_path",
                severity="error",
                message=f"{mpn!r}: local_datasheet_path is empty",
            ))
        else:
            pdf_path = _resolve_datasheet_path(refcircuit.local_datasheet_path)
            if not pdf_path.is_file():
                report.add(ValidationResult(
                    rule_id="audit.A1.pdf_missing",
                    severity="error",
                    message=(
                        f"{mpn!r}: datasheet not found at "
                        f"{pdf_path.relative_to(_CATALOG_DIR.parent)}"
                    ),
                ))
            elif not _check_pdf_magic(pdf_path):
                report.add(ValidationResult(
                    rule_id="audit.A1.not_a_pdf",
                    severity="error",
                    message=(
                        f"{mpn!r}: file at {pdf_path.name} does not begin with %PDF-"
                    ),
                ))

        # A2: verified flag
        if not refcircuit.minimum_circuit_verified:
            report.add(ValidationResult(
                rule_id="audit.A2.unverified",
                severity="error",
                message=(
                    f"{mpn!r}: minimum_circuit_verified=False — refcircuit "
                    "has not been audited against its datasheet"
                ),
            ))

        # A3: external parts
        if not refcircuit.external_parts and mpn not in _ZERO_EXTERNAL_ALLOWED:
            report.add(ValidationResult(
                rule_id="audit.A3.no_externals",
                severity="warning",
                message=(
                    f"{mpn!r}: external_parts is empty (allowed only for "
                    "passive connectors with no required supporting parts)"
                ),
            ))

        # A4: layout notes
        if not refcircuit.layout_notes:
            report.add(ValidationResult(
                rule_id="audit.A4.no_layout_notes",
                severity="warning",
                message=(
                    f"{mpn!r}: layout_notes is empty — at least one note "
                    "(rule/guideline/info) should accompany every IC"
                ),
            ))


def audit_part_tokens(report: ValidationReport) -> None:
    """A5: every part_token referenced by any refcircuit resolves in REGISTRY."""
    referenced_tokens: set[str] = set()
    for mpn, refcircuit in REFCIRCUITS.items():
        for external in refcircuit.external_parts:
            referenced_tokens.add(external.part_token)
    missing_tokens = sorted(token for token in referenced_tokens if token not in REGISTRY)
    for missing_token in missing_tokens:
        report.add(ValidationResult(
            rule_id="audit.A5.unknown_part_token",
            severity="error",
            message=(
                f"part_token {missing_token!r} is referenced in a refcircuit "
                "but not in the parts registry"
            ),
        ))


def audit_registry_completeness(report: ValidationReport) -> None:
    """A6 + A8: every catalog part has a non-empty footprint + valid LCSC code."""
    for token, part in sorted(REGISTRY.items()):
        if not part.footprint:
            report.add(ValidationResult(
                rule_id="audit.A6.no_footprint",
                severity="error",
                message=f"part_token {token!r}: footprint is empty",
            ))
        lcsc = part.lcsc
        if not lcsc or not lcsc.startswith("C") or not lcsc[1:].isdigit():
            report.add(ValidationResult(
                rule_id="audit.A8.invalid_lcsc",
                severity="error",
                message=(
                    f"part_token {token!r}: lcsc {lcsc!r} does not match C\\d+"
                ),
            ))


def audit_instance_counts(report: ValidationReport) -> None:
    """A7: IC_INSTANCE_COUNT keys equal REFCIRCUITS keys exactly."""
    refcircuit_keys = set(REFCIRCUITS.keys())
    instance_keys = set(IC_INSTANCE_COUNT.keys())
    in_refcircuits_not_in_counts = sorted(refcircuit_keys - instance_keys)
    in_counts_not_in_refcircuits = sorted(instance_keys - refcircuit_keys)
    for orphan in in_refcircuits_not_in_counts:
        report.add(ValidationResult(
            rule_id="audit.A7.missing_in_instance_count",
            severity="error",
            message=(
                f"{orphan!r}: present in REFCIRCUITS but missing from "
                "IC_INSTANCE_COUNT"
            ),
        ))
    for orphan in in_counts_not_in_refcircuits:
        report.add(ValidationResult(
            rule_id="audit.A7.missing_in_refcircuits",
            severity="error",
            message=(
                f"{orphan!r}: present in IC_INSTANCE_COUNT but missing from "
                "REFCIRCUITS"
            ),
        ))


def run_audit() -> ValidationReport:
    """Run all audit checks and return the aggregated report."""
    report = ValidationReport()
    audit_refcircuits(report)
    audit_part_tokens(report)
    audit_registry_completeness(report)
    audit_instance_counts(report)
    return report


def summary_line(report: ValidationReport) -> str:
    return (
        f"refcircuits={len(REFCIRCUITS)}, "
        f"parts={len(REGISTRY)}, "
        f"errors={report.error_count}, "
        f"warnings={report.warning_count}"
    )
