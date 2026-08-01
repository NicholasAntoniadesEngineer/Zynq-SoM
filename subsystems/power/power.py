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
INTERFACE = RAILS + PORTS

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
    meta = Meta(meta)
    c = Circuit("power", "Power: +VIN->+5V->+3V3 bucks + +1V8 LDO, PG LEDs")

    c.use_part("LM61460AANRJRR", ref="U1")
    c.net("+VIN", "U1.8", "U1.12")
    c.net("GND", "U1.9", "U1.11", "U1.3")
    c.port("EN_VOUT_5V", "U1.7", **meta.expect_kw("EN_VOUT_5V"))
    for ref, val, fp, lcsc in BUCK5V_CIN:
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C24", "Device:C", POWER_VCC_BYPASS, C0603, LCSC=LCSC_1U)
    c.net("U1_VCC", "U1.2", "C24.1")
    c.net("GND", "C24.2")
    c.part("R11", "Device:R", POWER_BIAS_SERIES, R_FP, LCSC=LCSC_BIAS_SERIES)
    c.net("+VOUT_5V_REG", "R11.1")
    c.part("C28", "Device:C", POWER_BIAS_BYPASS, C0603, LCSC=LCSC_1U)
    c.net("BIAS_5V0", "U1.1", "R11.2", "C28.1")
    c.net("GND", "C28.2")
    c.part("R10", "Device:R", POWER_RT_FREQ, R_FP, LCSC=LCSC_RT)
    c.net("RT_5V0", "U1.6", "R10.1")
    c.net("GND", "R10.2")
    c.part("C4", "Device:C", POWER_BOOT_CAP, C0603, LCSC=LCSC_VIN_HF)
    # SNVSBD5D 9.2.2.7 shorts RBOOT(13) to CBOOT(14): no boot resistor exists.
    c.net("BOOT_5V0", "U1.14", "U1.13", "C4.1")
    c.part("L1", "Device:L", POWER_SW_INDUCTOR, L_FP, LCSC=LCSC_INDUCTOR)
    c.net("SW_5V0", "U1.10", "C4.2", "L1.1")
    c.net("+VOUT_5V_REG", "L1.2")
    for ref in BUCK5V_COUT:
        c.part(ref, "Device:C", POWER_COUT_BULK, C0805, LCSC=LCSC_COUT)
        c.net("+VOUT_5V_REG", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("R1", "Device:R", POWER_FB5V_TOP, R_FP, LCSC=LCSC_FB5V_TOP)
    c.part("R2", "Device:R", POWER_FB_BOTTOM, R_FP, LCSC=LCSC_FB_BOTTOM)
    c.net("+VOUT_5V_REG", "R1.1")
    c.net("FB_5V0", "U1.4", "R1.2", "R2.1")
    c.net("GND", "R2.2")
    c.part("C27", "Device:C", POWER_CFF_CAP, C0603, LCSC=LCSC_CFF)
    c.part("R12", "Device:R", POWER_RFF_SERIES, R_FP, LCSC=LCSC_1K)
    c.net("+VOUT_5V_REG", "C27.1")
    c.net("CFF_5V0", "C27.2", "R12.1")
    c.net("FB_5V0", "R12.2")
    c.part("D1", "Device:LED", "red", LED_FP, LCSC=LCSC_LED)
    c.part("R3", "Device:R", POWER_LED5V_SERIES, R_FP, LCSC=LCSC_1K)
    c.net("+VOUT_5V_REG", "D1.2")
    c.net("PG_5V0", "D1.1", "R3.1")
    c.net("GND", "R3.2")
    c.nc("U1.5")

    c.use_part("LM61460AANRJRR", ref="U2")
    c.net("+VOUT_5V", "U2.8", "U2.12")
    c.net("GND", "U2.9", "U2.11", "U2.3")
    c.port("EN_VOUT_3V3", "U2.7", **meta.expect_kw("EN_VOUT_3V3"))
    for ref, val, fp, lcsc in BUCK3V3_CIN:
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VOUT_5V", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C31", "Device:C", POWER_VCC_BYPASS, C0603, LCSC=LCSC_1U)
    c.net("U2_VCC", "U2.2", "C31.1")
    c.net("GND", "C31.2")
    c.part("R13", "Device:R", POWER_BIAS_SERIES, R_FP, LCSC=LCSC_BIAS_SERIES)
    c.net("+VOUT_3V3_REG", "R13.1")
    c.part("C32", "Device:C", POWER_BIAS_BYPASS, C0603, LCSC=LCSC_1U)
    c.net("BIAS_3V3", "U2.1", "R13.2", "C32.1")
    c.net("GND", "C32.2")
    c.part("R14", "Device:R", POWER_RT_FREQ, R_FP, LCSC=LCSC_RT)
    c.net("RT_3V3", "U2.6", "R14.1")
    c.net("GND", "R14.2")
    c.part("C9", "Device:C", POWER_BOOT_CAP, C0603, LCSC=LCSC_VIN_HF)
    c.net("BOOT_3V3", "U2.14", "U2.13", "C9.1")
    c.part("L2", "Device:L", POWER_SW_INDUCTOR, L_FP, LCSC=LCSC_INDUCTOR)
    c.net("SW_3V3", "U2.10", "C9.2", "L2.1")
    c.net("+VOUT_3V3_REG", "L2.2")
    for ref in BUCK3V3_COUT:
        c.part(ref, "Device:C", POWER_COUT_BULK, C0805, LCSC=LCSC_COUT)
        c.net("+VOUT_3V3_REG", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("R4", "Device:R", POWER_FB3V3_TOP, R_FP, LCSC=LCSC_FB3V3_TOP)
    c.part("R5", "Device:R", POWER_FB_BOTTOM, R_FP, LCSC=LCSC_FB_BOTTOM)
    c.net("+VOUT_3V3_REG", "R4.1")
    c.net("FB_3V3", "U2.4", "R4.2", "R5.1")
    c.net("GND", "R5.2")
    c.part("C23", "Device:C", POWER_CFF_CAP, C0603, LCSC=LCSC_CFF)
    c.part("R15", "Device:R", POWER_RFF_SERIES, R_FP, LCSC=LCSC_1K)
    c.net("+VOUT_3V3_REG", "C23.1")
    c.net("CFF_3V3", "C23.2", "R15.1")
    c.net("FB_3V3", "R15.2")
    c.part("D2", "Device:LED", "red", LED_FP, LCSC=LCSC_LED)
    c.part("R6", "Device:R", POWER_LED_SERIES, R_FP, LCSC=LCSC_330R)
    c.net("+VOUT_3V3_REG", "D2.2")
    c.net("PG_3V3", "D2.1", "R6.1")
    c.net("GND", "R6.2")
    c.nc("U2.5")

    c.use_part("AP2112K-1.8TRG1", ref="U3", value="AP2112K-1.8",
               lib_id=LDO_LIB, footprint=LDO_FP)
    c.net("+VOUT_3V3", "U3.1")
    c.net("GND", "U3.2")
    c.port("EN_VOUT_1V8", "U3.3", **meta.expect_kw("EN_VOUT_1V8"))
    c.nc("U3.4")
    c.net("+VOUT_1V8_REG", "U3.5")
    c.part("C12", "Device:C", POWER_LDO_CAP, C0603, LCSC=LCSC_1U)
    c.net("+VOUT_3V3", "C12.1")
    c.net("GND", "C12.2")
    c.part("C13", "Device:C", POWER_LDO_CAP, C0603, LCSC=LCSC_1U)
    c.net("+VOUT_1V8_REG", "C13.1")
    c.net("GND", "C13.2")

    # +1V8 < red Vf ~2.0 V, so the indicator is FET-sensed off +VOUT_3V3.
    c.part("R7", "Device:R", POWER_GATE_STOP, R_FP, LCSC=LCSC_1K)
    c.part("R8", "Device:R", POWER_GATE_PULLDOWN, R_FP, LCSC=LCSC_100K)
    c.use_part("AO3400A", ref="Q1", lib_id=FET_LIB, footprint=FET_FP)
    c.net("+VOUT_1V8", "R7.1")
    c.net("PG_1V8_G", "R7.2", "R8.1", "Q1.1")
    c.net("GND", "R8.2", "Q1.2")
    c.part("R9", "Device:R", POWER_LED_SERIES, R_FP, LCSC=LCSC_330R)
    c.part("D3", "Device:LED", "red", LED_FP, LCSC=LCSC_LED)
    c.net("PG_1V8_D", "Q1.3", "R9.2")
    c.net("PG_1V8_K", "R9.1", "D3.1")
    c.net("+VOUT_3V3", "D3.2")

    for net in ("+VOUT_5V", "+VOUT_3V3", "+VOUT_1V8", "GND"):
        c.testpoint(net)

    c.draws("+VOUT_5V", DRAWS_5V_A, meta.note("draws_5v", DRAWS_5V_NOTE))
    c.draws("+VOUT_3V3", DRAWS_3V3_A, meta.note("draws_3v3", DRAWS_3V3_NOTE))
    c.draws("+VOUT_1V8", DRAWS_1V8_A, meta.note("draws_1v8", DRAWS_1V8_NOTE))

    return meta.finish(c)
