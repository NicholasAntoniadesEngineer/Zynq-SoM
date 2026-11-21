# user_io — 4 user LEDs (gated rail) + 4 user buttons on PL bank 13

A carrier-local schgen subsystem providing four user-controllable indicator
LEDs and four push-buttons on the Zynq-7000 PL bank-13 IOs exposed through SoM
connector J2. It is board-specific: it binds the verbatim `IO_*_13` net names
from `carrier/som_interface.json` and rides the carrier rail tree directly, so
it has no abstract-port bind contract.

## Interface

The subsystem drives carrier nets directly. PL pins are emitted with
`c.port(net, ..., expect="som_j2_connector")` so they merge with the J2 bank-13
pins at board link.

Rails:

| net | class | role |
|-----|-------|------|
| `+3V3_USER_LED` | POWER | bring-up-gated module rail (SY6280 load switch on `bringup_modules`, stage 2); all 4 LED anodes + C1 |
| `+3V3` | POWER | ungated VCCO_13-level rail; the 4 button pull-ups |
| `GND` | GROUND | button contacts 3/4 and C1 return |

PL pin map (J2 / bank 13):

| ref | function | PL net (port) | J2 pin |
|-----|----------|---------------|--------|
| D1/R1 | LED red | `IO_25_13` | 23 |
| D2/R2 | LED green | `IO_L6_P_13` | 21 |
| D3/R3 | LED blue | `IO_L24_P_13` | 10 |
| D4/R4 | LED white | `IO_L24_N_13` | 7 |
| SW1/R5 | button | `IO_L15_P_13` | 9 |
| SW2/R6 | button | `IO_L19_P_13` | 12 |
| SW3/R7 | button | `IO_L21_P_13` | 13 |
| SW4/R8 | button | `IO_L22_P_13` | 19 |

The LED-cathode nodes (`USER_LED{n}_K`) are private SIGNAL nets internal to the
subsystem. The 8 J2 pins are chosen to spend the cheapest pins first (4
singleton P-pins, 1 true singleton, 1 VREF-mate pair, 1 plain pair), leaving all
clock pairs and L16/L17/L18/L23 free.

## Design

**LEDs are active-low sinks on a gated rail.** Each anode sits on
`+3V3_USER_LED`; the cathode passes through a per-color series resistor to the PL
pin, so the fabric pulls the pin low to light the LED. Because the anode rail is
the bring-up-gated module rail, the rail gate kills all four LEDs regardless of
fabric state during bring-up stage 2.

**Per-color series resistor.** The rail is only 3.3 V, so the drop across the
series R is `(3.3 - Vf)`. Red (Vf ~1.8-2.4 V) has ~1.3 V of headroom and uses
**1k** (~1.3 mA). The three high-Vf colors — green (Vf ~3.1 V), blue (Vf
~3.1 V), white (Vf 2.6-3.1 V) — would draw only ~0.2 mA on a 1k (invisible), so
they use **200R**: ~1 mA at the 3.1 V corner up to ~3.5 mA at the white 2.6 V
corner, always under the 5 mA LED rating at every Vf corner. 3.3 V cannot drive
a 3.1 V LED brightly; 200R is the safe maximum-brightness choice without a 5 V
rail. The four LEDs share one 0603 footprint; red and white are LCSC Basic,
green and blue Extended (distinct-color all-Basic 0603 is not available).

**Buttons are active-low tacts.** Each TS-1187A switch ties contacts 1/2 to the
PL pin and contacts 3/4 to GND, with a 10k pull-up to the **ungated** `+3V3`
(VCCO_13 level). The pull-up rides the ungated rail so a held button reads
correctly whenever PL is alive, even while the LED rail is off during bring-up.
A pressed button shorts the pin to GND. No RC debounce is fitted — debouncing is
done in PL fabric.

**Decoupling.** C1 (100n) bypasses the `+3V3_USER_LED` rail at the LED anodes.

**Power budget.** `+3V3_USER_LED` draws ~12 mA worst case (red ~1.3 mA on 1k
plus three high-Vf colors up to ~3.5 mA each on 200R); `+3V3` draws ~2 mA from
the four 10k button pull-ups when held.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|------------|------|
| D1 | red | `Device:LED` (LED_0603) | C2286 |
| D2 | green | `Device:LED` (LED_0603) | C12624 |
| D3 | blue | `Device:LED` (LED_0603) | C2288 |
| D4 | white | `Device:LED` (LED_0603) | C2290 |
| R1 | 1k | `Device:R` (R_0603) | C21190 |
| R2-R4 | 200R | `Device:R` (R_0603) | C8218 |
| R5-R8 | 10k | `Device:R` (R_0603) | C25804 |
| SW1-SW4 | USER | `TS-1187A-B-A-B` (use_part) | — |
| C1 | 100n | `Device:C` (C_0603) | C14663 |

## Build & test

`test_user_io.py` runs the subsystem-local checks offline (model completeness,
the DECAP/EP/STRAP design-rule slice, per-color LED series-R, button 10k pulls to
`+3V3`, and the `.cir` ↔ netlist passive match).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/user_io/test_user_io.py -q
```
