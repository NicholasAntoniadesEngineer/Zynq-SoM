"""Per-IC canonical topology validators (one registered function per REFCIRCUITS key)."""

from __future__ import annotations

from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.refcircuits.fusb302 import FUSB302_REFCIRCUIT
from scripts.carrier.refcircuits.hx5008nlt import HX5008NLT_REFCIRCUIT
from scripts.carrier.refcircuits.ina226 import INA226_REFCIRCUIT
from scripts.carrier.refcircuits.tpd12s016 import (
    TPD12S016_RX_REFCIRCUIT,
    TPD12S016_TX_REFCIRCUIT,
)
from scripts.carrier.validate.canonical.rules import (
    error,
    require_external,
    require_strap,
    require_supply_rail,
    validate_topology_baseline,
)
from scripts.carrier.validate.report import ValidationResult


def _loc(circuit_key: str) -> str:
    return f"refcircuits/{circuit_key}"


def _baseline(circuit_key: str) -> list[ValidationResult]:
    return validate_topology_baseline(
        circuit_key,
        REFCIRCUITS[circuit_key],
        location=_loc(circuit_key),
    )


def validate_fusb302bmpx() -> list[ValidationResult]:
    location = "refcircuits/fusb302.py"
    ref_circuit = FUSB302_REFCIRCUIT
    results = _baseline("FUSB302BMPX")
    cc_caps = [
        part for part in ref_circuit.external_parts if part.from_pin in {"CC1", "CC2"}
    ]
    if len(cc_caps) != 2:
        results.append(
            error(
                "fusb302.cc_caps",
                f"FUSB302 needs 200pF caps on CC1/CC2; found {len(cc_caps)}",
                location,
            )
        )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="fusb302.vbus_div_lower",
            location=location,
            from_pin="VBUS",
            part_token="100k_0402_1%",
        )
    )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="fusb302.vbus_div_upper",
            location=location,
            from_pin="VBUS",
            part_token="1M_0402_1%",
        )
    )
    return results


def validate_usblc6_4sc6() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["USBLC6-4SC6"]
    results = _baseline("USBLC6-4SC6")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="usblc6.vbus_bypass",
            location=_loc("USBLC6-4SC6"),
            from_pin="VBUS",
            part_token="100n_0402_X7R",
        )
    )
    return results


def validate_tps2051cdbvr() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["TPS2051CDBVR"]
    results = _baseline("TPS2051CDBVR")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tps2051.in_cap",
            location=_loc("TPS2051CDBVR"),
            from_pin="IN",
            part_token="1u_0402_X7R",
        )
    )
    return results


def validate_tpd12s016pwr_tx() -> list[ValidationResult]:
    ref_circuit = TPD12S016_TX_REFCIRCUIT
    location = "refcircuits/tpd12s016.py (TX)"
    results = _baseline("TPD12S016PWR_TX")
    for pin in ("VCCA", "VCCB"):
        results.extend(
            require_external(
                ref_circuit,
                rule_prefix=f"tpd12.tx.{pin.lower()}_bulk",
                location=location,
                from_pin=pin,
                part_token="1u_0402_X7R",
            )
        )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tpd12.tx.i2c_pullup",
            location=location,
            from_pin="SDA_B",
            part_token="4k7_0402_1%",
        )
    )
    return results


def validate_tpd12s016pwr_rx() -> list[ValidationResult]:
    ref_circuit = TPD12S016_RX_REFCIRCUIT
    location = "refcircuits/tpd12s016.py (RX)"
    results = _baseline("TPD12S016PWR_RX")
    for pin in ("VCCA", "VCCB"):
        results.extend(
            require_external(
                ref_circuit,
                rule_prefix=f"tpd12.rx.{pin.lower()}_bulk",
                location=location,
                from_pin=pin,
                part_token="1u_0402_X7R",
            )
        )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tpd12.rx.i2c_pullup",
            location=location,
            from_pin="SDA_B",
            part_token="4k7_0402_1%",
        )
    )
    return results


def validate_cp2102n() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["CP2102N-A02-GQFN24R"]
    results = _baseline("CP2102N-A02-GQFN24R")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="cp2102n.vdd_bulk",
            location=_loc("CP2102N-A02-GQFN24R"),
            from_pin="VDD",
            part_token="4u7_0402_X5R",
        )
    )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="cp2102n.rst_pullup",
            location=_loc("CP2102N-A02-GQFN24R"),
            from_pin="RST_N",
            part_token="10k_0402_1%",
        )
    )
    return results


def validate_ina226() -> list[ValidationResult]:
    ref_circuit = INA226_REFCIRCUIT
    location = "refcircuits/ina226.py"
    results = _baseline("INA226AIDGSR")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="ina226.input_filter",
            location=location,
            from_pin="IN+",
            part_token="10R_0402_1%",
        )
    )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="ina226.diff_cap",
            location=location,
            from_pin="IN+",
            part_token="100n_0402_X7R",
        )
    )
    return results


def validate_ds3231() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["DS3231SN#"]
    results = _baseline("DS3231SN#")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="ds3231.vcc_bypass",
            location=_loc("DS3231SN#"),
            from_pin="VCC",
            part_token="100n_0402_X7R",
        )
    )
    return results


def validate_eeprom_24lc256() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["24LC256T-I/SN"]
    results = _baseline("24LC256T-I/SN")
    results.extend(
        require_strap(
            ref_circuit,
            rule_prefix="eeprom24lc256",
            location=_loc("24LC256T-I/SN"),
            pin="A0",
            tied_to="GND",
        )
    )
    return results


def validate_eeprom_24lc256_edid() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["24LC256T-I/SN_EDID"]
    results = _baseline("24LC256T-I/SN_EDID")
    results.extend(
        require_supply_rail(
            ref_circuit,
            rule_prefix="eeprom_edid",
            location=_loc("24LC256T-I/SN_EDID"),
        )
    )
    return results


def validate_tlv75718() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["TLV75718PDBVR"]
    results = _baseline("TLV75718PDBVR")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tlv75718.in_cap",
            location=_loc("TLV75718PDBVR"),
            from_pin="IN",
            part_token="1u_0402_X7R",
        )
    )
    return results


def validate_tlv75725() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["TLV75725PDBVR"]
    results = _baseline("TLV75725PDBVR")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tlv75725.out_cap",
            location=_loc("TLV75725PDBVR"),
            from_pin="OUT",
            part_token="1u_0402_X7R",
        )
    )
    return results


def validate_tlv75733() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["TLV75733PDBVR"]
    results = _baseline("TLV75733PDBVR")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tlv75733.out_cap",
            location=_loc("TLV75733PDBVR"),
            from_pin="OUT",
            part_token="1u_0402_X7R",
        )
    )
    return results


def validate_hx5008() -> list[ValidationResult]:
    ref_circuit = HX5008NLT_REFCIRCUIT
    location = "refcircuits/hx5008nlt.py"
    results = _baseline("HX5008NLT")
    pair_caps = [
        part
        for part in ref_circuit.external_parts
        if part.part_token == "1n_2kV_0603_safety"
        and part.from_pin.startswith("CT_PAIR")
    ]
    if len(pair_caps) != 4:
        results.append(
            error(
                "hx5008.bob_smith_caps",
                f"HX5008 needs 4x 1nF Bob Smith caps; found {len(pair_caps)}",
                location,
            )
        )
    pair_resistors = [
        part
        for part in ref_circuit.external_parts
        if part.part_token == "75R_0603_1%"
    ]
    if len(pair_resistors) != 4:
        results.append(
            error(
                "hx5008.bob_smith_res",
                f"HX5008 needs 4x 75R Bob Smith resistors; found {len(pair_resistors)}",
                location,
            )
        )
    return results


def validate_usbc_sink() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["USBC_SINK"]
    results = _baseline("USBC_SINK")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="usbc.cc_pullup",
            location=_loc("USBC_SINK"),
            from_pin="CC1",
            part_token="5k1_0402_1%",
        )
    )
    return results


def validate_hdmi_a() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["HDMI_A"]
    results = _baseline("HDMI_A")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="hdmi.cec_pullup",
            location=_loc("HDMI_A"),
            from_pin="CEC",
            part_token="10k_0402_1%",
        )
    )
    return results


def validate_microsd() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["DM3AT-SF-PEJM5"]
    results = _baseline("DM3AT-SF-PEJM5")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="microsd.vdd_bypass",
            location=_loc("DM3AT-SF-PEJM5"),
            from_pin="VDD",
            part_token="100n_0402_X7R",
        )
    )
    return results


def validate_rj45() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["RJHSE5380"]
    results = _baseline("RJHSE5380")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="rj45.led1",
            location=_loc("RJHSE5380"),
            from_pin="LED1_A",
            part_token="330R_0402_1%",
        )
    )
    return results


def validate_ss14() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["SS14"]
    results = _baseline("SS14")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="power_input.bulk",
            location=_loc("SS14"),
            from_pin="CATHODE",
            part_token="100u_1206_X5R",
        )
    )
    return results


def validate_fmc_lpc() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["FX10A-168P-SV(91)"]
    results = _baseline("FX10A-168P-SV(91)")
    decoupling = [
        part
        for part in ref_circuit.external_parts
        if part.part_token == "100n_0402_X7R"
    ]
    if sum(part.quantity for part in decoupling) < 4:
        results.append(
            error(
                "fmc.decoupling",
                "FMC LPC needs at least 4x 100n decoupling caps",
                _loc("FX10A-168P-SV(91)"),
            )
        )
    return results


def validate_pmod() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["PM254R-12-08-H85"]
    results = _baseline("PM254R-12-08-H85")
    if not ref_circuit.no_external_required:
        results.append(
            error(
                "pmod.no_external",
                "PMOD connector must declare no_external_required IO pins",
                _loc("PM254R-12-08-H85"),
            )
        )
    return results


def validate_lvds_lcd() -> list[ValidationResult]:
    return _baseline("FPC-05F-40PH20")


def validate_mipi_camera() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["1.0-15P"]
    results = _baseline("1.0-15P")
    results.extend(
        require_supply_rail(
            ref_circuit,
            rule_prefix="mipi",
            location=_loc("1.0-15P"),
        )
    )
    return results


def validate_jtag_header() -> list[ValidationResult]:
    return _baseline("ZX-PM2.54-2-7PY")


def validate_swd_header() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["HX-PZ1.27-2x5P-TP"]
    results = _baseline("HX-PZ1.27-2x5P-TP")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="swd.nreset_pullup",
            location=_loc("HX-PZ1.27-2x5P-TP"),
            from_pin="nRESET",
            part_token="10k_0402_1%",
        )
    )
    return results


def validate_sma_clock() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["KH-SMA-P-8496"]
    results = _baseline("KH-SMA-P-8496")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="sma.ac_couple",
            location=_loc("KH-SMA-P-8496"),
            from_pin="CENTER",
            part_token="22p_0402_C0G",
        )
    )
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="sma.termination",
            location=_loc("KH-SMA-P-8496"),
            from_pin="XADC_CLK",
            part_token="49R9_0402_1%",
        )
    )
    return results


def validate_user_led() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["YLED0603G"]
    results = _baseline("YLED0603G")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="led.series",
            location=_loc("YLED0603G"),
            from_pin="ANODE",
            part_token="330R_0402_1%",
        )
    )
    return results


def validate_tactile_switch() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["TS-1002S-06026C"]
    results = _baseline("TS-1002S-06026C")
    results.extend(
        require_external(
            ref_circuit,
            rule_prefix="tact.pullup",
            location=_loc("TS-1002S-06026C"),
            from_pin="SW",
            part_token="10k_0402_1%",
        )
    )
    return results


def validate_dip_switch() -> list[ValidationResult]:
    ref_circuit = REFCIRCUITS["DS-04P"]
    results = _baseline("DS-04P")
    pullups = [
        part
        for part in ref_circuit.external_parts
        if part.part_token == "10k_0402_1%"
    ]
    if len(pullups) < 4:
        results.append(
            error(
                "dip.pullups",
                "DIP switch needs 4x 10k pull-ups",
                _loc("DS-04P"),
            )
        )
    return results
