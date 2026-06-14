"""board_services — board-management peripherals on the gated +3V3_AUX rail.

The four board-level services the carrier was missing, all powered from the
manually-gated +3V3_AUX rail (the gate + I2C isolator that feed them live on
board_aux), so they obey the same bring-up discipline as every other module
(constraint C1: "a manual power enable like the previous"):

  * U1  24AA025E48  — 2 Kb I2C EEPROM with a factory-locked **EUI-48 MAC**
                      (gives the LAN8720/RJ45 a globally-unique address
                      instead of a soft/random one), strapped to **0x51**.
  * U2  RV-3028-C7  — ultra-low-power I2C RTC with an INTEGRATED 32.768 kHz
                      DTCXO (no external crystal), VBACKUP coin cell (CR1220,
                      BT1) with automatic switchover, address **0x52**.
  * U3  TPS3823-33  — supervisor + windowed watchdog (see the C2 note below).
  * J10 SH1.0-4P    — a **QWIIC / STEMMA-QT** expansion port (gated 3V3 + the
                      isolated AUX I2C), so daughter sensors hang off the
                      board without touching the always-on management bus.

The bus they share, AUX_I2C, is the isolated side of the board_aux PCA9306, so
when +3V3_AUX is OFF these chips are powered down AND cut off from the always-on
STM32_I2C2 management bus (no back-powering through their ESD diodes — LAW 0).

WATCHDOG SAFETY (C2: "I don't want it resetting the system during power-up").
THREE independent guards, any one of which alone prevents a power-up reset:
  1. U3.VDD is +3V3_AUX, which defaults OFF (board_aux SW1) — the supervisor is
     physically UNPOWERED through power-up and cannot drive anything.
  2. The TPS3823 disables its watchdog timer when WDI is left floating; WDI is
     driven only by the PL (WATCHDOG_KICK), which is Hi-Z until the fabric is
     configured — so even once the AUX rail is enabled, the watchdog stays
     disarmed until firmware deliberately starts toggling it.
  3. RESET# does NOT gate any rail or POR line. It rides a PL bank-35 IO
     (WATCHDOG_RST_N -> J3.31) as a firmware-mediated EVENT: software decides
     what a watchdog bite means. A bite can never hard-reset the board.

I2C ADDRESS MAP (7-bit) on STM32_I2C2: 0x20 TCA9535 / 0x22 FUSB302B /
0x40-0x41 INA3221 / 0x50 FMC-EEPROM / **0x51 ID-EEPROM (A0=1,A1=0)** /
**0x52 RV-3028 RTC**. No collisions.

ZYNQ-AGNOSTIC (C3).  The only SoM-side signals are the two watchdog lines,
homed to spare PL bank-35 IO by their verbatim som_interface.json net names
(xdc.py emits the constraints live) — nothing here hard-codes the Zynq part.

QWIIC PAD ORDER — VERIFY AT LAYOUT: pads 1..4 are wired to the QWIIC standard
GND / +3V3 / SDA / SCL (looking into the receptacle); confirm pad 1's location
against the J10 footprint silk before fab, since a swapped power pad would
damage external modules. Pads 5/6 are the shell/mounting tabs -> GND.
"""

from __future__ import annotations

from schgen.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_100N = "C1591"        # 100n X7R 0603
LCSC_10K = "C25804"        # 10k 1% 0603
LCSC_1K = "C21190"         # 1k 0603 (WDI series)

# PL bank-35 IO carrying the two watchdog signals (verbatim contract nets):
#   WATCHDOG_KICK  -> IO_L16_N_35 (J3.29)   PL -> U3.WDI
#   WATCHDOG_RST_N -> IO_L16_P_35 (J3.31)   U3.RESET# -> PL (event, C2)
J3_MAP = "som_j3_connector (PL bank-35 — watchdog kick/event, xdc.py live)"
AUX_BUS = "board_aux (PCA9306 isolated side of STM32_I2C2)"


def circuit() -> Circuit:
    c = Circuit("board_services",
                "Board services: ID-EEPROM(MAC) + RTC + watchdog + QWIIC "
                "on gated +3V3_AUX")

    # ===== 1. ID-EEPROM 24AA025E48 (EUI-48 MAC) @ 0x51 ======================
    c.use_part("24AA025E48T-I_OT", ref="U1")
    c.net("+3V3_AUX", "U1.VCC")
    c.net("GND", "U1.VSS")
    c.port("AUX_I2C_SCL", "U1.SCL", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.port("AUX_I2C_SDA", "U1.SDA", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.net("+3V3_AUX", "U1.A0")                            # A0=1
    c.net("GND", "U1.A1")                                 # A1=0  -> 0x51
    for cap in c.decouple("U1.VCC", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N

    # ===== 2. RTC RV-3028-C7 @ 0x52, coin-cell backed ======================
    c.use_part("RV-3028-C7-32.768kHz-1ppm-TA-QC", ref="U2")
    c.net("+3V3_AUX", "U2.VDD")
    c.net("GND", "U2.VSS")
    c.port("AUX_I2C_SCL", "U2.SCL", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.port("AUX_I2C_SDA", "U2.SDA", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.net("GND", "U2.EVI")                                # event input unused
    c.nc("U2.CLKOUT")                                     # prog clock-out unused
    c.net("RTC_INT_N", "U2.INT#")                         # alarm (local probe)
    c.pullup("U2.INT#", "10k", "+3V3_AUX", footprint=R_FP).fields["LCSC"] = \
        LCSC_10K
    for cap in c.decouple("U2.VDD", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    # VBACKUP: CR1220 with the RV-3028's automatic switchover. Do NOT enable
    # the trickle charger in firmware — BT1 is a PRIMARY cell.
    c.use_part("KH-CR1220-2", ref="BT1")
    c.net("V_RTC_BAT", "U2.VBACKUP", "BT1.1")
    c.net("GND", "BT1.2")
    c.waive_decap("U2", "VBACKUP is the RV-3028 coin-cell backup input (a "
                  "primary CR1220, not a switching rail); the RTC regulates "
                  "internally and a cap on the battery net is optional — no "
                  "bypass fitted by design")

    # ===== 3. supervisor + watchdog TPS3823-33 (C2: see header) =============
    c.use_part("TPS3823-33DBVR", ref="U3")
    c.net("+3V3_AUX", "U3.VDD")
    c.net("GND", "U3.GND")
    for cap in c.decouple("U3.VDD", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    # MR# (manual reset): left to the TPS3823's internal pull-up (de-asserted)
    c.nc("U3.MR#")
    # WDI <- WATCHDOG_KICK (PL bank-35) via 1k: limits ESD back-feed when the
    # rail is off but PL still drives; WDI floats -> watchdog disabled (C2 g2).
    rk = c.part(c.auto_ref("R"), "Device:R", "1k", R_FP, LCSC=LCSC_1K)
    c.net("WDI_AUX", "U3.WDI", f"{rk.ref}.2")
    c.port("IO_L16_N_35", f"{rk.ref}.1", expect=J3_MAP)  # WATCHDOG_KICK
    # RESET# (push-pull, active-low) -> PL bank-35 event line, firmware-mediated
    # (C2 g3). Push-pull -> no pull-up; PL internal pull holds it when AUX off.
    c.port("IO_L16_P_35", "U3.RESET#", expect=J3_MAP)    # WATCHDOG_RST_N

    # ===== 4. QWIIC / STEMMA-QT expansion (gated 3V3 + isolated AUX I2C) ====
    # pads 1..4 = QWIIC GND / +3V3 / SDA / SCL (VERIFY pad-1 vs silk at layout)
    c.use_part("ZX-SH1.0-4PWT", ref="J10")
    c.net("GND", "J10.1")
    c.net("+3V3_AUX", "J10.2")
    c.port("AUX_I2C_SDA", "J10.3", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.port("AUX_I2C_SCL", "J10.4", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=400_000, expect=AUX_BUS)
    c.net("GND", "J10.5", "J10.6")                        # shell/mounting tabs

    # ---- power-tree budget (round 4): everything rides the gated rail ------
    c.draws("+3V3_AUX", 0.205,
            "ID-EEPROM ~1mA + RV-3028 <0.1mA + TPS3823 15uA + INT# 10k pull "
            "+ QWIIC external 200mA budget")
    return c
