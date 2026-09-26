from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    OTG_CC_RP,
    OTG_ENABLE_PULLDOWN,
    OTG_FAULT_PULLUP,
    OTG_ID_STRAP,
    OTG_INPUT_BYPASS,
    OTG_VBUS_BULK,
    OTG_VBUS_MLCC,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100K = "C25803"
LCSC_BYPASS = "C14663"
LCSC_VBUS_MLCC = "C45783"
LCSC_CC_RP = "C23206"
LCSC_ID_STRAP = "C21190"

RAILS = ("+VBUS_SUPPLY", "+VDD_LOGIC", "GND", "CHASSIS_GND")
PORTS = ("USB_DP", "USB_DM", "VBUS", "VBUS_EN", "FLT_N", "USB_ID")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('usbc_otg')

DRAWS_VBUS_A = 0.500
DRAWS_VBUS_NOTE = ("downstream USB device budget, TPS2051C current-limited")
DRAWS_FLT_A = 0.0005
DRAWS_FLT_NOTE = ("FLT# 100k pull-up on the logic rail")

RAIL_WORST_V = {"+VBUS_SUPPLY": 5.0, "+VDD_LOGIC": 3.3, "GND": 0.0,
                "CHASSIS_GND": 0.0, "VBUS": 5.0}

CC_PINS = (("R1", "J2.CC1"), ("R2", "J2.CC2"))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('usbc_otg', meta)
