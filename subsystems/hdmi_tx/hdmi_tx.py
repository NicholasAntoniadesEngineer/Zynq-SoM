from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    HDMI_TX_CABLE_BULK,
    HDMI_TX_CABLE_BYPASS,
    HDMI_TX_RAIL_BULK,
    HDMI_TX_RAIL_BYPASS,
    HDMI_TX_STRAP_PULL,
)

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"
LCSC_1U = "C15849"
LCSC_10U = "C15850"
LCSC_10K = "C25804"

RAILS = ("+VDD_IO", "+5V", "GND", "CHASSIS_GND")
TMDS_PORTS = (
    "TMDS_D2_P", "TMDS_D2_N",
    "TMDS_D1_P", "TMDS_D1_N",
    "TMDS_D0_P", "TMDS_D0_N",
    "TMDS_CLK_P", "TMDS_CLK_N",
)
CTRL_PORTS = ("CEC", "DDC_SCL", "DDC_SDA", "HPD")
PORTS = TMDS_PORTS + CTRL_PORTS
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('hdmi_tx')

DDC_BUS = "HDMI_TX_DDC"
DDC_SPEED_HZ = 100_000

DRAWS_VCCA_NOTE = "TPD12S016 ICCA + LS_OE/CT_HPD straps"
DRAWS_VCCA_A = 0.002
DRAWS_5V_NOTE = ("HDMI source +5V to cable — TPD12S016 switch limit 55 mA "
                 "(DS 7.3.10)")
DRAWS_5V_A = 0.055

TMDS_LANES = (
    ("TMDS_D2_P", "23", "1"), ("TMDS_D2_N", "22", "3"),
    ("TMDS_D1_P", "21", "4"), ("TMDS_D1_N", "20", "6"),
    ("TMDS_D0_P", "18", "7"), ("TMDS_D0_N", "17", "9"),
    ("TMDS_CLK_P", "16", "10"), ("TMDS_CLK_N", "15", "12"),
)
TMDS_PAIRS = (
    ("TMDS_D2_P", "TMDS_D2_N"),
    ("TMDS_D1_P", "TMDS_D1_N"),
    ("TMDS_D0_P", "TMDS_D0_N"),
    ("TMDS_CLK_P", "TMDS_CLK_N"),
)
SHIFTED = (
    ("CEC", "HDMI_TX_CON_CEC", "1", "7", "13"),
    ("DDC_SCL", "HDMI_TX_CON_SCL", "2", "8", "15"),
    ("DDC_SDA", "HDMI_TX_CON_SDA", "3", "9", "16"),
    ("HPD", "HDMI_TX_CON_HPD", "4", "10", "19"),
)


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('hdmi_tx', meta)
