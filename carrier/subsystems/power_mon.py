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

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

J1_MAP = "som_j1_connector"
BRINGUP_INT = "bringup (TCA9535 spare port P11)"

def circuit() -> Circuit:
    c = Circuit("power_mon", "Rail telemetry: 2x INA3221 + shunts (I2C 0x40/41)")
    c.use_part("INA3221AIRGVR", ref="U1")                # 0x40: A0=GND
    c.use_part("INA3221AIRGVR", ref="U2")                # 0x41: A0=VS

    # ---- shunts: regulator side -> board rail (research dossier table 1) ---
    c.use_part("RLM12FTCMR010", ref="RS1", value="10mR")
    c.net("+VIN", "RS1.1", "U1.IN+1")                # PD entry (usb_pd sense)
    c.net("+VIN_SYS", "RS1.2", "U1.IN-1")            # buck-1 input (power.py)
    c.use_part("RLM12FTCMR010", ref="RS2", value="10mR")
    c.net("+5V_REG", "RS2.1", "U1.IN+2")             # buck-1 output cluster
    c.net("+5V", "RS2.2", "U1.IN-2")                 # board +5V rail
    c.use_part("RLM12FTCMR010", ref="RS3", value="10mR")
    c.net("+3V3_REG", "RS3.1", "U1.IN+3")            # buck-2 output cluster
    c.net("+3V3", "RS3.2", "U1.IN-3")                # board +3V3 rail
    c.use_part("RLM12FTCMR020", ref="RS4", value="20mR")
    c.net("+1V8_REG", "RS4.1", "U2.IN+1")            # LDO output cluster
    c.net("+1V8", "RS4.2", "U2.IN-1")                # board +1V8 rail

    # unused U2 channels: inputs to GND (datasheet — reads 0 V / 0 A)
    c.net("GND", "U2.IN+2", "U2.IN-2", "U2.IN+3", "U2.IN-3")

    # ---- supply: always-on SC rail, address straps ------------------------
    c.net("+3V3_SC", "U1.VS", "U1.VPU", "U2.VS", "U2.VPU")
    c.net("GND", "U1.GND", "U1.PAD", "U2.GND", "U2.PAD")
    c.net("GND", "U1.A0")                                # A0 #1 -> 0x40
    c.net("+3V3_SC", "U2.A0")                            # A0 #2 -> 0x41
    for u in ("U1", "U2"):                               # C1, C2
        for cap in c.decouple(f"{u}.VS", "100n", footprint=C0603):
            cap.fields["LCSC"] = "C14663"   # Basic, 20.6M stock (2026-06-11)
    c.part("C3", "Device:C", "10u", C0805, LCSC="C15850")
    c.net("+3V3_SC", "C3.1")
    c.net("GND", "C3.2")

    # ---- I2C to the STM32 (shared bus; pulls live on usb_pd/bringup) ------
    c.port("STM32_I2C2_SDA", "U1.SDA", "U2.SDA",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U1.SCL", "U2.SCL",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)

    # ---- alert: wire-OR CRITICALs, defined-high, to the bringup expander --
    c.part("R1", "Device:R", "10k", R0603, LCSC="C25804")
    c.port("PMON_ALERT_N", "U1.CRITICAL", "U2.CRITICAL", "R1.2",
           expect=BRINGUP_INT)
    c.net("+3V3_SC", "R1.1")

    # WARNING/PV/TC: open-drain status outputs, I2C-readable — unused
    c.nc("U1.WARNING", "U1.PV", "U1.TC", "U2.WARNING", "U2.PV", "U2.TC")
    return c
