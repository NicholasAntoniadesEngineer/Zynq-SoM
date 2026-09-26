from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    JTAG_CRYSTAL_FREQ,
    JTAG_CRYSTAL_LOAD,
    JTAG_LDO_CIN,
    JTAG_LDO_COUT,
    JTAG_MODE_PULLDOWN,
    JTAG_OE_PULLUP,
    JTAG_RESET_PULL,
    JTAG_SUPPLY_BYPASS,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"
LCSC_1U = "C15849"
LCSC_10U = "C15850"
LCSC_16P = "C162205"
LCSC_10K = "C25804"
LCSC_100K = "C25803"

RAILS = ("+VBUS_USB", "+3V3_ISLAND", "GND")
PORTS = ("USB_DP", "USB_DM",
         "JTAG_TCK", "JTAG_TDI", "JTAG_TMS", "JTAG_TDO",
         "UART_RXD", "UART_TXD")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('usb_jtag')

DRAWS_NOTE = ("CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull network")
DRAWS_A = 0.045
RESET_WAIVER = ("CH347 RST#: 10k pull-up + the chip's built-in power-on reset "
                "(DS 5.1); no external RC cap fitted by design")

CRYSTAL_LEGS = ("DBG_XI", "DBG_XO")


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('usb_jtag', meta)
