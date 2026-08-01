"""usb_jtag_connector bind — circuit + basis: subsystems/usb_jtag_connector/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.usb_jtag_connector import usb_jtag_connector as _lib

_SUB = "usb_jtag_connector"
_BRIDGE = "usb_jtag (CH347T bridge)"

_VBUS = bind(
    _SUB, "+VBUS", "+5V_DBG",
    "Receptacle VBUS published as a POWER rail so it merges by name onto "
    "usb_jtag's AP2112K input. The bridge is alive only with the cable plugged "
    "(constraint C1), which is what makes the island self-powered.",
    "policy")

_USB = {
    port: bind(_SUB, port, net,
               "USB 2.0 HS pair (90R diff) AFTER the USBLC6-2SC6 array. The "
               "CH347 datasheet FORBIDS a series R on UD+/UD-; the USBLC6 is a "
               "SHUNT array, so it adds no series element.",
               "datasheet")
    for port, net in (("USB_DP", "DBG_USB_DP"), ("USB_DM", "DBG_USB_DM"))
}

META = {
    "bind": {
        "+VBUS": _VBUS,
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        **_USB,
    },
    "expects": {
        "USB_DP": _BRIDGE,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
