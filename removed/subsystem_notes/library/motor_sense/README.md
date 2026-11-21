# motor_sense — ESC motor-rail telemetry + in-line current sense

The telemetry half of the carrier's generic motor interface (the 8-channel PWM
output half is `motor_pwm`). It is a reusable in-line power-sense pass-through:
the ESC battery / bench supply enters and exits the carrier through XT60
connectors, passing across an on-board shunt that an INA3221 meters for current
and bus voltage. All flight hardware — ESCs, props, battery — is off board.

## Interface

Carrier-local subsystem; it drives these nets/rails on the Zynq-7000 SoM carrier.

- **`ESC_VRAIL_IN`** — motor-power input node (J2 `+`), shunt high side, TVS-clamped.
- **`ESC_VRAIL`** — post-shunt load-side rail (J3 `+` → off-board ESCs), bus-V sense node.
- **`+3V3_SC`** — always-on SC management rail powering U2 and its pull-ups (draws ~2 mA).
- **`GND`** — shared with logic; the only galvanic tie between the motor rail and logic.
- **`STM32_I2C2_SDA` / `STM32_I2C2_SCL`** — INA3221 on the always-on STM32_I2C2 SC bus
  at address **0x42** (0x40/0x41 are `power_mon`). Expects `som_j1_connector`.
- **`ESC_FAULT_N`** — open-drain INA3221 CRITICAL over-current alert routed to a free
  PL pin on the SoM connector (bank 13, `IO_L1_N_13`). Expects `som_j2_connector`.

## Design

**In-line power path.** The ESC battery / bench supply enters at J2 (XT60PW-M, male
horizontal PCB-mount), passes through RS1 (10 mΩ shunt), and exits at J3 (XT60PW-M)
to the off-board ESCs. XT60 is the RC-bench convention, rated far above the demo
current. Both connectors tie `+` to the rail and `-` plus both mounting tabs to GND.

**Telemetry.** U2 (INA3221AIRGVR, 3-channel) reads current across RS1 and bus voltage
at the load side on a single channel: `IN+1` = shunt high side (`ESC_VRAIL_IN`),
`IN-1` = shunt low side / bus-V sense (`ESC_VRAIL`). The two unused channels are tied
to GND. A0 is strapped to SDA, selecting I2C address 0x42 per the datasheet address
table. The part runs on the always-on `+3V3_SC` rail (VS and VPU), so telemetry is
available regardless of PS/PL state.

**Over-current alert.** The INA3221 `CRITICAL` open-drain output drives `ESC_FAULT_N`,
a fast over-current event back to the PL for shutdown. It has a 10 k pull-up to
`+3V3_SC`. `WARNING`, `PV`, and `TC` are I2C-readable but left as NC.

**Rail bound.** The INA3221 common-mode abs-max is 26 V and D1 (SMBJ28A TVS) clamps
above that, so the protection bound is the battery, not the TVS: the ESC rail is held
≤ 4S (≤ ~20 V) for margin. D1 plus the 100 n HF bypass and the ≤ 4S bound cover the
hot-plug edge into IN+1; a current-limited bench supply, not a hot-plugged charged
pack, keeps transients out of the monitor.

**Load-side bulk.** Cb (470 µF / 35 V polarised electrolytic) sits on `ESC_VRAIL`
(post-shunt, by J3 → ESCs): local energy store for the ESC commutation-current pulses
and it stabilises the bus-V node the INA3221 meters. The 35 V rating gives > 1.5×
margin over the ≤ 4S rail; it seats on a stock D10 SMD electrolytic land pattern. It
sits on the lighter post-shunt net rather than the dense input trunk.

**Safety / isolation.** Bench-only, no flight hardware. The dirty motor rail shares
only GND with logic; PL pins never see it. D1 clamps hot-plug / inductive transients
on the ESC bus.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| J2 | XT60PW-M | XT60PW-M (ESC power in) | — |
| J3 | XT60PW-M | XT60PW-M (ESC rail out) | — |
| RS1 | 10mR | RLM12FTCMR010 | — |
| D1 | SMBJ28A | SMBJ28A (TVS) | — |
| U2 | INA3221AIRGVR | INA3221AIRGVR | — |
| C (HF bypass) | 100n | Device:C | C14663 |
| C (decouple ×n) | 100n | Device:C | C14663 |
| C (bulk decouple) | 10u | Device:C | C15850 |
| Cb | 470uF/35V | Device:C_Polarized (CP_Elec_10x10.5) | C976030 |
| R (pull-up) | 10k | Device:R | C25804 |

## Build & test

`test_motor_sense.py` covers the subsystem netlist. Run:

```
pytest carrier/subsystems/motor_sense/test_motor_sense.py
```
