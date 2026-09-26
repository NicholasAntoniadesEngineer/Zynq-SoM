from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import UART_CONN_CC_RD, UART_CONN_VBUS_BULK

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"
LCSC_10U = "C15850"

RAILS = ("GND", "CHASSIS_GND")
PORTS = ("VBUS", "USB_DP", "USB_DM")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('usb_uart_connector')

RAIL_WORST_V = {"GND": 0.0, "CHASSIS_GND": 0.0, "VBUS": 5.25}

CC_PINS = (("R1", "J1.CC1"), ("R2", "J1.CC2"))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('usb_uart_connector', meta)
