"""board_services — board-management peripherals on the gated +3V3_AUX rail.

The four board-level services the carrier was missing, all powered from the
manually-gated +3V3_AUX rail (the gate + I2C isolator that feed them live on
board_aux), so they obey the same bring-up discipline as every other module
(constraint C1: "a manual power enable like the previous"):

  * U1  24AA025E48  — 2 Kb I2C EEPROM with a factory-locked **EUI-48 MAC**
                      (gives the LAN8720/RJ45 a globally-unique address
                      instead of a soft/random one), strapped to **0x51**.
  * U2  RV-3028-C7  — ultra-low-power I2C RTC with an INTEGRATED 32.768 kHz
                      DTCXO (no external crystal), VBACKUP coin cell (RECHARGE-
                      ABLE ML1220, BT1) with automatic switchover, address
                      **0x52**.
  * U3  TPS3823-33  — supervisor + windowed watchdog (see the C2 note below).
  (the QWIIC / STEMMA-QT expansion connector that exposes this same gated 3V3 +
  isolated AUX I2C lives on its own sheet, board_qwiic, with ESD protection —
  the carrier's connectors-get-their-own-sheet idiom.)

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

I2C ADDRESS MAP (7-bit). The EEPROM/RTC live on AUX_I2C — the PCA9306-isolated
segment of STM32_I2C2 — so they SHARE that bus's address space (the isolator is
transparent when the rail is on). Full map: 0x20 TCA9535 / 0x22 FUSB302B /
0x40-0x41 INA3221 / 0x50 FMC-EEPROM (all on the always-on trunk) / **0x51
ID-EEPROM (A0=1,A1=0)** / **0x52 RV-3028 RTC** (both on the gated AUX segment).
No collisions.

ZYNQ-AGNOSTIC (C3).  The only SoM-side signals are the two watchdog lines,
homed to spare PL bank-35 IO by their verbatim som_interface.json net names
(xdc.py emits the constraints live) — nothing here hard-codes the Zynq part.

RTC BACKUP CELL: BT1 is a RECHARGEABLE ML1220 (Mn-Li) for a maintenance-free
RTC — the SC firmware ENABLES the RV-3028 trickle charger (TCE + ~3k series in
the EEPROM Backup register) so the cell tops up whenever the board is powered.
Do NOT fit a primary CR1220 (it would be charged) or a LIR Li-ion (its 4.2 V
charge target exceeds the 3.3 V supply). The KH-CR1220-2 holder fits both 12.5 mm
chemistries. (The QWIIC connector that exposes this bus lives on board_qwiic,
with its own ESD + pad-order note.)
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
    # VBACKUP: RECHARGEABLE ML1220 with the RV-3028's automatic switchover +
    # internal trickle charger (enabled in firmware). KH-CR1220-2 holder fits.
    c.use_part("KH-CR1220-2", ref="BT1")
    c.net("V_RTC_BAT", "U2.VBACKUP", "BT1.1")
    c.net("GND", "BT1.2")
    # Key on the V_RTC_BAT rail (the coin-cell net), NOT the bare ref "U2": a
    # ref-level waiver also silently waives U2.VDD (+3V3_AUX, the real switching
    # supply, which IS bypassed at line 105) and mis-attributes the report. The
    # net key waives ONLY the VBACKUP pin on V_RTC_BAT, leaving VDD under the rule.
    c.waive_decap("V_RTC_BAT", "VBACKUP is the RV-3028 coin-cell backup input "
                  "(a rechargeable ML1220, not a switching rail); the RTC "
                  "regulates internally and a cap on the cell net is optional "
                  "— no bypass fitted by design")

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

    # (the QWIIC connector + its ESD array live on board_qwiic; AUX_I2C reaches
    #  it as a port, +3V3_AUX as the gated power net)

    # ---- power-tree budget (round 4): everything rides the gated rail ------
    c.draws("+3V3_AUX", 0.005,
            "ID-EEPROM ~1mA + RV-3028 <0.1mA + TPS3823 15uA + INT# 10k pull")
    return c
