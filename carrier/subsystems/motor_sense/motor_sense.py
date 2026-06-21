"""motor_sense — ESC motor-rail telemetry + in-line current sense (drone demo).

The TELEMETRY half of the carrier's generic motor interface (the 8-ch PWM output
half is `motor_pwm`). KEPT GENERIC: a reusable in-line power-sense pass-through —
ESCs, props and battery are all OFF board, no flight hardware here.

The ESC battery / bench supply passes IN-LINE through the carrier: J2 (XT60 in)
-> RS1 10 mΩ shunt -> J3 (XT60 out) -> off-board ESCs. An INA3221 (U2) reads
current (across RS1) AND bus voltage (at IN-1, the load side) on ONE channel, on
the always-on STM32_I2C2 SC bus at 0x42 (0x40/0x41 are power_mon). Its CRITICAL
open-drain alert is a fast over-current event back to the PL (ESC_FAULT_N).

ISOLATION / SAFETY (bench-only, no flight): the dirty motor rail shares only GND
with logic; PL pins never see it. SMBJ28A (D1) clamps hot-plug / inductive
transients on the ESC bus. The INA3221 common-mode abs-max is 26 V and its TVS
clamps ABOVE that, so the ESC rail is bounded <= 4S (<= ~20 V) for margin (silk +
README), not by the TVS — use a current-limited bench supply (or add bulk near
the ESCs/PDB) to avoid hot-plug transients into the monitor.

PL pin ledger (FREE; XDC "unclaimed"; rename in som_conn_gen.FUNCTION_MAP):
  ESC_FAULT_N = IO_L1_N_13  (J2.37)

DEFERRED (sourced follow-up, NOT guessed; LAW 7): an on-board electrolytic bulk
cap on the motor rail (the 100 n 50 V HF bypass + the TVS + the <= 4S bound cover
v1; off-board bulk is recommended). Needs an EasyEDA-API-verified >=35 V part; the
search endpoint was down at authoring time.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"   # 100n X7R 50V 0603
LCSC_10U = "C15850"    # 10u 0805
LCSC_10K = "C25804"    # 10k 1% 0603

J1_MAP = "som_j1_connector (STM32_I2C2 SC management bus)"
J2_MAP = "som_j2_connector (bank 13 PL — ESC_FAULT_N)"


def circuit() -> Circuit:
    c = Circuit("motor_sense",
                "ESC motor-rail telemetry: INA3221 + 10mR shunt (I2C 0x42)")

    # ===== motor power IN-LINE: J2 (XT60 in) -> RS1 shunt -> J3 (XT60 out) ====
    c.use_part("XT60PW-M", ref="J2")            # ESC battery / bench-supply IN
    c.net("ESC_VRAIL_IN", "J2.+")
    c.net("GND", "J2.-", "J2.3", "J2.4")        # +/- + 2 mounting tabs to GND
    c.use_part("SMBJ28A", ref="D1")             # TVS clamp on the ESC bus
    c.net("ESC_VRAIL_IN", "D1.K")
    c.net("GND", "D1.A")
    chf = c.part(c.auto_ref("C"), "Device:C", "100n", C_FP, LCSC=LCSC_100N)
    c.net("ESC_VRAIL_IN", f"{chf.ref}.1")       # HF bypass (bulk is off-board)
    c.net("GND", f"{chf.ref}.2")
    c.use_part("RLM12FTCMR010", ref="RS1", value="10mR")
    c.net("ESC_VRAIL_IN", "RS1.1")
    c.net("ESC_VRAIL", "RS1.2")                 # post-shunt / load side
    c.use_part("XT60PW-M", ref="J3")            # ESC rail OUT (to off-board ESCs)
    c.net("ESC_VRAIL", "J3.+")
    c.net("GND", "J3.-", "J3.3", "J3.4")

    # ===== U2: INA3221 rail telemetry on STM32_I2C2 (0x42) ===================
    c.use_part("INA3221AIRGVR", ref="U2")
    c.net("ESC_VRAIL_IN", "U2.IN+1")            # shunt high side
    c.net("ESC_VRAIL", "U2.IN-1")               # shunt low side = bus-V sense
    c.net("GND", "U2.IN+2", "U2.IN-2", "U2.IN+3", "U2.IN-3")  # unused ch -> GND
    c.net("+3V3_SC", "U2.VS", "U2.VPU")         # always-on SC rail
    c.net("GND", "U2.GND", "U2.PAD")
    for cap in c.decouple("U2.VS", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c2 = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+3V3_SC", f"{c2.ref}.1")
    c.net("GND", f"{c2.ref}.2")
    # A0 strapped to SDA -> I2C address 0x42 (datasheet address table)
    c.port("STM32_I2C2_SDA", "U2.SDA", "U2.A0", kind="i2c", role="sda",
           bus="STM32_I2C2", speed_hz=400_000, expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U2.SCL", kind="i2c", role="scl",
           bus="STM32_I2C2", speed_hz=400_000, expect=J1_MAP)
    # CRITICAL over-current alert (open drain) -> PL fast-shutdown event
    c.port("ESC_FAULT_N", "U2.CRITICAL", expect=J2_MAP)
    c.pullup("U2.CRITICAL", "10k", "+3V3_SC", footprint=R_FP).fields["LCSC"] = \
        LCSC_10K
    c.nc("U2.WARNING", "U2.PV", "U2.TC")        # I2C-readable, unused

    c.draws("+3V3_SC", 0.002, "INA3221 ~0.35 mA + CRITICAL pull-up")
    # ESC_VRAIL is externally sourced + metered by U2 over I2C; probe it at the
    # J2/J3 XT60 terminals (no on-board TP pad).
    return c
