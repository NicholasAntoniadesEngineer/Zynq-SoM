"""power_mon — 2x INA3221 rail telemetry (+VIN, +5V, +3V3, +1V8).

Per carrier/research/power_mon.md: two TI INA3221 triple monitors (ONE part
number, C181255 — the task's C190480 is a live-verified ghost) on the shared
STM32_I2C2 bus at 0x40 (A0=GND) and 0x41 (A0=VS); board address map is
0x20 TCA9535 / 0x22 FUSB302B / 0x40-0x41 here. Series shunts sized from the
PLAN rail budgets: 10 mR 1206 on the 3 A nets (30 mV @ 3 A, 4 mA LSB), 20 mR
on the 600 mA +1V8 (12 mV, 2 mA LSB). The rail nets SPLIT at the shunts —
power.py keeps regulator-side clusters on +VIN_SYS / +5V_REG / +3V3_REG /
+1V8_REG and the board-facing rails live on the load side, so each channel
reads its own rail's loads only. Supplies run from the always-on +3V3_SC so
telemetry works with every monitored rail down. Both CRITICAL pins (open
drain) wire-OR into PMON_ALERT_N (10k to +3V3_SC) for the bringup expander's
spare port P11; WARNING/PV/TC stay I2C-readable and are author NCs. Unused
U2 channels have IN+/IN- tied to GND per the datasheet. No I2C pull-ups
here — usb_pd/bringup own the bus pulls.
"""

from __future__ import annotations

from schgen.model import Circuit

INA = "INA3221AIRGVR:INA3221AIRGVR"
RS10 = "RLM12FTCMR010:RLM12FTCMR010"
RS20 = "RLM12FTCMR020:RLM12FTCMR020"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

J1_MAP = "som_j1_connector"
BRINGUP_INT = "bringup (TCA9535 spare port P11)"

# INA3221 (VQFN-16) pins, from parts/INA3221AIRGVR/INA3221AIRGVR.py:
# ch1 IN+/IN- = 12/11, ch2 = 15/14, ch3 = 2/1; 3 GND, 4 VS, 5 A0, 6 SCL,
# 7 SDA, 8 WARNING, 9 CRITICAL, 10 PV, 13 TC, 16 VPU, 17 PAD.


def circuit() -> Circuit:
    c = Circuit("power_mon", "Rail telemetry: 2x INA3221 + shunts (I2C 0x40/41)")
    c.part("U1", INA, "INA3221AIRGVR", INA, LCSC="C181255")   # 0x40: A0=GND
    c.part("U2", INA, "INA3221AIRGVR", INA, LCSC="C181255")   # 0x41: A0=VS

    # ---- shunts: regulator side -> board rail (research dossier table 1) ---
    c.part("RS1", RS10, "10mR", RS10, LCSC="C188070")
    c.net("+VIN", "RS1.1", "U1.12")                  # PD entry (usb_pd sense)
    c.net("+VIN_SYS", "RS1.2", "U1.11")              # buck-1 input (power.py)
    c.part("RS2", RS10, "10mR", RS10, LCSC="C188070")
    c.net("+5V_REG", "RS2.1", "U1.15")               # buck-1 output cluster
    c.net("+5V", "RS2.2", "U1.14")                   # board +5V rail
    c.part("RS3", RS10, "10mR", RS10, LCSC="C188070")
    c.net("+3V3_REG", "RS3.1", "U1.2")               # buck-2 output cluster
    c.net("+3V3", "RS3.2", "U1.1")                   # board +3V3 rail
    c.part("RS4", RS20, "20mR", RS20, LCSC="C393094")
    c.net("+1V8_REG", "RS4.1", "U2.12")              # LDO output cluster
    c.net("+1V8", "RS4.2", "U2.11")                  # board +1V8 rail

    # unused U2 channels: inputs to GND (datasheet — reads 0 V / 0 A)
    c.net("GND", "U2.15", "U2.14", "U2.2", "U2.1")

    # ---- supply: always-on SC rail, address straps ------------------------
    c.net("+3V3_SC", "U1.4", "U1.16", "U2.4", "U2.16")   # VS + VPU both
    c.net("GND", "U1.3", "U1.17", "U2.3", "U2.17")       # GND + PAD
    c.net("GND", "U1.5")                                 # A0 #1 -> 0x40
    c.net("+3V3_SC", "U2.5")                             # A0 #2 -> 0x41
    c.decouple("U1.4", "100n", footprint=C0603)          # C1
    c.decouple("U2.4", "100n", footprint=C0603)          # C2
    c.part("C3", "Device:C", "10u", C0805, LCSC="C15850")
    c.net("+3V3_SC", "C3.1")
    c.net("GND", "C3.2")

    # ---- I2C to the STM32 (shared bus; pulls live on usb_pd/bringup) ------
    c.port("STM32_I2C2_SDA", "U1.7", "U2.7",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U1.6", "U2.6",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)

    # ---- alert: wire-OR CRITICALs, defined-high, to the bringup expander --
    c.part("R1", "Device:R", "10k", R0603, LCSC="C25804")
    c.port("PMON_ALERT_N", "U1.9", "U2.9", "R1.2", expect=BRINGUP_INT)
    c.net("+3V3_SC", "R1.1")

    # WARNING/PV/TC: open-drain status outputs, I2C-readable — unused
    c.nc("U1.8", "U1.10", "U1.13", "U2.8", "U2.10", "U2.13")
    return c
