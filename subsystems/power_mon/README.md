# power_mon — 2x INA3221 rail telemetry (+VIN, +5V, +3V3, +1V8)

Rail current and bus-voltage monitoring for the four carrier supply rails. Two TI
INA3221 triple monitors sit on the always-on management I2C bus and each measure
the drop across a series sense shunt inserted in its rail. This is a
carrier-LOCAL subsystem: it wires the carrier's real net names directly and
exposes no abstract bind contract.

## Interface

`power_mon` drives carrier nets directly (no `META` bind). It exposes two ports
onto the shared `STM32_I2C2` bus and one alert port:

- `STM32_I2C2_SDA` / `STM32_I2C2_SCL` — 400 kHz I2C to the STM32 management MCU,
  `bus="STM32_I2C2"`, `expect=som_j1_connector`. Both ICs share this bus at
  addresses 0x40 and 0x41. No pull-ups here — `usb_pd` / `bringup` own the bus
  pulls.
- `PMON_ALERT_N` — wire-OR of both `CRITICAL` open-drain outputs plus the `R1`
  pull-up, `expect=bringup (TCA9535 spare port P11)`.

The rail nets enter/exit on the shunt pads: `+VIN`/`+VIN_SYS`, `+5V_REG`/`+5V`,
`+3V3_REG`/`+3V3`, `+1V8_REG`/`+1V8`. Supply is `+3V3_SC`; ground is `GND`. The
`_REG`/`+VIN_SYS` (source-side) net testpoints are waived — probe across the
shunt, since the post-shunt board rail carries the testpoint.

## Design

- **Monitor selection.** Two `INA3221AIRGVR` triple high-side I2C
  current/bus-voltage monitors cover four rails (3 channels each, 5 used). The
  INA3221 measures shunt drop and bus voltage per channel with an I2C interface
  and integrated alert comparators.
- **Address map.** `U1.A0 -> GND` gives 0x40; `U2.A0 -> +3V3_SC` gives 0x41. This
  fits the carrier address map alongside 0x20 TCA9535 and 0x22 FUSB302B with no
  collision.
- **Channel assignment.** U1 monitors +VIN (ch1), +5V (ch2), +3V3 (ch3); U2
  monitors +1V8 (ch1). U2's ch2/ch3 are unused, with `IN+/IN-` tied to GND per
  the datasheet so they read 0 V / 0 A.
- **Series shunts / rail split.** Each rail splits at its shunt so a channel reads
  only its own rail's loads. `power.py` / `power_som.py` place each regulator's
  OUTPUT cluster on the `_REG` net (and the buck INPUTs on `+VIN_SYS`); the
  board-facing rail lives on the load side, with the shunt in series between them:

  | shunt | source side (IN+) | load side (IN-) | value |
  |-------|-------------------|-----------------|-------|
  | RS1 | `+VIN` (PD entry, usb_pd sense) | `+VIN_SYS` (buck inputs) | 10 mR |
  | RS2 | `+5V_REG` (buck-1 output cluster) | `+5V` (board rail) | 10 mR |
  | RS3 | `+3V3_REG` (buck-2 output cluster) | `+3V3` (board rail) | 10 mR |
  | RS4 | `+1V8_REG` (LDO output cluster) | `+1V8` (board rail) | 20 mR |

- **Shunt sizing.** The three 3 A nets use 10 mR 1206 (30 mV @ 3 A, ~4 mA LSB);
  the 600 mA +1V8 rail uses 20 mR (12 mV @ 600 mA, ~2 mA LSB).
- **Always-on supply.** Both ICs run from `+3V3_SC` (the always-on SoM SC rail) so
  telemetry works with every monitored rail down. `VS` + `VPU` tie to `+3V3_SC`;
  `GND` + the exposed `PAD` tie to GND. Decoupling: 100n per IC (`C1`/`C2`) plus a
  shared 10u bulk (`C3`).
- **Alert.** Both `CRITICAL` open-drain pins wire-OR into `PMON_ALERT_N`, held
  defined-high by `R1` (10k to `+3V3_SC`), routed to the bringup expander's spare
  port P11. `WARNING` / `PV` / `TC` stay I2C-readable and are no-connects.
- **Common-mode headroom.** The +VIN channel sense pins (IN+1 on `+VIN`, IN-1 on
  `+VIN_SYS`) keep ~3 V margin to the INA3221 26 V common-mode abs-max at the
  eFuse OVP-trip corner (+VIN can reach ~23.06 V before cutoff). This margin is
  coupled to the pd_input eFuse OVP setpoint — widening that trip must re-check
  the 26 V common-mode limit.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1 | — | `INA3221AIRGVR` (0x40, A0=GND) | — |
| U2 | — | `INA3221AIRGVR` (0x41, A0=VS) | — |
| RS1 | 10mR | `RLM12FTCMR010` | — |
| RS2 | 10mR | `RLM12FTCMR010` | — |
| RS3 | 10mR | `RLM12FTCMR010` | — |
| RS4 | 20mR | `RLM12FTCMR020` | — |
| C1 | 100n | `Device:C` (0603) | C14663 |
| C2 | 100n | `Device:C` (0603) | C14663 |
| C3 | 10u | `Device:C` (0805) | C15850 |
| R1 | 10k | `Device:R` (0603) | C25804 |

U1/U2 and RS1–RS4 are placed via `use_part` and draw their LCSC from the part
library; values shown are those set in `power_mon.py`.

## Build & test

`test_power_mon.py` is an offline electrical-correctness check (model
completeness, decap/EP slice, ratings, shunt invariants, address-strap/alert map,
SPICE-passive match).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/power_mon/test_power_mon.py -q
```
