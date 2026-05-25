"""Generic ReferenceCircuit conformance checks."""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.datasheets.fetch_datasheets import _is_acceptable_datasheet_pdf
from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.registry import get_part
from scripts.carrier.validate.report import ValidationResult

CARRIER_DIR = Path(__file__).resolve().parents[1]


def run_refcircuit_validation() -> list[ValidationResult]:
    results: list[ValidationResult] = []

    for circuit_name, ref_circuit in REFCIRCUITS.items():
        if ref_circuit.local_datasheet_path:
            local_pdf = CARRIER_DIR / ref_circuit.local_datasheet_path
            if not local_pdf.exists():
                results.append(
                    ValidationResult(
                        rule_id="refcircuit.missing_pdf",
                        severity="error",
                        message=(
                            f"{circuit_name} local datasheet missing: "
                            f"{ref_circuit.local_datasheet_path} "
                            "(run: python -m scripts.carrier.datasheets.fetch_datasheets --force)"
                        ),
                        location=f"refcircuits/{circuit_name}",
                    )
                )
            elif not _is_acceptable_datasheet_pdf(local_pdf.read_bytes()):
                results.append(
                    ValidationResult(
                        rule_id="refcircuit.invalid_pdf",
                        severity="error",
                        message=(
                            f"{circuit_name} local datasheet is not a valid "
                            f"datasheet PDF: {ref_circuit.local_datasheet_path}"
                        ),
                        location=f"refcircuits/{circuit_name}",
                    )
                )

        for external_part in ref_circuit.external_parts:
            try:
                get_part(external_part.part_token)
            except KeyError:
                results.append(
                    ValidationResult(
                        rule_id="refcircuit.unknown_token",
                        severity="error",
                        message=(
                            f"{circuit_name} external part references unknown token "
                            f"{external_part.part_token!r} "
                            f"(pin {external_part.from_pin})"
                        ),
                        location=f"refcircuits/{circuit_name}",
                    )
                )

        for strap_pin in ref_circuit.strap_pins:
            if not strap_pin.pin or not strap_pin.tied_to:
                results.append(
                    ValidationResult(
                        rule_id="refcircuit.invalid_strap",
                        severity="error",
                        message=f"{circuit_name} has incomplete strap pin definition",
                        location=f"refcircuits/{circuit_name}",
                    )
                )

    return results
