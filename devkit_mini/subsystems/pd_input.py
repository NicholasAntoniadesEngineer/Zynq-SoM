"""pd_input project bind — circuit + component basis: subsystems/pd_input/."""

from __future__ import annotations

from devkit_mini.basis import bind
from schgen.core.model import Circuit
from subsystems.pd_input import pd_input as _lib

_SUB = "pd_input"
_EXPANDER = "bringup (TCA9535 expander port P15)"

_VBUS_CONN = bind(
    _SUB, "+VBUS_CONN", "+VBUS_IN",
    "Raw receptacle VBUS ahead of the eFuse: TVS + inlet 100n + eFuse "
    "IN/IN_SYS/UVLO + OVP-top. usb_pd binds +VBUS_SENSE to this same net, so "
    "the PHY sees vSafe5V at the connector; FUSB302B U1.2 sits at its 21.0 V "
    "recommended max on the legal 20 V+5% contract (AMX-1).",
    "datasheet")

_VBUS_OUT = bind(
    _SUB, "+VBUS_OUT", "+VIN",
    "Fused eFuse output — the dVdT-charged board bulk that power.py consumes.",
    "policy")

_VDD_LOGIC = bind(
    _SUB, "+VDD_LOGIC", "+3V3_SC",
    "FLT# pull-up AND USBLC6 pin-5 clamp rail. +3V3_SC is an always-on SoM "
    "rail. NOT +VBUS_IN: TCA9535 IO abs max is VCC+0.5 = 3.8 V, and the "
    "USBLC6 internal TVS standoff is ~5.25 V — tying its clamp rail to the "
    "20 V inlet holds that TVS in continuous avalanche and defeats the data "
    "ESD (audit CRITICAL).",
    "datasheet")

_CC1 = bind(_SUB, "CC1", "STM32_USB_CC1",
            "Receptacle CC1 to the FUSB302B (usb_pd, same net) and the SoM "
            "STM32 CC sense.", "policy")
_CC2 = bind(_SUB, "CC2", "STM32_USB_CC2",
            "Receptacle CC2 to the FUSB302B (usb_pd, same net) and the SoM "
            "STM32 CC sense.", "policy")

_D_P = bind(_SUB, "USB_D_P", "STM32_USB_D_P",
            "FS data pair to the SoM FS PHY, post the USBLC6 ESD array; "
            "cable-flip paired as usb_hs_pair.", "policy")
_D_N = bind(_SUB, "USB_D_N", "STM32_USB_D_N",
            "FS data pair to the SoM FS PHY, post the USBLC6 ESD array; "
            "cable-flip paired as usb_hs_pair.", "policy")

_FLT_N = bind(
    _SUB, "FLT_N", "PD_FLT_N",
    "eFuse open-drain fault to the SoM SC via TCA9535 P15 (bringup_rails, "
    "DEF-F). The TPS26631 is the board's only +VIN protection device, so the "
    "flag is declared through expects rather than left a silent open.",
    "policy")

META = {
    "bind": {
        "+VBUS_CONN": _VBUS_CONN,
        "+VBUS_OUT": _VBUS_OUT,
        "+VDD_LOGIC": _VDD_LOGIC,
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "CC1": _CC1,
        "CC2": _CC2,
        "USB_D_P": _D_P,
        "USB_D_N": _D_N,
        "FLT_N": _FLT_N,
    },
    "expects": {
        "FLT_N": _EXPANDER,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
