from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import ETHERNET_BOB_SMITH_C, ETHERNET_BOB_SMITH_R

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_1206_3225Metric"
LCSC_BOB_SMITH_R = "C4275"
LCSC_BOB_SMITH_C = "C9196"

RAILS = ("CHASSIS_GND",)
MDI_PORTS = (
    "MDI0_P", "MDI0_N",
    "MDI1_P", "MDI1_N",
    "MDI2_P", "MDI2_N",
    "MDI3_P", "MDI3_N",
)
MX_PORTS = (
    "MX0_P", "MX0_N",
    "MX1_P", "MX1_N",
    "MX2_P", "MX2_N",
    "MX3_P", "MX3_N",
)
PORTS = MDI_PORTS + MX_PORTS
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('ethernet')

PAIR_IMPEDANCE = 100

#            ch  td_p td_n  mx_p mx_n  mct  tct
CHANNELS = [(0,   2,   3,   23,  22,  24,  1),
            (1,   5,   6,   20,  19,  21,  4),
            (2,   8,   9,   17,  16,  18,  7),
            (3,  11,  12,   14,  13,  15, 10)]


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('ethernet', meta)
