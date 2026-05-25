"""Shared helpers for per-IC canonical validation."""

from __future__ import annotations

from collections.abc import Callable

from scripts.carrier.model.refcircuit import ReferenceCircuit
from scripts.carrier.validate.report import ValidationResult


ValidatorFn = Callable[[], list[ValidationResult]]


def error(rule_id: str, message: str, location: str) -> ValidationResult:
    return ValidationResult(
        rule_id=rule_id,
        severity="error",
        message=message,
        location=location,
    )


def require_external(
    ref_circuit: ReferenceCircuit,
    *,
    rule_prefix: str,
    location: str,
    from_pin: str,
    part_token: str,
    count: int = 1,
) -> list[ValidationResult]:
    matches = [
        part
        for part in ref_circuit.external_parts
        if part.from_pin == from_pin and part.part_token == part_token
    ]
    actual_count = sum(part.quantity for part in matches)
    if actual_count != count:
        return [
            error(
                f"{rule_prefix}.missing",
                f"{ref_circuit.part_mpn} needs {count}x {part_token} on {from_pin}; "
                f"found {actual_count}",
                location,
            )
        ]
    return []


def require_strap(
    ref_circuit: ReferenceCircuit,
    *,
    rule_prefix: str,
    location: str,
    pin: str,
    tied_to: str,
) -> list[ValidationResult]:
    for strap in ref_circuit.strap_pins:
        if strap.pin == pin and strap.tied_to == tied_to:
            return []
    return [
        error(
            f"{rule_prefix}.strap_missing",
            f"{ref_circuit.part_mpn} requires strap {pin} -> {tied_to}",
            location,
        )
    ]


def require_supply_rail(
    ref_circuit: ReferenceCircuit,
    *,
    rule_prefix: str,
    location: str,
) -> list[ValidationResult]:
    if ref_circuit.supply_rail:
        return []
    supply_pins = frozenset({
        "VDD", "VCC", "VBUS", "VIN", "IN", "REGIN", "+5V", "PVIN",
    })
    has_supply_pin_external = any(
        part.from_pin in supply_pins
        and part.to_net not in {"GND", "CHASSIS_GND", "VSS"}
        for part in ref_circuit.external_parts
    )
    if not has_supply_pin_external:
        return []
    return [
        error(
            f"{rule_prefix}.no_supply_rail",
            f"{ref_circuit.part_mpn} has supply-pin externals but no supply_rail",
            location,
        )
    ]


def require_no_external_flagged(
    ref_circuit: ReferenceCircuit,
    *,
    rule_prefix: str,
    location: str,
    pins: frozenset[str],
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for pin in pins:
        if pin not in ref_circuit.no_external_required:
            results.append(
                error(
                    f"{rule_prefix}.no_external",
                    f"{ref_circuit.part_mpn} pin {pin} must be in no_external_required",
                    location,
                )
            )
    return results


def validate_topology_baseline(
    circuit_key: str,
    ref_circuit: ReferenceCircuit,
    *,
    location: str,
) -> list[ValidationResult]:
    """Minimum topology checks every registered refcircuit must pass."""
    results: list[ValidationResult] = []
    results.extend(
        require_supply_rail(
            ref_circuit,
            rule_prefix=f"{circuit_key}.baseline",
            location=location,
        )
    )
    for strap in ref_circuit.strap_pins:
        if not strap.justification:
            results.append(
                error(
                    f"{circuit_key}.strap_no_justification",
                    f"{circuit_key} strap {strap.pin} lacks justification",
                    location,
                )
            )
    if ref_circuit.no_external_required:
        for pin in ref_circuit.no_external_required:
            has_external = any(
                part.from_pin == pin for part in ref_circuit.external_parts
            )
            if has_external:
                results.append(
                    error(
                        f"{circuit_key}.no_external_conflict",
                        f"{circuit_key} pin {pin} is no_external_required but has externals",
                        location,
                    )
                )
    return results
