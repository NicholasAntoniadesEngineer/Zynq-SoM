from __future__ import annotations

from carrier.basis import PROJECT, register
from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

J1_MAP = "som_j1_connector"
BRINGUP_INT = "bringup (TCA9535 spare port P11)"

MONITOR_PART = register(
    "power_mon.monitor", "INA3221AIRGVR", "part",
    "TI INA3221 triple rail monitor, LCSC C181255 (the task's C190480 is a "
    "live-verified ghost). AMX-2: the +VIN channel sense pins keep ~3 V margin "
    "to the 26 V common-mode abs max at the eFuse OVP-trip corner (+VIN can "
    "reach ~23.06 V typ). That headroom is COUPLED to the pd_input OVP setpoint "
    "(PD-1) — widening the OVP trip must re-check this 26 V limit.",
    "datasheet")

SHUNT_3A = register(
    "power_mon.shunt_3a", "10mR", "ohm",
    "Series shunt on the 3 A rails (+VIN, +5V, +3V3), sized from the PLAN rail "
    "budgets: 30 mV at 3 A, 4 mA LSB. Part RLM12FTCMR010, 1206.",
    "datasheet")

SHUNT_600MA = register(
    "power_mon.shunt_600ma", "20mR", "ohm",
    "Series shunt on the 600 mA +1V8 rail: 12 mV, 2 mA LSB. Part "
    "RLM12FTCMR020, 1206.",
    "datasheet")

SUPPLY_HF = register("power_mon.supply_hf", "100n", "F",
                     "Per-VS decoupling. LCSC C14663, Basic, 20.6M stock "
                     "(2026-06-11).",
                     "datasheet")

SUPPLY_BULK = register("power_mon.supply_bulk", "10u", "F",
                       "Shared +3V3_SC bulk for both monitors. LCSC C15850.",
                       "datasheet")

ALERT_PULLUP = register(
    "power_mon.alert_pullup", "10k", "ohm",
    "Defined-high pull for the wire-ORed open-drain CRITICAL outputs. LCSC "
    "C25804.",
    "datasheet")

I2C_SPEED_HZ = register(
    "power_mon.i2c_speed", 400_000, "Hz",
    "Fast-mode I2C on the shared STM32_I2C2 trunk. Bus pull-ups live on "
    "usb_pd/bringup, never duplicated here.",
    "datasheet")

SUPPLY_DRAW_A = register(
    "power_mon.supply_draw", 0.002, "A",
    "2x INA3221 IQ ~350 uA each (dossier section 2) plus the 10k ALERT pull-up "
    "when asserted (~0.3 mA), rounded up.",
    "datasheet")

_SHUNTS = (
    ("RS1", "RLM12FTCMR010", SHUNT_3A, "+VIN", "+VIN_SYS", "U1", 1),
    ("RS2", "RLM12FTCMR010", SHUNT_3A, "+5V_REG", "+5V", "U1", 2),
    ("RS3", "RLM12FTCMR010", SHUNT_3A, "+3V3_REG", "+3V3", "U1", 3),
    ("RS4", "RLM12FTCMR020", SHUNT_600MA, "+1V8_REG", "+1V8", "U2", 1),
)

_TESTPOINT_WAIVERS = (
    ("+VIN_SYS", "RS1", "+VIN @ pd_input"),
    ("+5V_REG", "RS2", "+5V"),
    ("+3V3_REG", "RS3", "+3V3"),
    ("+1V8_REG", "RS4", "+1V8"),
)


def circuit() -> Circuit:
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'power_mon', __file__)
