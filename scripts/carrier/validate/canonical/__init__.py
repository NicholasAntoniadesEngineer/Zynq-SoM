"""Per-IC reference-circuit canonical validation package."""

from __future__ import annotations

from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.validate.canonical.registry import (
    CANONICAL_VALIDATORS,
    missing_registry_keys,
    run_registered_validators,
)
from scripts.carrier.validate.canonical.rules import error
from scripts.carrier.validate.report import ValidationResult


def _require_external(
    ref_circuit,
    *,
    rule_prefix: str,
    location: str,
    from_pin: str,
    part_token: str,
    count: int = 1,
) -> list[ValidationResult]:
    from scripts.carrier.validate.canonical.rules import require_external

    return require_external(
        ref_circuit,
        rule_prefix=rule_prefix,
        location=location,
        from_pin=from_pin,
        part_token=part_token,
        count=count,
    )


def validate_verified_metadata() -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for circuit_name, ref_circuit in REFCIRCUITS.items():
        if not ref_circuit.minimum_circuit_verified:
            results.append(
                error(
                    "refcircuit.unverified",
                    f"{circuit_name} minimum_circuit_verified is False",
                    f"refcircuits/{circuit_name}",
                )
            )
        if not ref_circuit.local_datasheet_path:
            results.append(
                error(
                    "refcircuit.no_local_pdf",
                    f"{circuit_name} missing local_datasheet_path",
                    f"refcircuits/{circuit_name}",
                )
            )
        if not ref_circuit.app_circuit_page:
            results.append(
                error(
                    "refcircuit.no_page_cite",
                    f"{circuit_name} missing app_circuit_page",
                    f"refcircuits/{circuit_name}",
                )
            )
        for external_part in ref_circuit.external_parts:
            if not external_part.justification:
                results.append(
                    error(
                        "refcircuit.no_justification",
                        f"{circuit_name} {external_part.part_token} lacks justification",
                        f"refcircuits/{circuit_name}",
                    )
                )
    return results


def validate_per_refcircuit_minimum() -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for circuit_name, ref_circuit in REFCIRCUITS.items():
        if not ref_circuit.minimum_circuit_verified:
            continue
        if ref_circuit.external_parts or ref_circuit.strap_pins:
            continue
        if ref_circuit.no_external_required:
            continue
        results.append(
            error(
                "refcircuit.no_externals",
                f"{circuit_name} has no external_parts, strap_pins, or no_external_required",
                f"refcircuits/{circuit_name}",
            )
        )
    return results


def validate_all_refcircuit_externals() -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for circuit_name, ref_circuit in REFCIRCUITS.items():
        location = f"refcircuits/{circuit_name}"
        for external_part in ref_circuit.external_parts:
            results.extend(
                _require_external(
                    ref_circuit,
                    rule_prefix=f"{circuit_name}.ext",
                    location=location,
                    from_pin=external_part.from_pin,
                    part_token=external_part.part_token,
                    count=external_part.quantity,
                )
            )
    return results


def run_canonical_validation() -> list[ValidationResult]:
    results: list[ValidationResult] = []
    results.extend(validate_verified_metadata())
    results.extend(validate_per_refcircuit_minimum())
    results.extend(run_registered_validators())
    results.extend(validate_all_refcircuit_externals())
    return results


__all__ = [
    "CANONICAL_VALIDATORS",
    "run_canonical_validation",
    "validate_verified_metadata",
    "validate_per_refcircuit_minimum",
    "validate_all_refcircuit_externals",
]
