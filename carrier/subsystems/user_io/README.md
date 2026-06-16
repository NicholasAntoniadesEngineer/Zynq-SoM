# user_io — 4 user LEDs (gated rail) + 4 user buttons, PL bank 13 (carrier-local)

A **carrier-local** schgen subsystem: 4 user LEDs and 4 user buttons on the
Zynq PL bank-13 IOs exposed by SoM connector **J2**. Unlike a generic
`subsystems/<name>/` library package, this one is **board-specific** — it binds
verbatim `IO_*_13` net names from `carrier/som_interface.json` and rides the
carrier rail tree directly, so there is no abstract-interface / bind contract.

## Package contents

| file | role |
|------|------|
| `user_io.py`      | the NETLIST — `circuit()`, carrier nets |
| `user_io.cir`     | SPICE subckt — the LED series-R + button pull-up passives, PL pins + rails as subckt pins |
| `test_user_io.py` | LOCAL electrical-correctness test (offline; model completeness + decoupling slice + per-color LED-R + button-pull invariants) |
| `README.md`       | this file |

## Purpose

LEDs are **active-low sinks on a bring-up-gated rail** (PLAN stage 2 "enable
user LEDs"): anode on `+3V3_USER_LED`, cathode through a per-color series
resistor to the PL pin. The rail gate (SY6280 load switch on `bringup_modules`)
kills all four LEDs regardless of fabric state. Buttons are **active-low tacts**
with 10k pull-ups to the **ungated** `+3V3`, so a held button reads correctly
whenever PL is alive — even while the LED rail is off during bring-up stage 2.

## Parts

| ref | value | part / footprint | LCSC | role |
|-----|-------|------------------|------|------|
| D1 | red   | `Device:LED` / LED_0603 | C2286  | LED1 (Basic) |
| D2 | green | `Device:LED` / LED_0603 | C12624 | LED2 (Extended) |
| D3 | blue  | `Device:LED` / LED_0603 | C2288  | LED3 (Extended) |
| D4 | white | `Device:LED` / LED_0603 | C2290  | LED4 (Basic) |
| R1 | 1k    | `Device:R` / R_0603 | C21190 | red series (~1.3 mA) |
| R2-R4 | 200R | `Device:R` / R_0603 | C8218 | green/blue/white series (high-Vf colors) |
| R5-R8 | 10k | `Device:R` / R_0603 | C25804 | button pull-ups to +3V3 |
| SW1-SW4 | USER | `TS-1187A-B-A-B` (use_part) | C318884 | tact switches (Basic) |
| C1 | 100n  | `Device:C` / C0603 | C14663 | +3V3_USER_LED rail bypass |

**Per-color series R (audit io_misc-1):** the rail is only 3.3 V, so the three
high-Vf colors (green/blue/white, Vf ~3.1 V) would draw only ~0.2 mA on a 1k
(invisible). They use **200R** (~1-3.5 mA, always under the 5 mA LED rating at
every Vf corner); **red** (Vf ~1.8-2.4 V) keeps **1k** (~1.3 mA). The "0603
distinct colors, all-Basic" ask is live-verified INFEASIBLE (Basic 0603 =
red/white only), so red+white are Basic, green+blue Extended, one footprint.

## Interface (carrier nets — LED / button map)

### Rails

| net | class | meaning |
|-----|-------|---------|
| `+3V3_USER_LED` | POWER | bring-up-gated module rail (stage 2); all 4 LED anodes + C1 |
| `+3V3` | POWER | ungated VCCO_13-level rail; the 4 button pull-ups |
| `GND` | GROUND | ground (button contacts 3/4, C1.2) |

### LED / button → PL pin map (verbatim `som_interface.json`, J2 pins)

| ref | function | PL net (port) | J2 pin | series R |
|-----|----------|---------------|--------|----------|
| D1/R1 | LED1 red | `IO_25_13`     | 23 | 1k (red) |
| D2/R2 | LED2 green | `IO_L6_P_13`  | 21 | 200R |
| D3/R3 | LED3 blue | `IO_L24_P_13`  | 10 | 200R |
| D4/R4 | LED4 white | `IO_L24_N_13` |  7 | 200R |
| SW1/R5 | BTN1 | `IO_L15_P_13` |  9 | 10k pull-up |
| SW2/R6 | BTN2 | `IO_L19_P_13` | 12 | 10k pull-up |
| SW3/R7 | BTN3 | `IO_L21_P_13` | 13 | 10k pull-up |
| SW4/R8 | BTN4 | `IO_L22_P_13` | 19 | 10k pull-up |

All PL pins are emitted as `c.port(..., expect="som_j2_connector")` — they merge
with the J2 bank-13 pins at board link. The internal LED-cathode nodes
(`USER_LEDn_K`) are private SIGNAL nets. Tact contacts 1/2 carry the signal,
3/4 go to GND (TS-1187A contact map).

## Power-tree budget

- `+3V3_USER_LED` 12 mA: red ~1.3 mA (1k) + green/blue/white up to ~3.5 mA each
  (200R, worst-low Vf corner).
- `+3V3` 2 mA: 4× button 10k pull-ups when pressed (~0.33 mA each).

## Notes

- **No RC debounce**: PL debounces in fabric (free), and the SoM-side bank has
  no Schmitt requirement for slow human inputs.
- **Bank-13 oversubscription** (dossier flag, not enacted here): lcd 34 + pmod
  16 + user_io 8 = 58 > 43 bank-13 IOs — the LCD bus must move (proposal: J3
  bank 34) before wave-3 J2 generation. user_io's 8 pins are chosen to spend the
  cheapest pins first (4 singleton P-pins, 1 true singleton, 1 VREF-mate pair, 1
  full plain pair); all clock pairs and L16/L17/L18/L23 stay free (19 free after
  this sheet).

## Local test

`test_user_io.py` runs the subsystem-LOCAL slices offline (model completeness,
the `design_rules` DECAP/EP/STRAP slice, per-color LED series-R, button 10k
pulls to +3V3, the `.cir` ↔ netlist passive match). Cross-board gates (the full
link / power-tree headroom / board ERC) stay aggregated by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/user_io/test_user_io.py -q
```
