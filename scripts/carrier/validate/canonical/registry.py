"""Registry mapping each REFCIRCUITS key to its canonical validator."""

from __future__ import annotations

from collections.abc import Callable

from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.validate.canonical import validators
from scripts.carrier.validate.report import ValidationResult


ValidatorFn = Callable[[], list[ValidationResult]]


CANONICAL_VALIDATORS: dict[str, ValidatorFn] = {
    "FUSB302BMPX": validators.validate_fusb302bmpx,
    "USBLC6-4SC6": validators.validate_usblc6_4sc6,
    "TPS2051CDBVR": validators.validate_tps2051cdbvr,
    "TPD12S016PWR_TX": validators.validate_tpd12s016pwr_tx,
    "TPD12S016PWR_RX": validators.validate_tpd12s016pwr_rx,
    "CP2102N-A02-GQFN24R": validators.validate_cp2102n,
    "INA226AIDGSR": validators.validate_ina226,
    "DS3231SN#": validators.validate_ds3231,
    "24LC256T-I/SN": validators.validate_eeprom_24lc256,
    "24LC256T-I/SN_EDID": validators.validate_eeprom_24lc256_edid,
    "TLV75718PDBVR": validators.validate_tlv75718,
    "TLV75725PDBVR": validators.validate_tlv75725,
    "TLV75733PDBVR": validators.validate_tlv75733,
    "HX5008NLT": validators.validate_hx5008,
    "USBC_SINK": validators.validate_usbc_sink,
    "HDMI_A": validators.validate_hdmi_a,
    "DM3AT-SF-PEJM5": validators.validate_microsd,
    "RJHSE5380": validators.validate_rj45,
    "SS14": validators.validate_ss14,
    "FX10A-168P-SV(91)": validators.validate_fmc_lpc,
    "PM254R-12-08-H85": validators.validate_pmod,
    "FPC-05F-40PH20": validators.validate_lvds_lcd,
    "1.0-15P": validators.validate_mipi_camera,
    "ZX-PM2.54-2-7PY": validators.validate_jtag_header,
    "HX-PZ1.27-2x5P-TP": validators.validate_swd_header,
    "KH-SMA-P-8496": validators.validate_sma_clock,
    "YLED0603G": validators.validate_user_led,
    "TS-1002S-06026C": validators.validate_tactile_switch,
    "DS-04P": validators.validate_dip_switch,
}


def registered_circuit_keys() -> frozenset[str]:
    return frozenset(CANONICAL_VALIDATORS.keys())


def missing_registry_keys() -> list[str]:
    return sorted(set(REFCIRCUITS.keys()) - set(CANONICAL_VALIDATORS.keys()))


def run_registered_validators() -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for circuit_key in sorted(CANONICAL_VALIDATORS.keys()):
        validator = CANONICAL_VALIDATORS[circuit_key]
        results.extend(validator())
    extra = missing_registry_keys()
    for circuit_key in extra:
        results.append(
            ValidationResult(
                rule_id="canonical.registry.missing",
                severity="error",
                message=f"No canonical validator registered for {circuit_key}",
                location="validate/canonical/registry.py",
            )
        )
    return results
