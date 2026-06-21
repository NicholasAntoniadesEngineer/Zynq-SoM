# motor_sense — ESC motor-rail telemetry + in-line shunt (carrier-local)

The TELEMETRY half of the carrier's generic motor interface (PWM output is in
`motor_pwm`). A reusable in-line power-sense pass-through — ESCs/props/battery are
all **off board**.

| block | parts | function |
|-------|-------|----------|
| in-line power | `J2`/`J3` XT60 + `RS1` 10 mΩ | battery passes J2 (in) → RS1 → J3 (out) → off-board ESCs |
| telemetry | `U2` INA3221 | current (across RS1) **and** bus voltage (at IN-1) on one channel, `STM32_I2C2` @ **0x42** (0x40/0x41 = power_mon) |
| over-current event | `CRITICAL` → `ESC_FAULT_N` | fast PL alert (open-drain, 10 k pull-up to +3V3_SC) |
| transient clamp | `D1` SMBJ28A | hot-plug / inductive clamp on the ESC bus |

**Rail bounds — BOTH voltage AND current (Phase-3 review):**
- **Voltage ≤ 4S (≤ ~20 V).** The INA3221 common-mode abs-max is 26 V; the SMBJ28A
  (31 V VBR, 45 V clamp) does NOT protect those 26 V pins, so the bound is the
  battery, not the TVS. **Pre-power / soft-start the rail — do not hot-plug a
  charged pack** (the sub-µs LC ring overshoots ~2×; a current-limited supply's
  kHz loop can't damp it). The deferred bulk cap below is what damps it.
- **Current ≤ ~7 A continuous.** `RS1` is a **1 W** 10 mΩ shunt → thermal limit
  ≈ √(1/0.01) = 10 A, 50 %-derated ≈ 7 A — well below the XT60's 60 A. **Do not
  exceed ~7 A through the rail** with this shunt. (The INA3221 ADC saturates at
  163.8 mV/10 mΩ = 16.4 A, also above the shunt's safe point — the 1 W shunt is
  the weakest link.)

**Safety:** the dirty motor rail shares only **GND** with logic; PL pins never see
it (the buffer's 5 V B-side absorbs any ESC-side fault).

**Deferred (sourced follow-up — NOT guessed; EasyEDA search API was down):**
- an electrolytic **bulk cap** (220–470 µF, ≥ 35 V) on `ESC_VRAIL_IN` to damp the
  hot-plug LC ring so the first peak stays under the INA3221's 26 V (the 100 n
  50 V HF bypass + TVS + ≤ 4S + the soft-start note cover v1);
- a **higher-power shunt** (2–3 W 2512 10 mΩ) + a series **fuse/polyfuse** if a
  current ceiling above ~7 A is wanted — to make the XT60 / INA / shunt current
  ranges coherent.
