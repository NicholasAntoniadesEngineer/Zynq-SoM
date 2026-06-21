# motor_pwm — 8-channel PWM/ESC output buffer (carrier-local)

The OUTPUT half of the carrier's generic, bench-top "drone capability" motor
interface (telemetry is in `motor_sense`; split so neither sheet is dense enough
to defeat the placer). A reusable robotics PWM breakout — ESCs/props/battery are
all **off board**.

| block | parts | function |
|-------|-------|----------|
| 8-ch buffer | `U1` SN74HCT245 | PL 3.3 V LVCMOS33 → 5 V buffered PWM/DShot; **isolates the PL** (ESC-side faults hit only the 5 V B-side) |
| fail-safe arm | `#OE` 10 k pull-up | outputs **HiZ** until the PL drives `ESC_BUF_OE_N` low |
| output header | `J1` 3×8 2.54 mm | per channel: SIG / +5V / GND (buffered output direct from `U1.B`) |
| servo-rail protect | `U3` SY6280 | gates +5V → `+5V_MOTOR_IO` with a 523 mA ILIM (a shorted servo lead can't crash board +5V) |

**ESC leads use SIG + GND only** (leave their BEC red wire off the +5V row). The
PL drives the 8 PWM (bank-33) + `ESC_BUF_OE_N` (bank-13) on contract pins verified
free (XDC "unclaimed"); renames in `som_conn_gen.FUNCTION_MAP`.

**Series-damping 33 R — TOOL-BLOCKED, NOT a sourcing defer (LAW 7).** Per-channel
33 R series damping on the 8 buffered outputs (EMI / DShot edge integrity into the
off-board leads) is the RIGHT design and the part **is sourced** (4×33R array
`C25508`, in the catalog). It is NOT in the v1 netlist for one reason: two 4-R
arrays reconverging on the 24-pin header form a *tree* the per-sheet placer's
chain template spreads to ~982 mm. The correct landing is a **single 8-element
33 R array** (one part, a clean fan — no reconverge) OR a placer wrap fix; the
8-array LCSC needs the EasyEDA search API, which was returning CloudFront errors
at authoring time. Tracked to instantiate, not abandoned.

**Deferred (sourced follow-up, not guessed):** a **5 V-rated** ESD array on the
outputs — the spec's PESD3V3L4UG is 3.3 V-working and would clamp the 5 V PWM, so
it is deliberately not used (needs an API-verified 5 V-rated array).
