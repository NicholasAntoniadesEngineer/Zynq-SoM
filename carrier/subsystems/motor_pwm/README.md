# motor_pwm — 8-channel PWM/ESC output buffer (5 V, PL-isolating)

The OUTPUT half of the carrier's generic bench-top "drone capability" motor
interface (the telemetry/motor-rail half is `motor_sense`; the two are split so
neither sheet is dense enough to defeat the placer's rail-stub router). It is a
reusable robotics PWM breakout: the Zynq PL drives 8 fabric PWM channels through
a level-translating, PL-isolating buffer to an off-board ESC/servo header. The
ESCs, props and battery are all off board.

## Interface

The subsystem drives these carrier nets:

- `ESC_PWM_IN0..7` — 8 PL fabric inputs (LVCMOS33), ports bound to the SoM
  bank-33 PL pins via the J2/J3 connectors. PWM 0-3 come from J2, PWM 4-7 from
  J3. Renames live in `som_conn_gen.FUNCTION_MAP`.
- `ESC_BUF_OE_N` — PL active-low buffer-enable port, bound to a bank-13 PL pin
  through J2.
- `+5V`, `GND` — board rails consumed by the buffer, ESD arrays and load switch.
- `+5V_MOTOR_IO` — the gated, current-limited servo-power rail feeding the
  header's +5 V row (testpoint exposed).

`c.draws("+5V", 0.080, ...)` declares the rail budget (HCT245 buffer plus the
light servo allowance under the 523 mA limit).

## Design

**Octal output buffer / PL isolation (U1, SN74HCT245PWR).** The 8 PL channels
drive an octal HCT245 with `DIR` tied to `+5V` (A→B, PL→ESC). The HCT TTL input
thresholds accept the 3.3 V LVCMOS33 PL levels at a 5 V VCC, so the buffer
level-translates 3.3 V → 5 V and isolates the PL: an ESC-side fault reaches only
the 5 V B-side, never a PL pin. The buffer runs off raw `+5V`, so it is always
powered (armed only by `#OE`). Decoupled with a 100 n 0603 (C14663).

**Fail-safe arm.** `#OE` carries a 10 k pull-up (C25804) to `+5V`, holding all
buffer outputs Hi-Z until the PL explicitly drives `ESC_BUF_OE_N` low. No
spurious ESC pulses occur before the PL arms.

**Output series-damping (RN1, RN2 — 4D03WGJ0330T5E, C25508).** Each buffered
output passes through a 33 R series element before the header SIG row, for EMI
and DShot edge integrity into the off-board leads. Two isolated 4-element arrays
are used (RN1 = ch 0-3, RN2 = ch 4-7). Element *j* of a 4D03 spans pin (j+1) ↔
(8−j) per the footprint's vertical pad pairs: the buffered `ESC_SIG{i}` enters
the top pad and the damped `ESC_OUT{i}` leaves the facing pad onto `J1.SIG`. The
elements are isolated (no internal common), so a faulted ESC lead cannot
back-feed a sibling channel.

**Output header (J1, HX_PZ2.54-3x8P_ZZ).** A 3×8 2.54 mm header, one column per
channel: SIG (pins 1-8, the damped output), +5V (pins 9-16, `+5V_MOTOR_IO`) and
GND (pins 17-24). ESC leads use SIG + GND only — their BEC stays off the +5 V
row.

**Output ESD (two SRV05-4, C2836319).** Two 5-line SRV05-4 arrays clamp the 8
off-board PWM output lines to `+5V`/`GND` at the connector, ahead of the 33 R and
buffer. The SRV05-4 has a 5 V standoff, so it does not clamp the 5 V buffered
signals. Pads bind by number on the KiCad SRV05-4 symbol (SOT-23-6): 1=IO1,
2=VN(GND), 3=IO2, 4=IO3, 5=VP(+5V), 6=IO4. VP ties to `+5V` (the rail the signals
swing against), VN to `GND`.

**Servo-rail current limit (U3, SY6280AAC).** A load switch gates `+5V` →
`+5V_MOTOR_IO`, default-ON (`EN` tied to `IN`). `ISET` sets the limit via a 13 k
resistor (C22797): ILIM = 6800 / 13 k ≈ 523 mA, protecting board `+5V` against a
shorted servo lead. Only the servo power is limited; the buffer itself stays on
raw `+5V`. The input is decoupled with a 100 n (C14663) and the gated output
holds up on a 10 u 0805 bulk cap (C15850).

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1 | SN74HCT245PWR | SN74HCT245PWR | — |
| U3 | SY6280AAC | SY6280AAC | — |
| RN1 | 4×33 R array | 4D03WGJ0330T5E | C25508 |
| RN2 | 4×33 R array | 4D03WGJ0330T5E | C25508 |
| J1 | 3×8 2.54 mm | HX_PZ2.54-3x8P_ZZ | — |
| D* (×2) | SRV05-4 | Power_Protection:SRV05-4 (SOT-23-6) | C2836319 |
| R* (#OE pull-up) | 10k | Device:R | C25804 |
| R* (ISET) | 13k | Device:R | C22797 |
| C* (U1 decouple) | 100n | Device:C (0603) | C14663 |
| C* (U3 decouple) | 100n | Device:C (0603) | C14663 |
| C* (rail bulk) | 10u | Device:C (0805) | C15850 |

## Build & test

`test_motor_pwm.py` asserts the circuit structure (buffer, channels, damping,
ESD, load switch and rails). Run:

```
pytest carrier/subsystems/motor_pwm/test_motor_pwm.py
```
