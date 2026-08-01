from __future__ import annotations

from schgen.core.model import Circuit

from subsystems.usb_pd import usb_pd as _usb_pd
from subsystems.usbc_otg import usbc_otg as _usbc_otg
from subsystems.microsd import microsd as _microsd
from subsystems.uart_bridge import uart_bridge as _uart_bridge

V3V3 = "+3V3_MINI"
V5V = "+5V_DEV"
V1V8 = "+1V8_FPGA"
VBUS_RAW = "+VBUS_RAW"
GND = "GND"

_J_CONN = "devkit_conn (mini header J5 GPIO map)"
_UART_HDR = "devkit_uart_header (FPGA UART0 pin map)"
_USB_CONN = "devkit_usb_receptacles (USB2 connector sheet)"


USB_PD_META = {
    "bind": {
        "+VDD_LOGIC": V3V3,
        "+VBUS_SENSE": VBUS_RAW,
        "GND": GND,
        "CC1": "PD_CC1",
        "CC2": "PD_CC2",
        "I2C_SDA": "MINI_I2C0_SDA",
        "I2C_SCL": "MINI_I2C0_SCL",
        "INT_N": "MINI_PD_INT_N",
    },
    "expects": {
        "I2C_SDA": _J_CONN,
        "I2C_SCL": _J_CONN,
        "INT_N": _J_CONN,
    },
    "buses": {"i2c": "MINI_I2C0"},
    "notes": {"draws": "FUSB302B VDD (<1 mA) on the shared +3V3_MINI logic rail; "
                       "MINI_I2C0 + INT pull-ups are board-shared, off-subsystem"},
}


def usb_pd_circuit() -> Circuit:
    return _usb_pd.circuit(USB_PD_META)


USBC_OTG_META = {
    "bind": {
        "+VBUS_SUPPLY": V5V,
        "+VDD_LOGIC": V3V3,
        "GND": GND,
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "USB2_HOST_DP",
        "USB_DM": "USB2_HOST_DM",
        "VBUS": "USB2_HOST_VBUS",
        "VBUS_EN": "USB2_HOST_EN",
        "FLT_N": "USB2_HOST_FLT_N",
        "USB_ID": "USB2_HOST_ID",
    },
    "expects": {
        "VBUS_EN": _J_CONN,
        "USB_ID": _J_CONN,
        "FLT_N": _J_CONN,
    },
    "notes": {
        "draws_vbus": "downstream USB device budget (TPS2051C limited) from +5V_DEV",
        "draws_flt": "USB2_HOST_FLT# 100k pull-up on the shared +3V3_MINI logic rail",
    },
}


def usbc_otg_circuit() -> Circuit:
    return _usbc_otg.circuit(USBC_OTG_META)


MICROSD_META = {
    "bind": {
        "+VDD_HOST": V1V8,
        "+VDD_CARD": V3V3,
        "GND": GND,
        "SD_CLK": "SD0_CLK",
        "SD_CMD": "SD0_CMD",
        "SD_D0": "SD0_DAT0",
        "SD_D1": "SD0_DAT1",
        "SD_D2": "SD0_DAT2",
        "SD_D3": "SD0_DAT3",
        "CD_N": "SD0_DETECT_N",
    },
    "expects": {
        "CD_N": _J_CONN,
    },
    "notes": {
        "draws_card": "SD card write burst ~200 mA + pulls + TXS02612 VCCB "
                      "on +3V3_MINI",
        "draws_host": "TXS02612 VCCA (FPGA 1.8 V SDIO level)",
    },
}


def microsd_circuit() -> Circuit:
    return _microsd.circuit(MICROSD_META)


UART_BRIDGE_META = {
    "bind": {
        "+VDD_IO": V3V3,
        "GND": GND,
        "USB_VBUS": "USB2_UART_VBUS",
        "USB_DP": "USB2_UART_DP",
        "USB_DM": "USB2_UART_DM",
        # null-modem: bridge TXD/RTS_N cross onto the host's RXD/CTS_N nets.
        "UART_TXD": "FPGA_UART0_RXD",
        "UART_RXD": "FPGA_UART0_TXD",
        "UART_RTS_N": "FPGA_UART0_CTS_N",
        "UART_CTS_N": "FPGA_UART0_RTS_N",
    },
    "expects": {
        "USB_VBUS": _USB_CONN,
        "USB_DP": _USB_CONN,
        "UART_TXD": _UART_HDR,
        "UART_RXD": _UART_HDR,
        "UART_RTS_N": _UART_HDR,
        "UART_CTS_N": _UART_HDR,
    },
    "notes": {"draws": "CP2102N active ~14 mA typ + RST 1k pull-up on +3V3_MINI"},
}


def uart_bridge_circuit() -> Circuit:
    return _uart_bridge.circuit(UART_BRIDGE_META)


PROJECT = (
    ("usb_pd", usb_pd_circuit),
    ("usbc_otg", usbc_otg_circuit),
    ("microsd", microsd_circuit),
    ("uart_bridge", uart_bridge_circuit),
)

SHARED_RAILS = (V3V3, GND)


def subsystem_circuits() -> "list[tuple[str, Circuit]]":
    return [(name, build()) for name, build in PROJECT]
