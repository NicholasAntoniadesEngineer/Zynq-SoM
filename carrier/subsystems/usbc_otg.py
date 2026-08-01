"""usbc_otg project bind — circuit + component basis: subsystems/usbc_otg/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.usbc_otg import usbc_otg as _lib

_SUB = "usbc_otg"
_J1_MAP = "som_j1_connector (STM32 GPIO function map)"
_FLT_BRINGUP = "bringup (TCA9535 expander port P14)"

_VBUS_SUPPLY = bind(
    _SUB, "+VBUS_SUPPLY", "+5V_USB",
    "Bringup-gated module rail the port SOURCES onto the cable VBUS through the "
    "TPS2051C current-limited switch.",
    "policy")

_VDD_LOGIC = bind(
    _SUB, "+VDD_LOGIC", "+3V3_SC",
    "G4 ABS-MAX FIX: the FLT# pull-up is re-railed +5V_USB -> +3V3_SC because a "
    "TCA9535 IO abs max is VCC+0.5 = 3.8 V (TI SCPS201E) and a 5 V pull on P14 "
    "violates it. +3V3_SC also keeps FLT# readable while +5V_USB is gated OFF.",
    "datasheet")

_VBUS = bind(_SUB, "VBUS", "USB_VBUS",
             "The connector VBUS the SoM senses: TPS2051 OUT + the receptacle "
             "VBUS pads, also the CC Rp reference and the ESD VBUS pin.",
             "policy")

_USB_ID = bind(
    _SUB, "USB_ID", "USB_ID",
    "OTG ID (contract J1.20) strapped low through 1k = HOST role for this port; "
    "the FS+PD Type-C is the device/dual-role port.",
    "datasheet")

META = {
    "bind": {
        "+VBUS_SUPPLY": _VBUS_SUPPLY,
        "+VDD_LOGIC": _VDD_LOGIC,
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "USB_D+",
        "USB_DM": "USB_D-",
        "VBUS": _VBUS,
        "VBUS_EN": "VBUS_OUT_EN",
        "FLT_N": "USBOTG_FLT_N",
        "USB_ID": _USB_ID,
    },
    "expects": {
        "VBUS_EN": _J1_MAP,
        "USB_ID": _J1_MAP,
        "FLT_N": _FLT_BRINGUP,
    },
    "notes": {
        "draws_vbus": "downstream USB device budget, TPS2051C current-limited",
        "draws_flt": "USBOTG_FLT# 100k pull-up (G4 re-rail)",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
