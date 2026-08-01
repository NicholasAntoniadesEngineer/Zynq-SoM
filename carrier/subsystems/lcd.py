"""lcd project bind — circuit + component basis: subsystems/lcd/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.lcd import lcd as _lib

_SUB = "lcd"
_J3_MAP = "som_j3_connector (PL bank 34, +VCCO_34=3.3V)"
_J2_MAP = "som_j2_connector (PL bank 13 — touch I2C only)"

_PANEL_PORTS = (
    "LCD_R0", "LCD_R1", "LCD_R2", "LCD_R3", "LCD_R4", "LCD_R5", "LCD_R6", "LCD_R7",
    "LCD_G0", "LCD_G1", "LCD_G2", "LCD_G3", "LCD_G4", "LCD_G5", "LCD_G6", "LCD_G7",
    "LCD_B0", "LCD_B1", "LCD_B2", "LCD_B3", "LCD_B4", "LCD_B5", "LCD_B6", "LCD_B7",
    "LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE", "LCD_PCLK",
)

_VBOOST_IN = bind(
    _SUB, "+VBOOST_IN", "+5V_LCD",
    "Gated 5 V module rail (round-5 bringup_modules SY6280, like +5V_USB) into "
    "the SY7201 boost input, so a powered-down module fully kills the backlight.",
    "policy")

_VDD_LCD = bind(
    _SUB, "+VDD_LCD", "+3V3_LCD",
    "Gated 3.3 V module rail for panel logic + touch, peer of +3V3_PMOD / "
    "+3V3_SD. The DISP and touch pull-ups land here so a powered-down panel is "
    "not back-fed through them.",
    "policy")

_TP_CLAMP = bind(
    _SUB, "+VDD_TP_CLAMP", "+3V3",
    "The USBLC6 touch-I2C ESD clamp references the ALWAYS-ON +3V3 (the bank-13 "
    "VCCO), not the gated panel rail — protection must stay valid while "
    "+3V3_LCD is off.",
    "datasheet")

_PANEL = {
    p: bind(_SUB, p, p,
            "TTL panel video/control on PL bank 34: user decision 2026-06-11 "
            "moved these off bank 13, which lcd+pmod+user_io had "
            "oversubscribed; +VCCO_34 = 3.3 V suits the TTL panel.",
            "policy")
    for p in _PANEL_PORTS
}

_BL_PWM = bind(_SUB, "BL_PWM", "LCD_BL_PWM",
               "The only non-identity panel rename — the carrier prefixes the "
               "backlight PWM to keep it distinct from the panel data bus.",
               "policy")

_TOUCH = {
    port: bind(_SUB, port, net,
               "Touch group stays on bank 13 via J2 while the panel moved to "
               "bank 34, so the LCD_CTP bus spans two connector sheets.",
               "policy")
    for port, net in (("TP_SDA", "LCD_CTP_SDA"), ("TP_SCL", "LCD_CTP_SCL"),
                      ("TP_RST", "LCD_CTP_RST"), ("TP_INT", "LCD_CTP_INT"))
}

META = {
    "bind": {
        "+VBOOST_IN": _VBOOST_IN,
        "+VDD_LCD": _VDD_LCD,
        "+VDD_TP_CLAMP": _TP_CLAMP,
        "GND": "GND",
        **_PANEL,
        "BL_PWM": _BL_PWM,
        **_TOUCH,
    },
    "expects": {
        **{p: _J3_MAP for p in _PANEL_PORTS},
        "BL_PWM": _J3_MAP,
        **{p: _J2_MAP for p in _TOUCH},
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
