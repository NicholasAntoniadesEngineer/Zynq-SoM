from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"
LCSC_10U = "C15850"
LCSC_10K = "C25804"
LCSC_13K = "C22797"
LCSC_33R_ARRAY = "C25508"
LCSC_SRV05 = "C2836319"
SOT23_6 = "Package_TO_SOT_SMD:SOT-23-6"

J2_MAP = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)"
J3_MAP = "som_j3_connector (bank 33 PL — ESC PWM 4-7)"

BUFFER_PART = register(
    "motor_pwm.buffer", "SN74HCT245PWR", "part",
    "Octal buffer level-translating 3.3 V -> 5 V (HCT TTL thresholds accept "
    "the LVCMOS33 inputs at a 5 V VCC) and isolating the PL: an ESC-side fault "
    "reaches only the 5 V B-side, never a PL pin. DIR high = A->B.",
    "datasheet")

OE_PULLUP = register(
    "motor_pwm.oe_pullup", "10k", "ohm",
    "FAIL-SAFE ARM: holds #OE high so the buffer outputs stay HiZ and emit no "
    "spurious ESC pulses until the PL explicitly drives #OE low. LCSC C25804.",
    "datasheet")

DAMPING_ARRAY = register(
    "motor_pwm.damping_array", "4D03WGJ0330T5E", "part",
    "4x33R series damping into the off-board ESC leads for EMI / DShot edge "
    "integrity. ISOLATED elements — no internal common — so a faulted lead "
    "cannot back-feed a sibling. Element j spans pin (j+1) <-> pin (8-j) on the "
    "verified footprint: buffered signal in the top pad, damped signal out the "
    "facing pad. LCSC C25508.",
    "datasheet")

ESD_ARRAY = register(
    "motor_pwm.esd_array", "SRV05-4", "part",
    "5 V standoff, so it does NOT clamp the 5 V buffered signals — the 3.3 V "
    "PESD3V3L4UG the spec named would. Clamps the 8 leads at the connector, "
    "ahead of the damping array and the buffer. KiCad SOT-23-6 pin map "
    "1=IO1 2=VN 3=IO2 4=IO3 5=VP 6=IO4; schgen binds by pad NUMBER, not name. "
    "LCSC C2836319.",
    "datasheet")

OUTPUT_HEADER = register(
    "motor_pwm.output_header", "HX_PZ2.54-3x8P_ZZ", "part",
    "3x8 output header, per channel SIG / +5V / GND: SIG on 1..8, +5V on 9..16, "
    "GND on 17..24.",
    "datasheet")

SERVO_ISET = register(
    "motor_pwm.servo_iset", "13k", "ohm",
    "SY6280 ILIM = 6800/13k = 523 mA, protecting board +5V against a shorted "
    "servo lead. Only the servo POWER row is limited; the buffer runs off raw "
    "+5V so it is always alive, armed by #OE. LCSC C22797.",
    "datasheet")

SWITCH_DECAP = register("motor_pwm.switch_decap", "100n", "F",
                        "HF companion to the SY6280's recommended input cap, "
                        "and the HCT245 VCC bypass. LCSC C14663.", "datasheet")

SERVO_HOLDUP = register("motor_pwm.servo_holdup", "10u", "F",
                        "Servo-rail hold-up at U3.OUT, the SY6280-recommended "
                        "output cap. LCSC C15850.", "datasheet")

BUFFER_DRAW_A = register("motor_pwm.buffer_draw", 0.080, "A",
                         "HCT245 buffer plus a light servo allowance under the "
                         "523 mA ILIM.", "datasheet")

_CH = [
    ("A1", "B1", J2_MAP), ("A2", "B2", J2_MAP),
    ("A3", "B3", J2_MAP), ("A4", "B4", J2_MAP),
    ("A5", "B5", J3_MAP), ("A6", "B6", J3_MAP),
    ("A7", "B7", J3_MAP), ("A8", "B8", J3_MAP),
]

_CHANNELS_PER_ARRAY = 4
_ARRAY_TOP_PIN = 1
_ARRAY_SPAN = 8
_SIG_FIRST_PIN = 1
_RAIL_ROW = range(9, 17)
_GND_ROW = range(17, 25)
_ESD_ARRAYS = 2
_ESD_IO_PINS = (1, 3, 4, 6)
_ESD_VP_PIN = 5
_ESD_VN_PIN = 2


def circuit() -> Circuit:
    c = Circuit("motor_pwm", "8-ch PWM/ESC output buffer (5V, PL-isolating)")

    c.use_part(BUFFER_PART, ref="U1")
    c.net("+5V", "U1.VCC", "U1.DIR")
    c.net("GND", "U1.GND")
    for cap in c.decouple("U1.VCC", SWITCH_DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.port("ESC_BUF_OE_N", "U1.#OE", expect=J2_MAP)
    c.pullup("U1.#OE", OE_PULLUP, "+5V",
             footprint=R_FP).fields["LCSC"] = LCSC_10K

    c.use_part(DAMPING_ARRAY, ref="RN1")
    c.use_part(DAMPING_ARRAY, ref="RN2")
    c.use_part(OUTPUT_HEADER, ref="J1")
    for i, (apin, bpin, src) in enumerate(_CH):
        rn = "RN1" if i < _CHANNELS_PER_ARRAY else "RN2"
        j = i % _CHANNELS_PER_ARRAY
        c.port(f"ESC_PWM_IN{i}", f"U1.{apin}", expect=src)
        c.net(f"ESC_SIG{i}", f"U1.{bpin}", f"{rn}.{j + _ARRAY_TOP_PIN}")
        c.net(f"ESC_OUT{i}", f"{rn}.{_ARRAY_SPAN - j}",
              f"J1.{_SIG_FIRST_PIN + i}")
    c.net("+5V_MOTOR_IO", *[f"J1.{p}" for p in _RAIL_ROW])
    c.net("GND", *[f"J1.{p}" for p in _GND_ROW])

    for arr in range(_ESD_ARRAYS):
        ed = c.part(c.auto_ref("D"), "Power_Protection:SRV05-4", ESD_ARRAY,
                    SOT23_6, LCSC=LCSC_SRV05)
        b = arr * _CHANNELS_PER_ARRAY
        for k, pad in enumerate(_ESD_IO_PINS):
            c.net(f"ESC_OUT{b + k}", f"{ed.ref}.{pad}")
        c.net("+5V", f"{ed.ref}.{_ESD_VP_PIN}")
        c.net("GND", f"{ed.ref}.{_ESD_VN_PIN}")

    c.use_part("SY6280AAC", ref="U3")
    c.net("+5V", "U3.IN", "U3.EN")
    c.net("+5V_MOTOR_IO", "U3.OUT")
    c.net("GND", "U3.GND")
    rset = c.part(c.auto_ref("R"), "Device:R", SERVO_ISET, R_FP, LCSC=LCSC_13K)
    c.net("MIO_ISET", "U3.ISET", f"{rset.ref}.1")
    c.net("GND", f"{rset.ref}.2")
    for cap in c.decouple("U3.IN", SWITCH_DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    cblk = c.part(c.auto_ref("C"), "Device:C", SERVO_HOLDUP, C0805,
                  LCSC=LCSC_10U)
    c.net("+5V_MOTOR_IO", f"{cblk.ref}.1")
    c.net("GND", f"{cblk.ref}.2")

    c.draws("+5V", BUFFER_DRAW_A,
            "HCT245 buffer + light servo allowance (ILIM 523mA)")
    c.testpoint("+5V_MOTOR_IO")
    return c
