# board_aux — manually-gated +3V3_AUX rail + PCA9306 I2C isolator

board_aux is the infrastructure half of the carrier's board-services block: it
makes a manually-enabled, default-OFF `+3V3_AUX` rail and bridges the always-on
STM32 management I2C onto that gated segment. The peripherals it powers live on
`board_services`; the QWIIC connector that re-exports the rail and bus lives on
`board_qwiic`. It is a carrier-LOCAL subsystem — real carrier net names are wired
directly, with no abstract-interface `META` bind contract.

## Interface

Carrier nets driven and ports published:

- **Input rail:** `+3V3` (always-on) into the load switch.
- **Gated rail:** `+3V3_AUX` — the switched output, default-OFF until SW1 is
  flipped. Published with `testpoint("+3V3_AUX")` and a 6 mA load declared to the
  power tree (status LED + the two 4k7 AUX-bus pull-ups).
- **Management bus ports (always-on side):** `STM32_I2C2_SCL` / `STM32_I2C2_SDA`,
  typed i2c (scl/sda, 400 kHz, bus `STM32_I2C2`), expecting bringup_rails /
  usb_pd / power_mon.
- **Isolated bus ports (gated side):** `AUX_I2C_SCL` / `AUX_I2C_SDA`, typed i2c
  (scl/sda, 400 kHz, bus `AUX_I2C`), consumed by board_services / board_qwiic.
  Both have testpoints.

A project consumes board_aux by wiring `board_services` / `board_qwiic` to the
`AUX_I2C_*` ports and feeding the always-on `STM32_I2C2_*` ports from the
management bus; the `+3V3` / `+3V3_SC` / `GND` rails are shared carrier nets.

## Design

**Manual power gate (U1, SY6280AAC).** A current-limited load switch gates `+3V3`
→ `+3V3_AUX`, matching the bring-up module switches. ILIM is set by R1 = 13k on
ISET: ILIM = 6800/13k ≈ 523 mA, sized above the gated load. The enable is LOCAL
and defaults OFF: DIP switch SW1 (DSHP04, position 1) closes `+3V3` onto
`EN_AUX`, and R2 = 100k holds `EN_AUX` low until a human flips the switch, so the
rail comes up de-energized at power-on. SW1 positions 2–4 are spare (commons
bused to `+3V3`, even pins NC). Keeping the gate self-contained on this sheet
makes the whole block a single add/revert that touches none of the dense
rail-control sheets, and keeps each sheet below the placer's congestion threshold.

**Bypass + bulk.** 100n on U1.IN and U1.OUT. A 10u 0805 bulk cap holds up
`+3V3_AUX` for the ~200 mA QWIIC load; the SY6280 datasheet recommends an output
cap and its soft-start tolerates the 10u.

**Status LED.** A red LED on the gated output through R3 = 330R lights when the
AUX rail is enabled, making the manual gate state visible at a glance.

**I2C isolator (U2, PCA9306DCUR).** The board_services peripherals run off the
gated rail but their bus is the always-on `STM32_I2C2`. Tying gated SDA/SCL
straight to that pulled-up bus would back-power the unpowered chips through their
ESD diodes (LAW 0). The PCA9306 bidirectional level/isolation switch bridges the
two domains. The reference asymmetry IS the isolation: VREF1 references `+3V3_SC`
(always-on side — its pull-ups already live on bringup_rails), VREF2 references
the gated `+3V3_AUX` with its own 4k7 pull-ups (R5/R6, required on both sides of
the PCA9306). U2.EN is pulled to `+3V3_AUX` through R4 = 100k, so the switch
OPENS whenever the AUX rail is down — the peripherals are cleanly isolated while
off. 100n bypass on each VREF.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1  | SY6280AAC | parts: `SY6280AAC` | — |
| U2  | PCA9306DCUR | parts: `PCA9306DCUR` | — |
| SW1 | DSHP04TSGER | parts: `DSHP04TSGER` | — |
| D   | red | `Device:LED` | C2286 |
| C (×4) | 100n | `Device:C` | C14663 |
| C   | 10u | `Device:C` (0805) | C15850 |
| R (ISET) | 13k | `Device:R` | C22797 |
| R (EN pulldown) | 100k | `Device:R` | C25803 |
| R (LED) | 330R | `Device:R` | C23138 |
| R (PCA9306 EN pull-up) | 100k | `Device:R` | C25803 |
| R (×2 AUX bus pull-ups) | 4k7 | `Device:R` | C23162 |

Refdes for the `Device:*` parts are auto-assigned; the netlist topology is the
authority. Three testpoints sit on `+3V3_AUX`, `AUX_I2C_SCL`, `AUX_I2C_SDA`.

## Build & test

`test_board_aux.py` checks model completeness, the decap/strap slice, ratings,
the SPICE-passive match, and the gate/isolation invariants (VREF1 = +3V3_SC,
VREF2 = +3V3_AUX, EN pulled to the gated rail).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/board_aux/test_board_aux.py -q
```
