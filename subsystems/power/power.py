from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    POWER_5V_BULK,
    POWER_BIAS_BYPASS,
    POWER_BIAS_SERIES,
    POWER_BOOT_CAP,
    POWER_CFF_CAP,
    POWER_COUT_BULK,
    POWER_FB3V3_TOP,
    POWER_FB5V_TOP,
    POWER_FB_BOTTOM,
    POWER_GATE_PULLDOWN,
    POWER_GATE_STOP,
    POWER_LDO_CAP,
    POWER_LED5V_SERIES,
    POWER_LED_SERIES,
    POWER_RFF_SERIES,
    POWER_RT_FREQ,
    POWER_SW_INDUCTOR,
    POWER_VCC_BYPASS,
    POWER_VIN_BULK,
    POWER_VIN_HF,
)

LDO_LIB = "Regulator_Linear:AP2204K-1.5"
LDO_FP = "Package_TO_SOT_SMD:SOT-23-5"
FET_LIB = "Transistor_FET:Q_NMOS_GSD"
FET_FP = "Package_TO_SOT_SMD:SOT-23"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"
DZ_FP = "Diode_SMD:D_SOD-123"
L_FP = "SWPA8040S100MT:SWPA8040S100MT"

LCSC_VIN_HF = "C14663"
LCSC_VIN_BULK = "C13585"
LCSC_5V_BULK = "C45783"
LCSC_1U = "C15849"
LCSC_BIAS_SERIES = "C22859"
LCSC_RT = "C31850"
LCSC_INDUCTOR = "C37429"
LCSC_COUT = "C45783"
LCSC_FB5V_TOP = "C12447"
LCSC_FB3V3_TOP = "C23346"
LCSC_FB_BOTTOM = "C25804"
LCSC_CFF = "C1653"
LCSC_1K = "C21190"
LCSC_330R = "C23138"
LCSC_100K = "C25803"
LCSC_LED = "C2286"

RAILS = ("+VIN",
         "+VOUT_5V_REG", "+VOUT_5V",
         "+VOUT_3V3_REG", "+VOUT_3V3",
         "+VOUT_1V8_REG", "+VOUT_1V8",
         "GND")
PORTS = ("EN_VOUT_5V", "EN_VOUT_3V3", "EN_VOUT_1V8")
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('power')

EXPECT_EN = "rail-enable cells (off-subsystem)"

DRAWS_5V_A = 0.004
DRAWS_5V_NOTE = "PG LED + FB divider"
DRAWS_3V3_A = 0.009
DRAWS_3V3_NOTE = "PG LED + downstream PG-sense LED chain + FB divider"
DRAWS_1V8_A = 0.001
DRAWS_1V8_NOTE = "PG FET gate divider"

RAIL_WORST_V = {"+VIN": 21.0,
                "+VOUT_5V_REG": 5.0, "+VOUT_5V": 5.0,
                "+VOUT_3V3_REG": 3.3, "+VOUT_3V3": 3.3,
                "+VOUT_1V8_REG": 1.8, "+VOUT_1V8": 1.8,
                "GND": 0.0}

BUCK5V_CIN = (("C1", POWER_VIN_HF, C0603, LCSC_VIN_HF),
              ("C25", POWER_VIN_HF, C0603, LCSC_VIN_HF),
              ("C2", POWER_VIN_BULK, C1206, LCSC_VIN_BULK),
              ("C3", POWER_VIN_BULK, C1206, LCSC_VIN_BULK))
BUCK3V3_CIN = (("C7", POWER_VIN_HF, C0603, LCSC_VIN_HF),
               ("C29", POWER_VIN_HF, C0603, LCSC_VIN_HF),
               ("C8", POWER_5V_BULK, C0805, LCSC_5V_BULK),
               ("C30", POWER_5V_BULK, C0805, LCSC_5V_BULK))
BUCK5V_COUT = ("C5", "C6", "C26")
BUCK3V3_COUT = ("C10", "C11")


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('power', meta)
