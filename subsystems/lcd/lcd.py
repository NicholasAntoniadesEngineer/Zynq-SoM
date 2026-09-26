from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    LCD_BLPWM_PULLDOWN,
    LCD_BOOST_CIN,
    LCD_BOOST_COUT,
    LCD_BOOST_HF,
    LCD_BOOST_INDUCTOR,
    LCD_DISP_PULLUP,
    LCD_ISET_SENSE,
    LCD_PANEL_BULK,
    LCD_PANEL_BYPASS,
    LCD_PCLK_DAMPING,
    LCD_RESET_PULLDOWN,
    LCD_TOUCH_PULL,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_ISET = "C22769"
LCSC_BOOST_CIN = "C15850"
LCSC_BOOST_COUT = "C125847"
LCSC_BOOST_HF = "C15849"
LCSC_BYPASS = "C14663"
LCSC_BULK = "C15850"
LCSC_TOUCH_PULL = "C23162"
LCSC_100K = "C25803"
LCSC_10K = "C25804"
LCSC_PCLK_DAMP = "C23345"
LCSC_SCHOTTKY = "C8678"

RAILS = ("+VBOOST_IN", "+VDD_LCD", "+VDD_TP_CLAMP", "GND")
PORTS = (
    "LCD_R0", "LCD_R1", "LCD_R2", "LCD_R3", "LCD_R4", "LCD_R5", "LCD_R6", "LCD_R7",
    "LCD_G0", "LCD_G1", "LCD_G2", "LCD_G3", "LCD_G4", "LCD_G5", "LCD_G6", "LCD_G7",
    "LCD_B0", "LCD_B1", "LCD_B2", "LCD_B3", "LCD_B4", "LCD_B5", "LCD_B6", "LCD_B7",
    "LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE",
    "TP_SDA", "TP_SCL", "TP_RST", "TP_INT",
    "LCD_PCLK", "BL_PWM",
)
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('lcd')

I2C_BUS = "LCD_CTP"
I2C_SPEED_HZ = 400_000

DRAWS_LCD_NOTE = "panel logic 25-75 mA + touch <= 25 mA"
DRAWS_LCD_A = 0.100
DRAWS_BOOST_NOTE = "SY7201 boost input @133 mA LED string (operating point + margin)"
DRAWS_BOOST_A = 0.450

RGB_BANKS = ((5, "LCD_R"), (13, "LCD_G"), (21, "LCD_B"))
SYNC_PINS = ((31, "LCD_DISP"), (32, "LCD_HSYNC"),
             (33, "LCD_VSYNC"), (34, "LCD_DE"))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('lcd', meta)
