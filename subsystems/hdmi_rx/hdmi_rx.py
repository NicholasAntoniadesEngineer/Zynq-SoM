from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    HDMI_RX_CEC_PULL,
    HDMI_RX_DET_BOTTOM,
    HDMI_RX_DET_TOP,
    HDMI_RX_EDID_BYPASS,
    HDMI_RX_HPD_ASSERT,
)

U_LIB = "Memory_EEPROM:M24C02-WMN"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_HPD_ASSERT = "C21190"
LCSC_CEC_PULL = "C22967"
LCSC_DET_TOP = "C25804"
LCSC_DET_BOTTOM = "C22809"
LCSC_EDID_BYPASS = "C14663"

RAILS = ("+VDD_LOGIC", "GND", "CHASSIS_GND")
TMDS_PORTS = (
    "TMDS_RX_D2_P", "TMDS_RX_D2_N",
    "TMDS_RX_D1_P", "TMDS_RX_D1_N",
    "TMDS_RX_D0_P", "TMDS_RX_D0_N",
    "TMDS_RX_CLK_P", "TMDS_RX_CLK_N",
)
CTRL_PORTS = ("HDMI_5V_DET", "CEC")
PORTS = TMDS_PORTS + CTRL_PORTS
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('hdmi_rx')

TMDS_LANES = (
    ("TMDS_RX_D2_P", 1, "U2", "IO1"), ("TMDS_RX_D2_N", 3, "U2", "IO2"),
    ("TMDS_RX_D1_P", 4, "U2", "IO3"), ("TMDS_RX_D1_N", 6, "U2", "IO4"),
    ("TMDS_RX_D0_P", 7, "U3", "IO1"), ("TMDS_RX_D0_N", 9, "U3", "IO2"),
    ("TMDS_RX_CLK_P", 10, "U3", "IO3"), ("TMDS_RX_CLK_N", 12, "U3", "IO4"),
)
TMDS_PAIRS = (
    ("TMDS_RX_D2_P", "TMDS_RX_D2_N"),
    ("TMDS_RX_D1_P", "TMDS_RX_D1_N"),
    ("TMDS_RX_D0_P", "TMDS_RX_D0_N"),
    ("TMDS_RX_CLK_P", "TMDS_RX_CLK_N"),
)

DRAWS_NOTE = ("CEC 27k pull-up (EEPROM + EDID WC# are cable-5V-fed)")
DRAWS_A = 0.001


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('hdmi_rx', meta)
