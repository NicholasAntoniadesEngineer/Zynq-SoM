from __future__ import annotations

from carrier.basis import register
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
    c = Circuit("power_mon", "Rail telemetry: 2x INA3221 + shunts (I2C 0x40/41)")
    c.use_part(MONITOR_PART, ref="U1")
    c.use_part(MONITOR_PART, ref="U2")

    # The rail nets SPLIT at the shunts (DEF-D): each channel therefore reads
    # only its own rail's loads, not the chain's.
    for ref, mpn, val, reg_net, board_net, mon, ch in _SHUNTS:
        c.use_part(mpn, ref=ref, value=val)
        c.net(reg_net, f"{ref}.1", f"{mon}.IN+{ch}")
        c.net(board_net, f"{ref}.2", f"{mon}.IN-{ch}")

    c.net("GND", "U2.IN+2", "U2.IN-2", "U2.IN+3", "U2.IN-3")

    c.net("+3V3_SC", "U1.VS", "U1.VPU", "U2.VS", "U2.VPU")
    c.net("GND", "U1.GND", "U1.PAD", "U2.GND", "U2.PAD")
    c.net("GND", "U1.A0")
    c.net("+3V3_SC", "U2.A0")
    for u in ("U1", "U2"):
        for cap in c.decouple(f"{u}.VS", SUPPLY_HF, footprint=C0603):
            cap.fields["LCSC"] = "C14663"
    c.part("C3", "Device:C", SUPPLY_BULK, C0805, LCSC="C15850")
    c.net("+3V3_SC", "C3.1")
    c.net("GND", "C3.2")

    c.port("STM32_I2C2_SDA", "U1.SDA", "U2.SDA",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ,
           expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U1.SCL", "U2.SCL",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ,
           expect=J1_MAP)

    c.part("R1", "Device:R", ALERT_PULLUP, R0603, LCSC="C25804")
    c.port("PMON_ALERT_N", "U1.CRITICAL", "U2.CRITICAL", "R1.2",
           expect=BRINGUP_INT)
    c.net("+3V3_SC", "R1.1")

    c.nc("U1.WARNING", "U1.PV", "U1.TC", "U2.WARNING", "U2.PV", "U2.TC")

    c.draws("+3V3_SC", SUPPLY_DRAW_A, "2x INA3221 ~0.7 mA + ALERT pull-up")

    for rail, shunt, board_tp in _TESTPOINT_WAIVERS:
        c.waive_tp(rail, f"reg-side of {shunt} — probe across the shunt "
                         f"(the {board_tp} TP is the post-shunt/load side)")
    return c
