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
INTERFACE = RAILS + PORTS

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
    meta = Meta(meta)
    i2c_bus = meta.bus("i2c", I2C_BUS)
    draws_lcd_note = meta.note("draws_lcd", DRAWS_LCD_NOTE)
    draws_boost_note = meta.note("draws_boost", DRAWS_BOOST_NOTE)
    c = Circuit("lcd", "40-pin TTL RGB LCD + SY7201 backlight boost")
    c.use_part("AFC07-S40FCA-00", ref="J1")
    c.use_part("SY7201ABC", ref="U1")
    c.use_part("SWPA4030S100MT", ref="L1", value=LCD_BOOST_INDUCTOR)
    c.part("D1", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA",
           LCSC=LCSC_SCHOTTKY)
    c.part("R1", "Device:R", LCD_ISET_SENSE, R0603, LCSC=LCSC_ISET)
    c.part("C1", "Device:C", LCD_BOOST_CIN, C0805, LCSC=LCSC_BOOST_CIN)
    c.part("C2", "Device:C", LCD_BOOST_COUT, C0805, LCSC=LCSC_BOOST_COUT)
    c.part("C3", "Device:C", LCD_PANEL_BYPASS, C0603, LCSC=LCSC_BYPASS)

    for base, prefix in RGB_BANKS:
        for off in range(8):
            net = f"{prefix}{off}"
            c.port(net, f"J1.{base + off}", **meta.expect_kw(net))
    for pin, net in SYNC_PINS:
        c.port(net, f"J1.{pin}", **meta.expect_kw(net))

    c.use_part("USBLC6-2SC6", ref="U2")
    c.net("CTP_SDA_FFC", "J1.37", "U2.1")
    c.net("CTP_SCL_FFC", "J1.38", "U2.3")
    c.port("TP_SDA", "U2.6", kind="i2c", role="sda",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("TP_SDA"))
    c.port("TP_SCL", "U2.4", kind="i2c", role="scl",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("TP_SCL"))
    c.net("+VDD_TP_CLAMP", "U2.5")
    c.net("GND", "U2.2")
    c.port("TP_RST", "J1.39", **meta.expect_kw("TP_RST"))
    c.port("TP_INT", "J1.40", **meta.expect_kw("TP_INT"))

    c.part("R2", "Device:R", LCD_TOUCH_PULL, R0603, LCSC=LCSC_TOUCH_PULL)
    c.net("TP_SDA", "R2.1")
    c.net("+VDD_LCD", "R2.2")
    c.part("R3", "Device:R", LCD_TOUCH_PULL, R0603, LCSC=LCSC_TOUCH_PULL)
    c.net("TP_SCL", "R3.1")
    c.net("+VDD_LCD", "R3.2")
    c.part("R5", "Device:R", LCD_RESET_PULLDOWN, R0603, LCSC=LCSC_100K)
    c.net("TP_RST", "R5.1")
    c.net("GND", "R5.2")
    c.part("R6", "Device:R", LCD_DISP_PULLUP, R0603, LCSC=LCSC_10K)
    c.net("LCD_DISP", "R6.1")
    c.net("+VDD_LCD", "R6.2")
    c.part("R7", "Device:R", LCD_PCLK_DAMPING, R0603, LCSC=LCSC_PCLK_DAMP)
    c.net("LCD_PCLK_PANEL", "J1.30", "R7.1")
    c.port("LCD_PCLK", "R7.2", **meta.expect_kw("LCD_PCLK"))

    c.net("+VDD_LCD", "J1.4", "C3.1")
    c.net("GND", "J1.3", "J1.29", "J1.36", "C3.2")
    c.nc("J1.35", "J1.41", "J1.42")
    bulk = c.part(c.auto_ref("C"), "Device:C", LCD_PANEL_BULK, C0805,
                  LCSC=LCSC_BULK)
    c.net("+VDD_LCD", f"{bulk.ref}.1")
    c.net("GND", f"{bulk.ref}.2")

    cin_hf = c.part(c.auto_ref("C"), "Device:C", LCD_BOOST_HF, C0603,
                    LCSC=LCSC_BOOST_HF)
    c.net("+VBOOST_IN", "U1.IN", "L1.1", "C1.1", f"{cin_hf.ref}.1")
    c.net("GND", "U1.GND", "C1.2", "C2.2", "R1.2", f"{cin_hf.ref}.2")
    c.net("LCD_BL_SW", "L1.2", "U1.LX")
    # Device:D_Schottky pin1 = K, pin2 = A: cathode on the boost OUTPUT, anode
    # on LX. Reversed here (audit 2026-06-19) is a dead backlight, DRC-clean.
    c.net("LCD_VLED_P", "D1.1", "C2.1", "U1.OVP", "J1.2")
    c.net("LCD_BL_SW", "D1.2")
    c.net("LCD_VLED_N", "J1.1", "R1.1", "U1.FB")
    c.port("BL_PWM", "U1.EN/PWM", **meta.expect_kw("BL_PWM"))
    c.part("R4", "Device:R", LCD_BLPWM_PULLDOWN, R0603, LCSC=LCSC_100K)
    c.net("BL_PWM", "R4.1")
    c.net("GND", "R4.2")

    c.testpoint("+VBOOST_IN")
    c.testpoint("TP_SDA")
    c.testpoint("TP_SCL")

    c.draws("+VDD_LCD", DRAWS_LCD_A, draws_lcd_note)
    c.draws("+VBOOST_IN", DRAWS_BOOST_A, draws_boost_note)
    c.waive_reset("TP_RST",
                  "GPIO-driven reset, held by 100k pull-down until PL releases")
    c.waive_part_rule("C2", "MLCC 50V on LCD_VLED_P: the 30V is the rare open-LED "
                      "OVP-clamp transient, not continuous (string ~9.6V); 50V/X7R "
                      "dossier-sized for it (lcd_backlight.md). 2x derate targets "
                      "continuous DC bias, not a fault clamp")
    return meta.finish(c)
