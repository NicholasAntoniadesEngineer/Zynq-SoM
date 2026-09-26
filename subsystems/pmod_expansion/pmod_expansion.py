from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    PMOD_EXP_ENABLE_PULLDOWN,
    PMOD_EXP_ILIM_SET,
    PMOD_EXP_INPUT_BULK,
    PMOD_EXP_INPUT_BYPASS,
    PMOD_EXP_LED_SERIES,
    PMOD_EXP_OUTPUT_BYPASS,
    PMOD_EXP_SOCKET_BULK,
    PMOD_EXP_SOCKET_BYPASS,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_100N = "C14663"
LCSC_10U = "C15850"
LCSC_13K = "C22797"
LCSC_100K = "C25803"
LCSC_330R = "C23138"
LCSC_RED = "C2286"

RAILS = ("+VDD_PMOD", "+VSW_PMOD", "GND")
PORTS = ("PMOD_IO1", "PMOD_IO2", "PMOD_IO3", "PMOD_IO4",
         "PMOD_IO5", "PMOD_IO6", "PMOD_IO7", "PMOD_IO8")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('pmod_expansion')

DRAWS_PMOD_A = 0.104
DRAWS_PMOD_NOTE = ("1x Pmod module budget ~100 mA (Digilent spec) + status LED")

RAIL_WORST_V = {"+VDD_PMOD": 3.3, "+VSW_PMOD": 3.3, "GND": 0.0}

PAD = {p: 2 * p - 1 for p in range(1, 7)}
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})

IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

IO_PORTS = list(PORTS)

ESD_CH = ["1", "3", "6", "4"]


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('pmod_expansion', meta)
