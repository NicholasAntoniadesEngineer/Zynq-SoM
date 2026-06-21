"""motor_pwm — 8-channel PWM/ESC output buffer (benchtop drone demo).

The OUTPUT half of the carrier's generic motor interface (the telemetry +
motor-rail half is `motor_sense`; split so neither sheet is dense enough to
defeat the placer's rail-stub router). KEPT GENERIC: a reusable robotics PWM
breakout — the ESCs, props and battery are all OFF board.

The Zynq PL drives 8 LVCMOS33 fabric pins (8 genuinely-free bank-33 contract
pins, verified vs som_interface.json + the XDC) into an octal 74HCT245 buffer
(U1) that level-translates 3.3 V -> 5 V (HCT TTL thresholds accept the 3.3 V
inputs at a 5 V VCC) and ISOLATES the PL: an ESC-side fault only reaches the 5 V
B-side, never a PL pin. The buffered 5 V outputs go to the 3x8 output header J1
(per channel: SIG / +5V / GND). Standard PWM or DShot in fabric.

FAIL-SAFE ARM: the PL drives #OE low to enable; a 10 k pull-up holds the buffer
outputs HiZ (no spurious ESC pulses) until the PL explicitly arms.

OUTPUT SERIES-DAMPING: each buffered output passes through a 33 R series element
(RN1/RN2, two isolated 4D03WGJ0330T5E arrays — RN1 ch0-3, RN2 ch4-7) before the
header SIG row, for EMI / DShot edge integrity into the off-board leads. Element j
of a 4D03 spans pin (j+1)<->pin(8-j) (footprint-verified vertical pad pairs): the
buffered ESC_SIG{i} enters the top pad, the damped ESC_OUT{i} leaves the facing
pad onto J1.SIG{1+i}. ISOLATED elements (no internal common) so a faulted ESC lead
cannot back-feed a sibling. The two arrays reconverging on the 24-pin header form a
tree the chain placer strung wide; the within-component row-wrap in place.py
(PAPER_W_BUDGET) lands it on A3 — demoting the crossed channel to labeled stubs
(KiCad merges by name, netlist untouched), a strict no-op for every other sheet.

SERVO-RAIL PROTECTION: the header's middle (+5 V) row is gated by a SY6280 load
switch (U3) whose current-limit (ILIM = 6800/13 k = 523 mA) protects board +5 V
against a shorted servo lead. The buffer itself runs off RAW +5 V so it is always
alive (armed by #OE); only the servo power is limited. ESC leads use SIG+GND only
(their BEC stays off the rail) — see the README silk note.

PL pin ledger (all FREE; XDC "unclaimed (wave-3 function map)"; IO->ESC renames
live in som_conn_gen.FUNCTION_MAP):
  ESC_PWM_IN0..3 = IO_L14_SRCC_P/N_33, IO_L11_SRCC_P/N_33  (J2.81/83/93/91)
  ESC_PWM_IN4..7 = IO_L3_DQS_P/N_33,   IO_L5_P/N_33         (J3.91/93/92/94)
  ESC_BUF_OE_N   = IO_L1P_13  (J2.57)

DEFERRED (sourced follow-up, NOT guessed; LAW 7): a 5 V-rated ESD array on the
outputs — the spec's PESD3V3L4UG is 3.3 V-working and would clamp the 5 V PWM, so
it is NOT used; needs an EasyEDA-API-verified 5 V-rated array. The buffer drive +
isolation + 33 R damping are the essential function; the ESD add is EMI/ESD polish.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"   # 100n X7R 50V 0603
LCSC_10U = "C15850"    # 10u 0805
LCSC_10K = "C25804"    # 10k 1% 0603
LCSC_13K = "C22797"    # 13k 1% 0603 -> SY6280 ILIM 523 mA
LCSC_33R_ARRAY = "C25508"   # 4x33R 0603x4 isolated array (output series-damping)

J2_MAP = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)"
J3_MAP = "som_j3_connector (bank 33 PL — ESC PWM 4-7)"

# 8 PWM channels: (buffer A-pin, buffer B-pin, source connector for the PL input)
_CH = [
    ("A1", "B1", J2_MAP), ("A2", "B2", J2_MAP),
    ("A3", "B3", J2_MAP), ("A4", "B4", J2_MAP),
    ("A5", "B5", J3_MAP), ("A6", "B6", J3_MAP),
    ("A7", "B7", J3_MAP), ("A8", "B8", J3_MAP),
]


def circuit() -> Circuit:
    c = Circuit("motor_pwm", "8-ch PWM/ESC output buffer (5V, PL-isolating)")

    # ===== U1: octal 3.3V->5V output buffer (PL PWM -> ESC) ==================
    c.use_part("SN74HCT245PWR", ref="U1")
    c.net("+5V", "U1.VCC", "U1.DIR")            # DIR high = A->B (PL -> ESC)
    c.net("GND", "U1.GND")
    for cap in c.decouple("U1.VCC", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.port("ESC_BUF_OE_N", "U1.#OE", expect=J2_MAP)
    c.pullup("U1.#OE", "10k", "+5V", footprint=R_FP).fields["LCSC"] = LCSC_10K

    # ===== 8 PWM channels: PL -> U1.A; U1.B (5V buffered) -> 33R damp -> SIG ===
    # Per-channel 33 R series-damping into the off-board ESC leads (EMI / DShot
    # edge integrity). Two 4-element isolated arrays (4D03WGJ0330T5E, C25508):
    # RN1 = ch0-3, RN2 = ch4-7. Footprint-verified vertical pad pairs — element
    # j of a 4D03 spans pin (j+1) <-> pin (8-j): the buffered B output enters the
    # TOP pad (pins 1-4), the damped output leaves the facing BOTTOM pad (8-5)
    # into the header SIG row. ISOLATED elements: no internal common (each R is
    # its own 2-pad device), so a faulted ESC lead cannot back-feed a sibling.
    c.use_part("4D03WGJ0330T5E", ref="RN1")     # ch0-3 series-damping array
    c.use_part("4D03WGJ0330T5E", ref="RN2")     # ch4-7 series-damping array
    c.use_part("HX_PZ2.54-3x8P_ZZ", ref="J1")
    for i, (apin, bpin, src) in enumerate(_CH):
        rn = "RN1" if i < 4 else "RN2"          # array; j = element within it
        j = i % 4                                # 0..3 -> pins (j+1) top, (8-j) bot
        c.port(f"ESC_PWM_IN{i}", f"U1.{apin}", expect=src)      # PL -> buffer A
        c.net(f"ESC_SIG{i}", f"U1.{bpin}", f"{rn}.{j + 1}")     # buffered -> R in
        c.net(f"ESC_OUT{i}", f"{rn}.{8 - j}", f"J1.{1 + i}")    # R out -> SIG row
    c.net("+5V_MOTOR_IO", *[f"J1.{p}" for p in range(9, 17)])    # +5V row (9-16)
    c.net("GND", *[f"J1.{p}" for p in range(17, 25)])            # GND row (17-24)

    # ===== U3: SY6280 gates +5V -> +5V_MOTOR_IO (servo-rail current limit) ====
    # default-ON (EN high): the ILIM (523 mA) protects board +5V from a shorted
    # servo lead; the buffer runs off raw +5V (always alive, armed by #OE).
    c.use_part("SY6280AAC", ref="U3")
    c.net("+5V", "U3.IN", "U3.EN")
    c.net("+5V_MOTOR_IO", "U3.OUT")
    c.net("GND", "U3.GND")
    rset = c.part(c.auto_ref("R"), "Device:R", "13k", R_FP, LCSC=LCSC_13K)
    c.net("MIO_ISET", "U3.ISET", f"{rset.ref}.1")
    c.net("GND", f"{rset.ref}.2")
    for cap in c.decouple("U3.IN", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    cblk = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+5V_MOTOR_IO", f"{cblk.ref}.1")      # servo-rail hold-up (SY6280 rec.)
    c.net("GND", f"{cblk.ref}.2")

    c.draws("+5V", 0.080, "HCT245 buffer + light servo allowance (ILIM 523mA)")
    c.testpoint("+5V_MOTOR_IO")                 # gated servo rail
    return c
