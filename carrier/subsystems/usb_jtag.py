"""usb_jtag project bind — circuit + component basis: subsystems/usb_jtag/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.usb_jtag import usb_jtag as _lib

_SUB = "usb_jtag"
_USB_MAP = "usb_jtag_connector (USB-C UFP receptacle + USBLC6 ESD)"
_J2_MAP = "som_j2_connector (PL bank 13 EMIO UART, LVCMOS33 — FUNCTION_MAP)"
_HDR_MAP = "debug_boot (the 2x7 JTAG header carries the same ZYNQ_T* nets)"

_VBUS_USB = bind(
    _SUB, "+VBUS_USB", "+5V_DBG",
    "The debug receptacle's own VBUS (U4 AP2112K input), published by "
    "usb_jtag_connector. Alive only with the debug cable plugged, which is what "
    "makes the bridge self-powered with the carrier rails off (constraint C1).",
    "policy")

_ISLAND = bind(
    _SUB, "+3V3_ISLAND", "+3V3_DBG",
    "AP2112K output powering the CH347, the LVC125 buffer and every pull. Not a "
    "carrier system rail — it exists only while the debug cable is present, so "
    "the island cannot back-feed an unpowered carrier.",
    "policy")

_JTAG = {
    port: bind(_SUB, port, net,
               "Carried on the debug_boot 2x7 header. The SN74LVC125 buffer with "
               "its SW1-gated default-HIGH OE# keeps the bridge off the header "
               "when an external pod drives it (LAW 0 contention proof).",
               "policy")
    for port, net in (("JTAG_TCK", "ZYNQ_TCK"), ("JTAG_TDI", "ZYNQ_TDI"),
                      ("JTAG_TMS", "ZYNQ_TMS"), ("JTAG_TDO", "ZYNQ_TDO"))
}

_UART_RXD = bind(
    _SUB, "UART_RXD", "DBG_UART_RXD",
    "CROSSOVER: library ports are bridge-relative, so CH347 TXD1 (pin 3) lands "
    "on the Zynq RXD net. Bank 13 is +VCCO_13 = +3V3 = LVCMOS33, matching the "
    "CH347 3.3 V IO.",
    "datasheet")
_UART_TXD = bind(
    _SUB, "UART_TXD", "DBG_UART_TXD",
    "CROSSOVER twin of UART_RXD: the Zynq TXD net drives CH347 RXD1 (pin 4).",
    "datasheet")

META = {
    "bind": {
        "+VBUS_USB": _VBUS_USB,
        "+3V3_ISLAND": _ISLAND,
        "GND": "GND",
        "USB_DP": "DBG_USB_DP",
        "USB_DM": "DBG_USB_DM",
        **_JTAG,
        "UART_RXD": _UART_RXD,
        "UART_TXD": _UART_TXD,
    },
    "expects": {
        "USB_DP": _USB_MAP,
        "JTAG_TCK": _HDR_MAP,
        "JTAG_TDI": _HDR_MAP,
        "JTAG_TMS": _HDR_MAP,
        "JTAG_TDO": _HDR_MAP,
        "UART_RXD": _J2_MAP,
        "UART_TXD": _J2_MAP,
    },
    "notes": {"draws": "CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull "
                       "network"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
