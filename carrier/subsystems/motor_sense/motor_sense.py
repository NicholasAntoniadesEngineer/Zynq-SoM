from __future__ import annotations

from carrier.basis import PROJECT, register
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
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'motor_sense', __file__)
