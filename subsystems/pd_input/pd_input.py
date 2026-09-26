from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    PD_INPUT_DVDT_CAP,
    PD_INPUT_FAULT_PULL,
    PD_INPUT_FUSED_BULK,
    PD_INPUT_ILIM_SET,
    PD_INPUT_INLET_BYPASS,
    PD_INPUT_OVP_BOTTOM,
    PD_INPUT_OVP_TOP,
)

C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
TVS_FP = "Diode_SMD:D_SMB"

LCSC_INLET_BYPASS = "C14663"
LCSC_TVS = "C10214"
LCSC_100K = "C25803"
LCSC_OVP_BOTTOM = "C188263"
LCSC_ILIM = "C23186"
LCSC_DVDT = "C1622"
LCSC_FUSED_BULK = "C596319"

RAILS = ("+VBUS_CONN", "+VBUS_OUT", "+VDD_LOGIC", "GND", "CHASSIS_GND")
PORTS = ("CC1", "CC2", "USB_D_P", "USB_D_N", "FLT_N")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('pd_input')

DRAWS_NOTE = ("USB-C PD inlet: sources +VBUS_OUT through the eFuse; the FLT# "
              "pull-up + USBLC6 clamp draw is <0.5 mA off +VDD_LOGIC")

RAIL_WORST_V = {
    "+VBUS_CONN": 21.0, "+VBUS_OUT": 21.0, "+VDD_LOGIC": 3.3,
    "GND": 0.0, "CHASSIS_GND": 0.0,
}


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('pd_input', meta)
