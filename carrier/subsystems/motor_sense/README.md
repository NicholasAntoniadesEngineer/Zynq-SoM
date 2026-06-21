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
| load-side bulk | `Cb` 470 µF / 35 V (`C976030`) | local ESC commutation bulk **and** stabilises the bus-V node the INA meters, on `ESC_VRAIL` (post-shunt, by J3 → ESCs) |

**Rail bounds — BOTH voltage AND current (Phase-3 review):**
- **Voltage ≤ 4S (≤ ~20 V).** The INA3221 common-mode abs-max is 26 V; the SMBJ28A
  (31 V VBR, 45 V clamp) does NOT protect those 26 V pins, so the bound is the
  battery, not the TVS. **Pre-power / soft-start the rail — do not hot-plug a
  charged pack** (the sub-µs LC ring overshoots ~2×; a current-limited supply's
  kHz loop can't damp it). The input TVS (`D1`) + the 100 n + the ≤ 4S bound cover
  that edge into the INA's IN+1; the bulk `Cb` sits on the load-side `ESC_VRAIL`
  (post-shunt), so it backs the ESCs + steadies IN-1, not the input node.
- **Current ≤ ~7 A continuous.** `RS1` is a **1 W** 10 mΩ shunt → thermal limit
  ≈ √(1/0.01) = 10 A, 50 %-derated ≈ 7 A — well below the XT60's 60 A. **Do not
  exceed ~7 A through the rail** with this shunt. (The INA3221 ADC saturates at
  163.8 mV/10 mΩ = 16.4 A, also above the shunt's safe point — the 1 W shunt is
  the weakest link.)

**Safety:** the dirty motor rail shares only **GND** with logic; PL pins never see
it (the buffer's 5 V B-side absorbs any ESC-side fault).

**Implemented (no EasyEDA fetch — stock KiCad footprint, verified LCSC in the BOM):**
- the **bulk cap** `Cb` = 470 µF / 35 V (`C976030`, `Device:C_Polarized` +
  `Capacitor_SMD:CP_Elec_10x10.5`) on the **load-side** `ESC_VRAIL`. It went there
  (not `ESC_VRAIL_IN`) because that is the conventional ESC-bulk node and it
  steadies the INA's bus-V (IN-1) reading, while the dense `ESC_VRAIL_IN` trunk was
  at the schematic router's per-net pin budget.

**Open (a design decision, NOT just sourcing):**
- a **higher-current shunt path.** `RS1` carries the **aggregate** ESC current
  (8 × ~5 A ≈ 40 A). At 40 A a 10 mΩ shunt is 0.4 V (over the INA's ±163 mV range)
  and 16 W — so lifting the ceiling means a *value* change (≈ 2 mΩ, e.g. 2–3 W 2512
  `C494555`) **and** an INA-scale/firmware change, plus an optional series fuse.
  The present 10 mΩ / 1 W is correct for the ≤ ~10 A low-current bench demo.
