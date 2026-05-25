"""Map io_assignment carrier_signal names to refcircuit / symbol pin names."""

from __future__ import annotations

import re

from scripts.carrier.blocks._block_common import IoAssignmentRow, load_io_rows
from scripts.carrier.model.block import Wire
from scripts.carrier.model.grid import Point


def unique_carrier_signals(io_rows: tuple[IoAssignmentRow, ...]) -> tuple[str, ...]:
    """Return carrier signals in first-seen row order (physical assignment order)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for row in io_rows:
        if row.carrier_signal in seen:
            continue
        seen.add(row.carrier_signal)
        ordered.append(row.carrier_signal)
    return tuple(ordered)


def identity_signal_map(
    io_rows: tuple[IoAssignmentRow, ...],
) -> dict[str, str]:
    from scripts.carrier.symbols.io_library import pin_name_for_carrier_signal

    return {
        row.carrier_signal: pin_name_for_carrier_signal(row.carrier_signal)
        for row in io_rows
    }


def eth_phy_to_magnetics(carrier_signal: str) -> str | None:
    match = re.fullmatch(r"ETH_PHY_MDI(\d)_([PN])", carrier_signal)
    if match is None:
        return None
    pair_index = int(match.group(1))
    polarity = match.group(2)
    return f"PHY{pair_index}_{polarity}"


def eth_led_to_rj45(carrier_signal: str) -> str | None:
    if carrier_signal == "ETH_LED1":
        return "LED1_A"
    if carrier_signal == "ETH_LED2":
        return "LED2_A"
    return None


def sdio_to_socket(carrier_signal: str) -> str | None:
    mapping = {
        "SDIO_CLK": "CLK",
        "SDIO_CMD": "CMD",
        "SDIO_D0": "DAT0",
        "SDIO_D1": "DAT1",
        "SDIO_D2": "DAT2",
        "SDIO_D3": "DAT3/CD",
    }
    return mapping.get(carrier_signal)


def jtag_to_header(carrier_signal: str) -> str | None:
    mapping = {
        "ZYNQ_TCK": "TCK",
        "ZYNQ_TMS": "TMS",
        "ZYNQ_TDI": "TDI",
        "ZYNQ_TDO": "TDO",
    }
    return mapping.get(carrier_signal)


def swd_to_header(carrier_signal: str) -> str | None:
    mapping = {
        "STM32_SWDIO": "SWDIO",
        "STM32_nRESET": "nRESET",
    }
    return mapping.get(carrier_signal)


def stm32_breakout_to_header(carrier_signal: str) -> str | None:
    mapping = {
        "STM32_SWDIO": "SWDIO",
        "STM32_nRESET": "nRESET",
    }
    if carrier_signal in mapping:
        return mapping[carrier_signal]
    if carrier_signal.startswith("STM32_GPIO"):
        return carrier_signal.replace("STM32_GPIO", "GPIO")
    return None


def usbc_otg_to_connector(carrier_signal: str) -> str | None:
    mapping = {
        "USB_D+": "D+",
        "USB_D-": "D-",
        "USB_VBUS": "VBUS",
        "USB_ID": "SBU1",
    }
    return mapping.get(carrier_signal)


def uart_to_cp2102n(carrier_signal: str) -> str | None:
    mapping = {
        "PS_UART0_TX": "RXD",
        "PS_UART0_RX": "TXD",
    }
    return mapping.get(carrier_signal)


def i2c_to_ina226(carrier_signal: str) -> str | None:
    mapping = {
        "PS_I2C_SDA": "SDA",
        "PS_I2C_SCL": "SCL",
    }
    return mapping.get(carrier_signal)


def load_signal_map(
    *destinations: str,
    mapper,
) -> dict[str, str]:
    io_rows = load_io_rows(*destinations)
    result: dict[str, str] = {}
    for row in io_rows:
        pin_name = mapper(row.carrier_signal)
        if pin_name is not None:
            result[row.carrier_signal] = pin_name
    return result


def boot_mode_to_dip(carrier_signal: str) -> str | None:
    if carrier_signal == "STM32_BOOT0":
        return "SW1"
    return None


def reset_to_switch(carrier_signal: str) -> str | None:
    if carrier_signal == "STM32_NRST":
        return "SW"
    return None


def ldo_output_for_vcco(carrier_signal: str) -> str | None:
    if carrier_signal.startswith("+VCCO_"):
        return "OUT"
    return None


def combined_jtag_swd_map() -> dict[str, str]:
    io_rows = load_io_rows("J_JTAG", "STM32_breakout")
    result: dict[str, str] = {}
    for row in io_rows:
        pin = jtag_to_header(row.carrier_signal)
        if pin is None:
            pin = swd_to_header(row.carrier_signal)
        if pin is None:
            pin = stm32_breakout_to_header(row.carrier_signal)
        if pin is not None:
            result[row.carrier_signal] = pin
    return result


def _complete_diff_lanes(
    carrier_signals: tuple[str, ...],
    *,
    bank_suffix: str,
) -> tuple[int, ...]:
    lane_polarities: dict[int, set[str]] = {}
    for carrier_signal in carrier_signals:
        match = re.search(rf"IO_L(\d+)_([PN])_{re.escape(bank_suffix)}", carrier_signal)
        if match is None:
            continue
        lane_index = int(match.group(1))
        lane_polarities.setdefault(lane_index, set()).add(match.group(2))
    return tuple(
        sorted(
            lane_index
            for lane_index, polarities in lane_polarities.items()
            if {"P", "N"}.issubset(polarities)
        )
    )


def _lane_signal(
    carrier_signals: tuple[str, ...],
    lane_index: int,
    polarity: str,
    bank_suffix: str,
) -> str | None:
    lane_token = f"_L{lane_index}_{polarity}_{bank_suffix}"
    for carrier_signal in carrier_signals:
        if lane_token in carrier_signal:
            return carrier_signal
    return None


def build_lvds_ffc_signal_map() -> dict[str, str]:
    """Map the first LVDS clock/data pairs to FFC connector symbol pins."""
    carrier_signals = unique_carrier_signals(load_io_rows("J_LCD"))
    selected_lanes = _complete_diff_lanes(carrier_signals, bank_suffix="33")[:2]
    ffc_pins = (
        ("LVDS_CLK+", "LVDS_CLK-"),
        ("LVDS_DATA0+", "LVDS_DATA0-"),
    )
    mapping: dict[str, str] = {}
    for lane_index, (positive_pin, negative_pin) in zip(selected_lanes, ffc_pins, strict=False):
        positive_signal = _lane_signal(carrier_signals, lane_index, "P", "33")
        negative_signal = _lane_signal(carrier_signals, lane_index, "N", "33")
        if positive_signal is not None:
            mapping[positive_signal] = positive_pin
        if negative_signal is not None:
            mapping[negative_signal] = negative_pin
    return mapping


def build_pmod_header_signal_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Map PMOD IO carrier signals to Digilent header IO0..IO7 pins."""
    jpm1_signals = unique_carrier_signals(load_io_rows("J_PMOD1"))
    jpm2_signals = unique_carrier_signals(
        load_io_rows("J_PMOD3", "J_PMOD4", "PMOD_AUX")
    )
    jpm1_map = {
        carrier_signal: f"IO{signal_index}"
        for signal_index, carrier_signal in enumerate(jpm1_signals)
        if signal_index < 8
    }
    jpm2_map = {
        carrier_signal: f"IO{signal_index}"
        for signal_index, carrier_signal in enumerate(jpm2_signals)
        if signal_index < 8
    }
    return jpm1_map, jpm2_map


def eth_mag_to_rj45_inter_wires(
    *,
    geometry_cache,
    mag_lib_id: str,
    mag_anchor: Point,
    rj45_lib_id: str,
    rj45_anchor: Point,
) -> tuple[Wire, ...]:
    from scripts.carrier.blocks._hand_block import connect

    wires: list[Wire] = []
    for pair_index in range(4):
        for polarity in ("P", "N"):
            td_pin = f"TD{pair_index}_{polarity}"
            mdi_pin = f"MDI{pair_index}_{polarity}"
            wires.extend(
                connect(
                    geometry_cache.absolute_pin_by_name(mag_lib_id, mag_anchor, td_pin),
                    geometry_cache.absolute_pin_by_name(
                        rj45_lib_id,
                        rj45_anchor,
                        mdi_pin,
                    ),
                )
            )
    return tuple(wires)

