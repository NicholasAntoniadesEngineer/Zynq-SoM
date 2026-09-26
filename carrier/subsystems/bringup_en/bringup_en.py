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
EXPECT_LCD = "lvds_lcd_power (backlight boost EN provision, dossier 3.2)"

GATE_PART = register(
    "bringup_en.gate", "SN74LVC1G08", "part",
    "One uniform AND cell per enable implements the dossier contract 'DIP is "
    "the master, STM32 is a veto'. TI SN74LVC1G08DBVR, LCSC C7666, "
    "live-verified 2026-06-10.",
    "datasheet")

DIP_PULLDOWN = register(
    "bringup_en.dip_pulldown", "100k", "ohm",
    "A-input pulldown, so an OPEN DIP reads 0 and a closed DIP reads 1. "
    "LCSC C25803.",
    "datasheet")

OVERRIDE_PULLUP = register(
    "bringup_en.override_pullup", "100k", "ohm",
    "B-input pull to +3V3_SC, so a Hi-Z override source means ENABLED. That is "
    "what lets a blank system controller boot 'switches only'. LCSC C25803.",
    "datasheet")

GATE_DECAP = register("bringup_en.gate_decap", "100n", "F",
                      "One bypass per gate on +3V3_SC. LCSC C14663.",
                      "datasheet")

SC_DRAW_A = register("bringup_en.sc_draw", 0.002, "A",
                     "Three LVC gates (uA static) plus the A/B 100k pull "
                     "networks at 33 uA each when driven.",
                     "datasheet")

# (cell, A net <- DIP, B net <- override, Y net -> enable, B pullup?, Y expect)
CELLS = (
    ("5V0", "BU_DIP_5V0", "STM32_RAIL_EN_5V0", "EN_5V0", True, EXPECT_POWER),
    ("3V3", "BU_DIP_3V3", "STM32_RAIL_EN_3V3", "EN_3V3", True, EXPECT_POWER),
    ("1V8", "BU_DIP_1V8", "STM32_RAIL_EN_1V8", "EN_1V8", True, EXPECT_POWER),
)


def circuit() -> Circuit:
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'bringup_en', __file__)
