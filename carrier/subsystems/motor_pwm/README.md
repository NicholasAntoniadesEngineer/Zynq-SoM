# motor_pwm — 8-channel PWM/ESC output buffer (carrier-local)

The OUTPUT half of the carrier's generic, bench-top "drone capability" motor
interface (telemetry is in `motor_sense`; split so neither sheet is dense enough
to defeat the placer). A reusable robotics PWM breakout — ESCs/props/battery are
all **off board**.

| block | parts | function |
|-------|-------|----------|
| 8-ch buffer | `U1` SN74HCT245 | PL 3.3 V LVCMOS33 → 5 V buffered PWM/DShot; **isolates the PL** (ESC-side faults hit only the 5 V B-side) |
| fail-safe arm | `#OE` 10 k pull-up | outputs **HiZ** until the PL drives `ESC_BUF_OE_N` low |
| output series-damp | `RN1`/`RN2` 4×33 R arrays | per-channel 33 R between `U1.B` and the header SIG row (EMI / DShot edge integrity into the off-board leads); two isolated `4D03WGJ0330T5E` (C25508) arrays, RN1 ch0-3, RN2 ch4-7 |
| output header | `J1` 3×8 2.54 mm | per channel: SIG / +5V / GND (SIG = damped output `U1.B → 33 R → J1`) |
| servo-rail protect | `U3` SY6280 | gates +5V → `+5V_MOTOR_IO` with a 523 mA ILIM (a shorted servo lead can't crash board +5V) |

**ESC leads use SIG + GND only** (leave their BEC red wire off the +5V row). The
PL drives the 8 PWM (bank-33) + `ESC_BUF_OE_N` (bank-13) on contract pins verified
free (XDC "unclaimed"); renames in `som_conn_gen.FUNCTION_MAP`.

**Series-damping 33 R — LANDED (LAW 7).** Per-channel 33 R series damping on the
8 buffered outputs (EMI / DShot edge integrity into the off-board leads) is now in
the netlist: two isolated 4-element arrays (`4D03WGJ0330T5E`, `C25508`, sourced),
RN1 = ch0-3, RN2 = ch4-7. Element *j* of a 4D03 spans pin (j+1)↔(8-j) — the
footprint's vertical pad pairs — so the buffered `ESC_SIG{i}` enters the top pad
and the damped `ESC_OUT{i}` leaves the facing pad onto the header SIG row. The two
arrays reconverging on the 24-pin header form a *tree* the per-sheet placer's
chain template strung to >400 mm (overflowing A3) — the reason this was held back.
The fix is a **within-component row-wrap** in `schgen/layout/place.py`
(`PAPER_W_BUDGET`): when a single connected component's row would overflow the
page, the placer wraps the offending part to a new row and demotes the crossed
channel to labeled stubs (KiCad merges by name — netlist untouched). The budget
is instrumented to be a strict no-op for every other sheet, so only this overflow
trips it.

**Deferred (sourced follow-up, not guessed):** a **5 V-rated** ESD array on the
outputs — the spec's PESD3V3L4UG is 3.3 V-working and would clamp the 5 V PWM, so
it is deliberately not used (needs an API-verified 5 V-rated array).
