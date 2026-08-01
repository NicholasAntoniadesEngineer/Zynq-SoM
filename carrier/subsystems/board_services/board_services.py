from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_100N = "C14663"
LCSC_10K = "C25804"
LCSC_1K = "C21190"

J3_MAP = "som_j3_connector (PL bank-33 +3V3/LVCMOS33 — watchdog kick/event, xdc.py live)"
AUX_BUS = "board_aux (PCA9306 isolated side of STM32_I2C2)"

EEPROM_PART = register(
    "board_services.eeprom", "24AA025E48T-I_OT", "part",
    "2 Kb I2C EEPROM with a factory-locked EUI-48 MAC, giving the LAN8720/RJ45 "
    "a globally-unique address instead of a soft/random one.",
    "datasheet")

RTC_PART = register(
    "board_services.rtc", "RV-3028-C7-32.768kHz-1ppm-TA-QC", "part",
    "Ultra-low-power I2C RTC with an INTEGRATED 32.768 kHz DTCXO, so no "
    "external crystal, plus VBACKUP automatic switchover.",
    "datasheet")

SUPERVISOR_PART = register(
    "board_services.supervisor", "TPS3823-33DBVR", "part",
    "Supervisor + windowed watchdog. The -33 suffix is load-bearing: VIT- = "
    "2.93 V, so VDD MUST stay on a 3.3 V rail — re-railing to 2.5 V would "
    "assert RESET forever. C2 power-up safety rests on three INDEPENDENT "
    "guards, any one of which alone prevents a power-up reset: VDD is the "
    "default-OFF +3V3_AUX; a floating WDI disables the timer (and the PL is "
    "Hi-Z until configured); RESET# gates no rail or POR line, it is a "
    "firmware-mediated PL event.",
    "datasheet")

BACKUP_CELL_HOLDER = register(
    "board_services.backup_cell_holder", "KH-CR1220-2", "part",
    "12.5 mm coin holder for the RECHARGEABLE ML1220 the SC firmware trickle-"
    "charges (RV-3028 TCE + ~3k series in the EEPROM Backup register). See "
    "carrier/README.md for the chemistries that must NOT be fitted.",
    "policy")

EEPROM_ADDR = register(
    "board_services.eeprom_addr", "0x51", "i2c-addr",
    "A0=1, A1=0. Board map: 0x20 TCA9535 / 0x22 FUSB302B / 0x40-0x41 INA3221 on "
    "the always-on trunk, 0x51 here and 0x52 RTC on the gated AUX segment. The "
    "PCA9306 is transparent when the rail is on, so both segments share one "
    "address space; no collisions. 0x50 freed when the FMC connector went.",
    "datasheet")

RTC_ADDR = register("board_services.rtc_addr", "0x52", "i2c-addr",
                    "Fixed RV-3028 address; see board_services.eeprom_addr for "
                    "the shared-segment map.",
                    "datasheet")

I2C_SPEED_HZ = register("board_services.i2c_speed", 400_000, "Hz",
                        "Fast-mode AUX_I2C, the PCA9306-isolated segment of "
                        "STM32_I2C2.",
                        "datasheet")

DECAP = register("board_services.decap", "100n", "F",
                 "Per-IC supply bypass. LCSC C14663.", "datasheet")

INT_PULLUP = register("board_services.int_pullup", "10k", "ohm",
                      "RV-3028 open-drain alarm pull to the gated rail. "
                      "LCSC C25804.", "datasheet")

WDI_SERIES_R = register(
    "board_services.wdi_series_r", "1k", "ohm",
    "Limits ESD back-feed into U3.WDI while +3V3_AUX is off but the PL still "
    "drives. It does NOT divide the kick: the LVCMOS33 driver VOH ~3.0 V clears "
    "the TPS3823 VIH = 0.7*VDD = 2.31 V, which the previous LVCMOS25 driver "
    "(VOH ~2.1 V) could not reliably meet. LCSC C21190.",
    "datasheet")

AUX_DRAW_A = register(
    "board_services.aux_draw", 0.005, "A",
    "ID-EEPROM ~1 mA + RV-3028 <0.1 mA + TPS3823 15 uA + the INT# 10k pull, all "
    "on the gated rail.",
    "datasheet")


def circuit() -> Circuit:
    c = Circuit("board_services",
                "Board services: ID-EEPROM, RTC, watchdog, QWIIC")

    c.use_part(EEPROM_PART, ref="U1")
    c.net("+3V3_AUX", "U1.VCC")
    c.net("GND", "U1.VSS")
    c.port("AUX_I2C_SCL", "U1.SCL", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.port("AUX_I2C_SDA", "U1.SDA", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.net("+3V3_AUX", "U1.A0")
    c.net("GND", "U1.A1")
    for cap in c.decouple("U1.VCC", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N

    c.use_part(RTC_PART, ref="U2")
    c.net("+3V3_AUX", "U2.VDD")
    c.net("GND", "U2.VSS")
    c.port("AUX_I2C_SCL", "U2.SCL", kind="i2c", role="scl", bus="AUX_I2C",
           speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.port("AUX_I2C_SDA", "U2.SDA", kind="i2c", role="sda", bus="AUX_I2C",
           speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.net("GND", "U2.EVI")
    c.nc("U2.CLKOUT")
    c.net("RTC_INT_N", "U2.INT#")
    c.pullup("U2.INT#", INT_PULLUP, "+3V3_AUX",
             footprint=R_FP).fields["LCSC"] = LCSC_10K
    for cap in c.decouple("U2.VDD", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.use_part(BACKUP_CELL_HOLDER, ref="BT1")
    c.net("V_RTC_BAT", "U2.VBACKUP", "BT1.1")
    c.net("GND", "BT1.2")
    # Key the waiver on V_RTC_BAT, NOT the bare ref "U2": a ref-level waiver
    # would also silently waive U2.VDD, the real switching supply.
    c.waive_decap("V_RTC_BAT", "VBACKUP is the RV-3028 coin-cell backup input "
                  "(a rechargeable ML1220, not a switching rail); the RTC "
                  "regulates internally and a cap on the cell net is optional "
                  "— no bypass fitted by design")

    c.use_part(SUPERVISOR_PART, ref="U3")
    c.net("+3V3_AUX", "U3.VDD")
    c.net("GND", "U3.GND")
    for cap in c.decouple("U3.VDD", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.nc("U3.MR#")
    rk = c.part(c.auto_ref("R"), "Device:R", WDI_SERIES_R, R_FP, LCSC=LCSC_1K)
    c.net("WDI_AUX", "U3.WDI", f"{rk.ref}.2")
    c.port("WATCHDOG_KICK", f"{rk.ref}.1", expect=J3_MAP)
    c.port("WATCHDOG_RST_N", "U3.RESET#", expect=J3_MAP)
    c.waive_reset("WATCHDOG_RST_N",
                  "TPS3823 RESET# is a push-pull supervisor OUTPUT driving a PL "
                  "bank-33 input as a firmware-mediated event (not a POR line): "
                  "no pull needed (push-pull; PL internal pull holds it when "
                  "+3V3_AUX is OFF), no cap by design (logic-event edge)")

    c.draws("+3V3_AUX", AUX_DRAW_A,
            "ID-EEPROM ~1mA + RV-3028 <0.1mA + TPS3823 15uA + INT# 10k pull")
    return c
