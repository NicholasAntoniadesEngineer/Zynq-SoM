"""lcd — 40-pin TTL RGB888 panel (AT043TN24-lineage pinout) + SY7201 backlight.

Per carrier/research/lcd_backlight.md: AFC07-S40FCA-00 FFC carries panel +
capacitive-touch I2C on pins 37-40; SY7201ABC boost drives the LED string at
133 mA (I = 0.2V / R_ISET, 1.5R), PWM-dimmable on EN, fed from the gated
+5V_LCD rail; logic on gated +3V3_LCD. LCD-1 (electrical audit): the boost
output cap is 2.2uF/50V X7R (C125847), not 1uF — at the 9-25V open-LED OVP
output the X7R DC-bias derating eats well over half of a 1uF, so 2.2uF keeps
real capacitance and ripple/loop margin healthy while staying 50V-rated. RGB/sync ports go to PL bank 34 via the
J3 sheet (USER DECISION 2026-06-11: bank 13 was oversubscribed by lcd+pmod+
user_io; +VCCO_34 = 3.3V for the TTL panel). Touch I2C stays on bank 13.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

BRINGUP = "bringup (gated LCD rails)"
J3_MAP = "som_j3_connector (PL bank 34, +VCCO_34=3.3V)"
J2_MAP = "som_j2_connector (PL bank 13 — touch I2C only)"


def circuit() -> Circuit:
    c = Circuit("lcd", "40-pin TTL RGB LCD + SY7201 backlight boost")
    c.use_part("AFC07-S40FCA-00", ref="J1")    # bare-number FFC pins
    c.use_part("SY7201ABC", ref="U1")
    c.use_part("SWPA4030S100MT", ref="L1", value="10uH")
    c.part("D1", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", LCSC="C8678")
    c.part("R1", "Device:R", "1.5R", R0603, LCSC="C22769")   # ISET 133mA
    c.part("C1", "Device:C", "10u", C0805, LCSC="C15850")    # boost in
    c.part("C2", "Device:C", "2.2u", C0805, LCSC="C125847")  # boost out 50V (LCD-1)
    c.part("C3", "Device:C", "100n", C0603, LCSC="C1591")    # panel VDD

    # ---- panel data: 24 RGB + syncs, PL bank 13 via J2 ---------------------
    for base, names in ((5, [f"LCD_R{i}" for i in range(8)]),
                        (13, [f"LCD_G{i}" for i in range(8)]),
                        (21, [f"LCD_B{i}" for i in range(8)])):
        for off, net in enumerate(names):
            c.port(net, f"J1.{base + off}", expect=J3_MAP)
    for pin, net in ((31, "LCD_DISP"), (32, "LCD_HSYNC"),
                     (33, "LCD_VSYNC"), (34, "LCD_DE")):
        c.port(net, f"J1.{pin}", expect=J3_MAP)
    # capacitive touch on the same FFC tail. The FFC is user-touchable, so the
    # touch-I2C pair is clamped at the connector by a USBLC6-2SC6 (the board's
    # standard low-cap ESD array; 1<->6 / 3<->4 passthrough). The external FFC
    # pins land on U2.1/U2.3; the protected pair (-> the pull-ups + the PL) on
    # U2.6/U2.4; clamp ref the ALWAYS-ON +3V3 (= the bank-13 VCCO, so protection
    # is valid even when the gated +3V3_LCD panel rail is off).
    c.use_part("USBLC6-2SC6", ref="U2")
    c.net("CTP_SDA_FFC", "J1.37", "U2.1")
    c.net("CTP_SCL_FFC", "J1.38", "U2.3")
    c.port("LCD_CTP_SDA", "U2.6", kind="i2c", role="sda",
           bus="LCD_CTP", speed_hz=400_000, expect=J2_MAP)
    c.port("LCD_CTP_SCL", "U2.4", kind="i2c", role="scl",
           bus="LCD_CTP", speed_hz=400_000, expect=J2_MAP)
    c.net("+3V3", "U2.5")
    c.net("GND", "U2.2")
    c.port("LCD_CTP_RST", "J1.39", expect=J2_MAP)
    c.port("LCD_CTP_INT", "J1.40", expect=J2_MAP)

    # ---- audit fixes (electrical-recon WAVE-LCD): the dossier-mandated
    # housekeeping passives lcd_backlight.md 3.1/3.2/4 that the netlist omitted.
    # Touch I2C is open-drain -> REQUIRES pull-ups (bus is dead without them).
    c.part("R2", "Device:R", "4k7", R0603, LCSC="C23162")
    c.net("LCD_CTP_SDA", "R2.1")
    c.net("+3V3_LCD", "R2.2")
    c.part("R3", "Device:R", "4k7", R0603, LCSC="C23162")
    c.net("LCD_CTP_SCL", "R3.1")
    c.net("+3V3_LCD", "R3.2")
    # touch controller held in reset until the PL releases it
    c.part("R5", "Device:R", "100k", R0603, LCSC="C25803")
    c.net("LCD_CTP_RST", "R5.1")
    c.net("GND", "R5.2")
    # panel display-enable defaults ON when the gated rail is up
    c.part("R6", "Device:R", "10k", R0603, LCSC="C25804")
    c.net("LCD_DISP", "R6.1")
    c.net("+3V3_LCD", "R6.2")
    # pixel-clock source-series damping (~33 MHz, the highest-edge-rate line):
    # SoM-side port -> 22R -> FFC pin 30 (resistor at the source/SoM end)
    c.part("R7", "Device:R", "22R", R0603, LCSC="C23345")
    c.net("LCD_PCLK_PANEL", "J1.30", "R7.1")
    c.port("LCD_PCLK", "R7.2", expect=J3_MAP)

    # ---- panel power (gated module rails = POWER nets with their own
    # symbols, sourced by the bringup sheet's SY6280s — like +5V_USB) -------
    c.net("+3V3_LCD", "J1.4", "C3.1")
    c.net("GND", "J1.3", "J1.29", "J1.36", "C3.2")
    c.nc("J1.35", "J1.41", "J1.42")        # NC + shell tabs unused
    # bulk on the gated +3V3_LCD logic rail (lcd_backlight.md 3.1: "10uF + 100n"
    # on panel VDD; only the 100n was present — peers camera/microsd carry 10u)
    bulk = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC="C15850")
    c.net("+3V3_LCD", f"{bulk.ref}.1")
    c.net("GND", f"{bulk.ref}.2")

    # ---- backlight boost: +5V_LCD -> L1 -> LX, D1 -> VLED+, ISET return ----
    c.net("+5V_LCD", "U1.IN", "L1.1", "C1.1")
    c.net("GND", "U1.GND", "C1.2", "C2.2", "R1.2")
    c.net("LCD_BL_SW", "L1.2", "U1.LX")                      # LX node
    c.net("LCD_VLED_P", "D1.2", "C2.1", "U1.OVP", "J1.2")    # boost out + OVP
    c.net("LCD_BL_SW", "D1.1")
    c.net("LCD_VLED_N", "J1.1", "R1.1", "U1.FB")             # current sense
    c.port("LCD_BL_PWM", "U1.EN/PWM", expect=J3_MAP)
    # backlight EN/PWM defaults OFF (boost off until the PL drives it high)
    c.part("R4", "Device:R", "100k", R0603, LCSC="C25803")
    c.net("LCD_BL_PWM", "R4.1")
    c.net("GND", "R4.2")

    # round-4 coverage gate: the gated boost feed rail (sourced by the
    # round-5 bringup_modules SY6280) + the touch I2C bus this sheet owns
    c.testpoint("+5V_LCD")
    c.testpoint("LCD_CTP_SDA")
    c.testpoint("LCD_CTP_SCL")

    # power-tree budget (round 4, lcd_backlight.md section "budget to
    # declare to bringup"): panel logic + touch <= 100 mA; boost input at
    # 133 mA LED current ~= 0.30 A plus margin -> 0.45 A
    c.draws("+3V3_LCD", 0.100, "panel logic 25-75 mA + touch <= 25 mA "
                               "(lcd_backlight.md)")
    c.draws("+5V_LCD", 0.450, "SY7201 boost input @133 mA LED string "
                              "(lcd_backlight.md operating point + margin)")
    # design-rule waiver (verification P1): LCD_CTP_RST is GPIO-driven by the PL
    # and held in reset by R5 (100k pull-down) until released — a driven reset,
    # not an RC reset, so no cap-to-GND by design.
    c.waive_reset("LCD_CTP_RST",
                  "GPIO-driven reset, held by 100k pull-down until PL releases")
    # part-rule waiver (CAP_VOLTAGE): C2 (2.2uF/50V X7R) on LCD_VLED_P now that
    # the boost output node resolves to its 30 V open-LED OVP clamp. The 2x MLCC
    # derate wants 60 V, but 30 V is a RARE open-LED fault TRANSIENT, not a
    # continuous bias — the continuous string voltage is ~9.6 V (50 V/2 = 25 V
    # derated >> 9.6 V). The 50 V/X7R part is dossier-sized for the transient.
    c.waive_part_rule("C2", "MLCC 50V on LCD_VLED_P: the 30V is the rare open-LED "
                      "OVP-clamp transient, not continuous (string ~9.6V); 50V/X7R "
                      "dossier-sized for it (lcd_backlight.md). 2x derate targets "
                      "continuous DC bias, not a fault clamp")
    return c
