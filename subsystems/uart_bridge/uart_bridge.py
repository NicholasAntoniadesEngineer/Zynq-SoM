from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    UART_BRIDGE_RESET_PULL,
    UART_BRIDGE_SENSE_BOTTOM,
    UART_BRIDGE_SENSE_TOP,
    UART_BRIDGE_SUPPLY_BYPASS,
    UART_BRIDGE_VREGIN_BULK,
)

LCSC_BYPASS = "C14663"
LCSC_BULK = "C15850"
LCSC_RESET_PULL = "C21190"
LCSC_SENSE_TOP = "C25961"
LCSC_SENSE_BOTTOM = "C23061"

RAILS = ("+VDD_IO", "GND")
PORTS = ("USB_VBUS", "USB_DP", "USB_DM",
         "UART_TXD", "UART_RXD", "UART_RTS_N", "UART_CTS_N")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('uart_bridge')

# TP creation order IS the placer's TP1/TP2 order: it must survive a project's
# TXD<->RXD crossover bind, so the sequence is declared, never incidental.
TESTPOINT_ORDER = ("UART_RXD", "UART_TXD")

DRAWS_NOTE = "CP2102N active ~14 mA typ + RST 1k pull-up"
DRAWS_A = 0.015
RESET_WAIVER = "open-drain RST: 1k pull-up only, internal POR; no RC cap"


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('uart_bridge', meta)
