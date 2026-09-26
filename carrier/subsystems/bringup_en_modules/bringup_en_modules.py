from __future__ import annotations

from carrier.basis import PROJECT, register
from schgen.core.model import Circuit

GATE_LIB = "74xGxx:74LVC1G08"
GATE_FP = "Package_TO_SOT_SMD:SOT-23-5"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_GATE = "C7666"
LCSC_100K = "C25803"
LCSC_100N = "C14663"

J3_MAP = "som_j3_connector (wave 3 STM32 GPIO function map)"
EXPECT_RAILS = "bringup_rails (DIP / TCA9535 control surfaces)"
EXPECT_MODULES = "bringup_modules (SY6280 load-switch cells)"
EXPECT_POWER = "power (regulator EN pins, dossier section 3.1)"
EXPECT_LCD = "RESERVED gated-EN hook (EN_LCD_BL -> testpoint; backlight is PWM-direct)"

GATE_PART = register(
    "bringup_en_modules.gate", "SN74LVC1G08", "part",
    "The same uniform DIP-AND-override cell the rail enables use. TI "
    "SN74LVC1G08DBVR, LCSC C7666, live-verified 2026-06-10.",
    "datasheet")

DIP_PULLDOWN = register(
    "bringup_en_modules.dip_pulldown", "100k", "ohm",
    "A-input pulldown, so an OPEN DIP reads 0 and a closed DIP reads 1. "
    "LCSC C25803.",
    "datasheet")

OVERRIDE_PULLUP = register(
    "bringup_en_modules.override_pullup", "100k", "ohm",
    "B-input pull to +3V3_SC so a Hi-Z TCA9535 port means ENABLED. The LCD_BL "
    "cell is the ONE exception: P10 carries a 100k pullDOWN on bringup_rails "
    "instead, so that provision defaults OFF until software raises it.",
    "datasheet")

GATE_DECAP = register("bringup_en_modules.gate_decap", "100n", "F",
                      "One bypass per gate on +3V3_SC. LCSC C14663.",
                      "datasheet")

SC_DRAW_A = register("bringup_en_modules.sc_draw", 0.005, "A",
                     "Eleven LVC gates (uA static) plus the A/B 100k pull "
                     "networks at 33 uA each when driven.",
                     "datasheet")

CELLS = (
    ("HDMI_TX", "BU_DIP_HDMI_TX", "BU_OVR_HDMI_TX", "EN_HDMI_TX",
     True, EXPECT_MODULES),
    ("HDMI_RX", "BU_DIP_HDMI_RX", "BU_OVR_HDMI_RX", "EN_HDMI_RX",
     True, EXPECT_MODULES),
    ("LCD", "BU_DIP_LCD", "BU_OVR_LCD", "EN_LCD", True, EXPECT_MODULES),
    ("CAM", "BU_DIP_CAM", "BU_OVR_CAM", "EN_CAM", True, EXPECT_MODULES),
    ("SD", "BU_DIP_SD", "BU_OVR_SD", "EN_SD", True, EXPECT_MODULES),
    ("USB", "BU_DIP_USB", "BU_OVR_USB", "EN_USB", True, EXPECT_MODULES),
    ("PMOD", "BU_DIP_PMOD", "BU_OVR_PMOD", "EN_PMOD", True, EXPECT_MODULES),
    ("USER_LED", "BU_DIP_USER_LED", "BU_OVR_USER_LED", "EN_USER_LED",
     True, EXPECT_MODULES),
    ("LCD_BL", "BU_DIP_SPARE", "BU_OVR_LCD_BL", "EN_LCD_BL", False,
     EXPECT_LCD),
    ("HDMI_TX_5V", "BU_DIP_HDMI_TX_5V", "BU_OVR_HDMI_TX_5V",
     "EN_HDMI_TX_5V", True, EXPECT_MODULES),
    ("LCD_5V", "BU_DIP_LCD_5V", "BU_OVR_LCD_5V", "EN_LCD_5V", True,
     EXPECT_MODULES),
)


def circuit() -> Circuit:
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'bringup_en_modules', __file__)
