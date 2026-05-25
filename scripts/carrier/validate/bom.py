"""BOM registry coherence checks."""

from __future__ import annotations

from scripts.carrier.registry.parts_registry import REGISTRY, REGISTRY_LIST
from scripts.carrier.registry.parts import ALLOWED_FOOTPRINT_PREFIXES, BOMPart
from scripts.carrier.validate.report import ValidationResult


def run_bom_validation() -> list[ValidationResult]:
    results: list[ValidationResult] = []

    for part in REGISTRY_LIST:
        if not part.lcsc.startswith("C") or not part.lcsc[1:].isdigit():
            results.append(
                ValidationResult(
                    rule_id="bom.lcsc_format",
                    severity="error",
                    message=f"Part {part.token!r} has invalid LCSC {part.lcsc!r}",
                    location="registry/parts_registry.py",
                )
            )

        if part.unit_price_usd < 0:
            results.append(
                ValidationResult(
                    rule_id="bom.negative_price",
                    severity="error",
                    message=f"Part {part.token!r} has negative unit price",
                    location="registry/parts_registry.py",
                )
            )

        if not _footprint_allowed(part):
            results.append(
                ValidationResult(
                    rule_id="bom.footprint_prefix",
                    severity="error",
                    message=(
                        f"Part {part.token!r} footprint {part.footprint!r} "
                        f"does not match allowed prefixes"
                    ),
                    location="registry/parts_registry.py",
                )
            )

        if part.stock_at_lcsc <= 0 and not part.allow_low_stock:
            results.append(
                ValidationResult(
                    rule_id="bom.zero_stock",
                    severity="warning",
                    message=(
                        f"Part {part.token!r} (LCSC {part.lcsc}) reports zero stock"
                    ),
                    location="registry/parts_registry.py",
                )
            )

    if len(REGISTRY) != len(REGISTRY_LIST):
        results.append(
            ValidationResult(
                rule_id="bom.duplicate_token",
                severity="error",
                message="Duplicate tokens detected in REGISTRY",
                location="registry/parts_registry.py",
            )
        )

    return results


def _footprint_allowed(part: BOMPart) -> bool:
    if not part.footprint:
        return False
    return any(
        part.footprint.startswith(prefix)
        for prefix in ALLOWED_FOOTPRINT_PREFIXES
    )
