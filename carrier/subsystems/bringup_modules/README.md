# bringup_modules — per-module power gates + status/user LEDs

Stage-3 bring-up power gating for the Zynq-7000 SoM carrier: every module is
individually power-gated through its own `SY6280AAC` load switch with a
programmable current limit, so a shorted module folds back at its own limit
instead of dragging the source rail down for everything else. Each gated output
carries a status LED, making a faulting module visible by eye. This is a
carrier-local subsystem and uses real carrier net names directly (no abstract
`bind` map).

## Interface

The sheet consumes the un-gated source rails `+3V3` and `+5V` and `GND`, and
publishes ten gated POWER rails that the module sheets consume by name:

| gated rail | consumer |
|------------|----------|
| `+3V3_HDMI_TX`, `+3V3_HDMI_RX`, `+3V3_LCD`, `+3V3_CAM`, `+3V3_SD`, `+3V3_PMOD`, `+3V3_USER_LED`, `+5V_USB`, `+5V_HDMI_TX`, `+5V_LCD` | `hdmi_tx`, `hdmi_rx`, `lcd`, camera, microSD, `pmod`, `user_io`, USB VBUS, HDMI TX 5 V, LCD backlight 5 V |

Ten `EN_<module>` ports drive the switch enables; their source is
`bringup_en` (the EN AND-gate cells), resolved at board level. Local SIGNAL
nodes `BU_ISET_<module>` (ISET divider) and `BU_PG_<module>` (status-LED anode
side) stay on-sheet.

## Design

**Load switch.** `SY6280AAC` (SOT-23-5; pinout 1=OUT, 2=GND, 3=ISET, 4=EN,
5=IN) gives constant-current foldback, over-temperature protection, and reverse
blocking. The current limit is programmed by `RSET` from ISET to GND:
`ILIM = 6800 / RSET`. RSET values stay on verified JLC-Basic E-series points:
13k → 523 mA, 6.8k → 1.0 A.

**Per-module gates (10).** Eight gate the primary module rails; two gate the
5 V module rails (`+5V_HDMI_TX`, `+5V_LCD`) from `+5V`, so those rails are
sourced and protected exactly like every other module rail.

| # | module | IN | OUT (gated rail) | RSET | LCSC | limit | LED R |
|---|--------|----|------------------|------|------|-------|-------|
| 1 | HDMI TX    | `+3V3` | `+3V3_HDMI_TX`  | 13k  | C22797 | 523 mA | 330R |
| 2 | HDMI RX    | `+3V3` | `+3V3_HDMI_RX`  | 13k  | C22797 | 523 mA | 330R |
| 3 | LCD        | `+3V3` | `+3V3_LCD`      | 6.8k | C23212 | 1.0 A  | 330R |
| 4 | Camera     | `+3V3` | `+3V3_CAM`      | 13k  | C22797 | 523 mA | 330R |
| 5 | microSD    | `+3V3` | `+3V3_SD`       | 6.8k | C23212 | 1.0 A  | 330R |
| 6 | USB VBUS   | `+5V`  | `+5V_USB`       | 6.8k | C23212 | 1.0 A  | 1k   |
| 7 | PMOD       | `+3V3` | `+3V3_PMOD`     | 13k  | C22797 | 523 mA | 330R |
| 8 | User LEDs  | `+3V3` | `+3V3_USER_LED` | 13k  | C22797 | 523 mA | 330R |
| 9 | HDMI TX 5V | `+5V`  | `+5V_HDMI_TX`   | 13k  | C22797 | 523 mA | 1k   |
| 10| LCD BL 5V  | `+5V`  | `+5V_LCD`       | 6.8k | C23212 | 1.0 A  | 1k   |

**ILIM sizing for the 5 V gates.** `+5V_LCD` budgets 450 mA (SY7201 boost input
at the 133 mA LED operating point plus margin) → 6.8k = 1.0 A. `+5V_HDMI_TX`
budgets 55 mA, already hard-limited inside the TPD12S016's 5V_OUT switch; the
SY6280 limit only backstops a board-level fault on the rail trace, so it uses
the smallest verified-Basic RSET point, 13k = 523 mA.

**Enable.** Each `EN_<module>` is driven push-pull at 3.3 V by its `bringup_en`
AND-cell, so EN never floats.

**Decoupling.** 100 nF on each switch IN and OUT (module subsystems own their
own bulk).

**Status LEDs.** A KT-0603R red LED on each gated output: 330R series on the
3.3 V rails (~3.9 mA), 1k on the 5 V outputs (~3 mA). A faulting module's LED
sags and points at the fault.

**microSD rail bleed.** A 10k bleed (C25804) on `+3V3_SD` to GND discharges the
rail for a clean re-seat, since the SY6280 has no quick-output-discharge and a
card power-cycle re-init needs VDD below ~0.5 V. Only the SD rail has this
power-cycle requirement; 0.33 mA static cannot mis-trip the 1.0 A limit.

**User LEDs.** The user LEDs themselves live on the `user_io` sheet bound to
real bank pins; this sheet only gates their `+3V3_USER_LED` rail via switch #8.

**Bring-up instrumentation.** Each gated output carries a testpoint at the
SY6280 output, so rail-by-rail bring-up can meter on this side of the module
connector. Each gated rail also declares its own status-LED draw to the
power-tree budget (~4 mA on the 3.3 V rails, ~3 mA on the 5 V rails).

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1..U10 | SY6280AAC | `SY6280AAC` (parts lib, SOT-23-5) | — |
| RSET (per gate) | 13k / 6.8k | `Device:R` 0603 | C22797 / C23212 |
| LED series R | 330R / 1k | `Device:R` 0603 | C23138 / C21190 |
| SD bleed | 10k | `Device:R` 0603 | C25804 |
| D (per gate) | red | `Device:LED` 0603 (KT-0603R) | C2286 |
| C (IN + OUT per gate) | 100n | `Device:C` 0603 | C14663 |

## Build & test

`test_bringup_modules.py` runs offline: model completeness, the design-rules
slice, part/spice slices, and the sheet invariants (10 SY6280 switches, the 10
gated POWER rails, the RSET set, status LEDs and their series R, the per-rail
testpoints, the power-draw notes).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_modules/test_bringup_modules.py -q
```
