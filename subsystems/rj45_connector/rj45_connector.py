from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import RJ45_LED_SERIES

R_FP = "Resistor_SMD:R_0603_1608Metric"

LCSC_LED_SERIES = "C23138"

RAILS = ("+VLED", "GND", "CHASSIS_GND")
MDI_PORTS = (
    "RJ45_MDI0_P", "RJ45_MDI0_N",
    "RJ45_MDI1_P", "RJ45_MDI1_N",
    "RJ45_MDI2_P", "RJ45_MDI2_N",
    "RJ45_MDI3_P", "RJ45_MDI3_N",
)
PORTS = MDI_PORTS
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('rj45_connector')

PAIR_IMPEDANCE = 100

MDI_CONTACTS = {
    1: "RJ45_MDI0_P", 2: "RJ45_MDI0_N",
    3: "RJ45_MDI1_P", 6: "RJ45_MDI1_N",
    4: "RJ45_MDI2_P", 5: "RJ45_MDI2_N",
    7: "RJ45_MDI3_P", 8: "RJ45_MDI3_N",
}

DRAWS_NOTE = "RJ45 housing LEDs (2x 330R port-present indicator)"
DRAWS_A = 0.008


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('rj45_connector', meta)
