from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
CP_ELEC_D10 = "Capacitor_SMD:CP_Elec_10x10.5"

LCSC_100N = "C14663"
LCSC_10U = "C15850"
LCSC_10K = "C25804"
LCSC_470U = "C976030"

J1_MAP = "som_j1_connector (STM32_I2C2 SC management bus)"
J2_MAP = "som_j2_connector (bank 13 PL — ESC_FAULT_N)"

RAIL_CONNECTOR = register(
    "motor_sense.rail_connector", "XT60PW-M", "part",
    "ESC battery / bench-supply inlet and the outlet to the off-board ESCs. "
    "The rail passes IN-LINE through the shunt, so J2 is pre-shunt and J3 "
    "post-shunt.",
    "datasheet")

RAIL_TVS = register(
    "motor_sense.rail_tvs", "SMBJ28A", "part",
    "28 V standoff TVS clamping the hot-plug edge on the ESC bus, ahead of the "
    "shunt and the INA3221 sense pins.",
    "datasheet")

SHUNT = register(
    "motor_sense.shunt", "10mR", "ohm",
    "In-line current-sense element, RLM12FTCMR010 1206. The rail splits at it: "
    "ESC_VRAIL_IN is the high side, ESC_VRAIL the load side the INA3221 also "
    "uses as its bus-voltage sense node.",
    "datasheet")

MONITOR_ADDR = register(
    "motor_sense.monitor_addr", "0x42", "i2c-addr",
    "A0 strapped to SDA selects 0x42 per the INA3221 address table, clear of "
    "the power_mon pair at 0x40/0x41.",
    "datasheet")

I2C_SPEED_HZ = register("motor_sense.i2c_speed", 400_000, "Hz",
                        "Fast-mode STM32_I2C2.", "datasheet")

RAIL_HF = register("motor_sense.rail_hf", "100n", "F",
                   "HF bypass on the pre-shunt ESC bus. LCSC C14663.",
                   "datasheet")

SUPPLY_HF = register("motor_sense.supply_hf", "100n", "F",
                     "INA3221 VS bypass. LCSC C14663.", "datasheet")

SUPPLY_BULK = register("motor_sense.supply_bulk", "10u", "F",
                       "Local +3V3_SC bulk. LCSC C15850.", "datasheet")

FAULT_PULLUP = register("motor_sense.fault_pullup", "10k", "ohm",
                        "Defined-high pull for the open-drain CRITICAL "
                        "over-current alert. LCSC C25804.", "datasheet")

RAIL_BULK = register(
    "motor_sense.rail_bulk", "470uF/35V", "F",
    "Local energy store for the ESC commutation-current pulses that also "
    "stabilises the bus-V node U2 meters. 35 V covers a 4S rail with >1.5x "
    "margin; the input TVS clamps the hot-plug edge. Placed on the LOAD-side "
    "net, not the dense pre-shunt trunk. LCSC C976030 (DMBJ RVT1V471M1010, "
    "D10x10.2) seats on the stock D10x10.5 land pattern.",
    "datasheet")

SC_DRAW_A = register("motor_sense.sc_draw", 0.002, "A",
                     "INA3221 ~0.35 mA + the CRITICAL pull-up.", "datasheet")


def circuit() -> Circuit:
    c = Circuit("motor_sense",
                "ESC motor-rail telemetry: INA3221 + 10mR shunt (I2C 0x42)")

    c.use_part(RAIL_CONNECTOR, ref="J2")
    c.net("ESC_VRAIL_IN", "J2.+")
    c.net("GND", "J2.-", "J2.3", "J2.4")
    c.use_part(RAIL_TVS, ref="D1")
    c.net("ESC_VRAIL_IN", "D1.K")
    c.net("GND", "D1.A")
    chf = c.part(c.auto_ref("C"), "Device:C", RAIL_HF, C_FP, LCSC=LCSC_100N)
    c.net("ESC_VRAIL_IN", f"{chf.ref}.1")
    c.net("GND", f"{chf.ref}.2")
    c.use_part("RLM12FTCMR010", ref="RS1", value=SHUNT)
    c.net("ESC_VRAIL_IN", "RS1.1")
    c.net("ESC_VRAIL", "RS1.2")
    c.use_part(RAIL_CONNECTOR, ref="J3")
    c.net("ESC_VRAIL", "J3.+")
    c.net("GND", "J3.-", "J3.3", "J3.4")

    c.use_part("INA3221AIRGVR", ref="U2")
    c.net("ESC_VRAIL_IN", "U2.IN+1")
    c.net("ESC_VRAIL", "U2.IN-1")
    c.net("GND", "U2.IN+2", "U2.IN-2", "U2.IN+3", "U2.IN-3")
    c.net("+3V3_SC", "U2.VS", "U2.VPU")
    c.net("GND", "U2.GND", "U2.PAD")
    for cap in c.decouple("U2.VS", SUPPLY_HF, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c2 = c.part(c.auto_ref("C"), "Device:C", SUPPLY_BULK, C0805, LCSC=LCSC_10U)
    c.net("+3V3_SC", f"{c2.ref}.1")
    c.net("GND", f"{c2.ref}.2")
    c.port("STM32_I2C2_SDA", "U2.SDA", "U2.A0", kind="i2c", role="sda",
           bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ, expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U2.SCL", kind="i2c", role="scl",
           bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ, expect=J1_MAP)
    c.port("ESC_FAULT_N", "U2.CRITICAL", expect=J2_MAP)
    c.pullup("U2.CRITICAL", FAULT_PULLUP, "+3V3_SC",
             footprint=R_FP).fields["LCSC"] = LCSC_10K
    c.nc("U2.WARNING", "U2.PV", "U2.TC")

    cb = c.part(c.auto_ref("C"), "Device:C_Polarized", RAIL_BULK, CP_ELEC_D10,
                LCSC=LCSC_470U)
    c.net("ESC_VRAIL", f"{cb.ref}.1")
    c.net("GND", f"{cb.ref}.2")

    c.draws("+3V3_SC", SC_DRAW_A, "INA3221 ~0.35 mA + CRITICAL pull-up")
    # ESC_VRAIL is externally sourced and metered over I2C — probe it at the
    # XT60 terminals; there is deliberately no on-board TP pad.
    return c
