"""lcd — carrier ADAPTER for the reusable 40-pin TTL RGB LCD + backlight subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/lcd/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT net names the hand-written sheet used, so the
emitted carrier/schematic/lcd.kicad_sch + its golden render are unchanged.

Authored per carrier/research/lcd_backlight.md: AFC07-S40FCA-00 40-pin 0.5 mm
bottom-contact FFC (LCSC C262572) carries the panel + capacitive-touch I2C on
pins 37-40; the SY7201ABC boost drives the LED string at 133 mA (I = 0.2V /
R_ISET, 1.5R), PWM-dimmable on EN, fed from the gated +5V_LCD rail; panel logic
on gated +3V3_LCD. LCD-1 (electrical audit): the boost output cap is 2.2uF/50V
X7R (C125847), not 1uF — at the 9-25V open-LED OVP output the X7R DC-bias
derating eats well over half of a 1uF, so 2.2uF keeps real capacitance and
ripple/loop margin healthy while staying 50V-rated.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VBOOST_IN    -> +5V_LCD   the gated 5V module rail (sourced by the round-5
                             bringup_modules SY6280, like +5V_USB) feeding the
                             SY7201 boost input. A powered-down module fully
                             kills the backlight boost.
  +VDD_LCD      -> +3V3_LCD  the gated 3.3V module rail for panel logic + touch;
                             a peer of +3V3_PMOD / +3V3_SD. The DISP / touch
                             pull-ups land here so a powered-down panel is not
                             back-fed through them.
  +VDD_TP_CLAMP -> +3V3      the ALWAYS-ON +3V3 (= the bank-13 VCCO) referencing
                             the USBLC6 touch-I2C ESD clamp, so protection is
                             valid even when the gated +3V3_LCD panel rail is off.
  GND           -> GND       (identity).

  RGB/sync/control ports -> the carrier's LCD_* names, destined for PL bank 34
  via the generated J3 sheet (USER DECISION 2026-06-11: bank 13 was
  oversubscribed by lcd+pmod+user_io; +VCCO_34 = 3.3V for the TTL panel):
    LCD_R0..R7/G0..G7/B0..B7, LCD_DISP/HSYNC/VSYNC/DE, LCD_PCLK, BL_PWM
    -> the identically-named carrier nets (LCD_BL_PWM for BL_PWM).
  Touch I2C + reset/interrupt stay on bank 13 via the generated J2 sheet:
    TP_SDA/TP_SCL -> LCD_CTP_SDA/LCD_CTP_SCL (the LCD_CTP bus),
    TP_RST/TP_INT -> LCD_CTP_RST/LCD_CTP_INT.

These ports bind on the generated J2/J3 connector sheets (som_conn_gen
FUNCTION_MAP), so the adapter declares that linker deferral via the library's
``expects`` hook: the panel video/control on J3 bank 34, the touch group on J2
bank 13.
"""

from __future__ import annotations

from subsystems.lcd import lcd as _lib
from schgen.core.model import Circuit

# The generated J2/J3 sheets (som_conn_gen FUNCTION_MAP) carry the bank-34 TTL
# panel video/control and the bank-13 touch I2C, so these ports bind there by
# name. EXPLICIT linker deferral so a standalone link reports them as awaiting
# their connector sheet, never a silent open. (Same deferral strings the hand-
# written sheet used.)
_J3_MAP = "som_j3_connector (PL bank 34, +VCCO_34=3.3V)"
_J2_MAP = "som_j2_connector (PL bank 13 — touch I2C only)"

# Carrier real-net names for the RGB/sync/control ports (identity except BL_PWM).
_PANEL_PORTS = (
    "LCD_R0", "LCD_R1", "LCD_R2", "LCD_R3", "LCD_R4", "LCD_R5", "LCD_R6", "LCD_R7",
    "LCD_G0", "LCD_G1", "LCD_G2", "LCD_G3", "LCD_G4", "LCD_G5", "LCD_G6", "LCD_G7",
    "LCD_B0", "LCD_B1", "LCD_B2", "LCD_B3", "LCD_B4", "LCD_B5", "LCD_B6", "LCD_B7",
    "LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE", "LCD_PCLK",
)

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects ports that bind on the generated J2/J3 sheets -> explicit linker
#           deferral (panel video/control -> J3 bank 34; touch -> J2 bank 13)
#   buses   the touch I2C is the carrier LCD_CTP bus
#   notes   power-tree draw notes cite the carrier dossier wording (lcd_backlight.md)
# (buses/notes keep the carrier's derived artifacts — layout_constraints.csv bus
#  grouping, power_tree.txt notes — byte-identical to the hand-written sheet.)
META = {
    "bind": {
        "+VBOOST_IN": "+5V_LCD",
        "+VDD_LCD": "+3V3_LCD",
        "+VDD_TP_CLAMP": "+3V3",
        "GND": "GND",
        **{p: p for p in _PANEL_PORTS},
        "BL_PWM": "LCD_BL_PWM",
        "TP_SDA": "LCD_CTP_SDA",
        "TP_SCL": "LCD_CTP_SCL",
        "TP_RST": "LCD_CTP_RST",
        "TP_INT": "LCD_CTP_INT",
    },
    "expects": {
        **{p: _J3_MAP for p in _PANEL_PORTS},
        "BL_PWM": _J3_MAP,
        "TP_SDA": _J2_MAP,
        "TP_SCL": _J2_MAP,
        "TP_RST": _J2_MAP,
        "TP_INT": _J2_MAP,
    },
    "buses": {"i2c": "LCD_CTP"},
    "notes": {
        "draws_lcd": "panel logic 25-75 mA + touch <= 25 mA (lcd_backlight.md)",
        "draws_boost": "SY7201 boost input @133 mA LED string "
                       "(lcd_backlight.md operating point + margin)",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
