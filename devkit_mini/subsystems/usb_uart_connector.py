"""usb_uart_connector bind — circuit + basis: subsystems/usb_uart_connector/."""

from __future__ import annotations

from devkit_mini.basis import bind
from schgen.core.model import Circuit
from subsystems.usb_uart_connector import usb_uart_connector as _lib

_SUB = "usb_uart_connector"

_VBUS = bind(
    _SUB, "VBUS", "USB_UART_VBUS",
    "The receptacle's OWN 5 V VBUS, NOT a board input rail — the bridge senses "
    "it through its 22k1/47k5 divider for datasheet self-powered cable-attach. "
    "This sheet PRODUCES the net that uart_bridge defers to.",
    "datasheet")

_USB = {
    port: bind(_SUB, port, net,
               "USB 2.0 HS pair (90R diff) behind the ESD array; the bridge's "
               "USB data pins join these same nets, which is what resolves its "
               "wave-2 deferral on both sheets.",
               "policy")
    for port, net in (("USB_DP", "USB_UART_DP"), ("USB_DM", "USB_UART_DM"))
}

META = {
    "bind": {
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "VBUS": _VBUS,
        **_USB,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
