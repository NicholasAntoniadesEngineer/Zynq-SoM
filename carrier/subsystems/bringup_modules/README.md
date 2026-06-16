# bringup_modules — per-module power gates + status LEDs (carrier-local subsystem)

The stage-3 bring-up power gates: **every module is individually power-gated**
so a fault is isolated by eye. One `SY6280AAC` load switch per module with a
**programmable current limit** (ILIM = 6800 / RSET; constant-current foldback,
OTP, reverse blocking) plus a per-module status LED on the gated output
(`carrier/research/bringup_power_gating.md` sections 3.2/3.3/3.4).

A shorted module folds back at *its own* limit instead of dragging `+3V3` down
for everything else, and that one module's status LED sags and points at the
fault.

This is a **carrier-local** subsystem (real carrier net names, no abstract
interface / `bind` map); it is folded into a per-name package only for
4-artifact parity with the generic `subsystems/<name>/` library.

## Switch table (10 gates)

SY6280AAC pinout (SOT-23-5, Silergy DS): 1=OUT 2=GND 3=ISET 4=EN 5=IN.
RSET on verified JLC-Basic E-series values; rows 9–10 are the round-5 5 V
gates (sourcing the previously-unsourced `+5V_HDMI_TX` / `+5V_LCD` rails).

| # | module | IN rail | OUT (gated rail) | RSET | LCSC | limit | LED R |
|---|--------|---------|------------------|------|------|-------|-------|
| 1 | HDMI TX    | `+3V3` | `+3V3_HDMI_TX`    | 13k  | C22797 | 523 mA | 330R |
| 2 | HDMI RX    | `+3V3` | `+3V3_HDMI_RX`    | 13k  | C22797 | 523 mA | 330R |
| 3 | LCD        | `+3V3` | `+3V3_LCD`        | 6.8k | C23212 | 1.0 A  | 330R |
| 4 | Camera     | `+3V3` | `+3V3_CAM`        | 13k  | C22797 | 523 mA | 330R |
| 5 | microSD    | `+3V3` | `+3V3_SD`         | 6.8k | C23212 | 1.0 A  | 330R |
| 6 | USB VBUS   | `+5V`  | `+5V_USB`         | 6.8k | C23212 | 1.0 A  | 1k   |
| 7 | PMOD       | `+3V3` | `+3V3_PMOD`       | 13k  | C22797 | 523 mA | 330R |
| 8 | User LEDs  | `+3V3` | `+3V3_USER_LED`   | 13k  | C22797 | 523 mA | 330R |
| 9 | HDMI TX 5V | `+5V`  | `+5V_HDMI_TX`     | 13k  | C22797 | 523 mA | 1k   |
| 10| LCD BL 5V  | `+5V`  | `+5V_LCD`         | 6.8k | C23212 | 1.0 A  | 1k   |

Each `EN_<module>` comes from its `bringup_en_modules` AND-cell (push-pull
3.3 V — EN never floats). **100 nF on each switch IN and OUT**; module
subsystems own their own bulk. ISET → RSET → GND sets the foldback limit.

Per-module **status LED** (KT-0603R red, C2286) on the gated output: 330R on
the 3V3 rails (~3.9 mA), 1k on the 5 V outputs (~3 mA). Net `BU_PG_<module>` is
the LED-anode-side node; `BU_ISET_<module>` is the ISET divider node.

## Rails / nets

| net | role |
|-----|------|
| `+3V3`, `+5V` | POWER (IN) — the un-gated source rails. |
| `+3V3_HDMI_TX`, `+3V3_HDMI_RX`, `+3V3_LCD`, `+3V3_CAM`, `+3V3_SD`, `+3V3_PMOD`, `+3V3_USER_LED`, `+5V_USB`, `+5V_HDMI_TX`, `+5V_LCD` | POWER (OUT) — the gated per-module rails consumed by name on the module sheets (`hdmi_tx`, `hdmi_rx`, `lcd`, …). |
| `GND` | GROUND. |
| `EN_<module>` (10) | PORT — the enables from `bringup_en_modules`. |
| `BU_ISET_<module>`, `BU_PG_<module>` | SIGNAL — local ISET/LED nodes. |

(The user LEDs themselves live on `user_io`, bound to real bank pins; this
sheet only **gates** their `+3V3_USER_LED` rail via switch #8.)

## Parts

| ref | value | part | LCSC |
|-----|-------|------|------|
| U1..U10 | SY6280AAC | `parts/SY6280AAC/` (SOT-23-5) | (parts lib) |
| RSET | 13k / 6.8k | `Device:R` 0603 | C22797 / C23212 |
| LED R | 330R / 1k | `Device:R` 0603 | C23138 / C21190 |
| D | red | `Device:LED` 0603 (KT-0603R) | C2286 |
| C | 100n | `Device:C` 0603 (IN + OUT per switch) | C14663 |

Every gated rail carries a **testpoint** at its SY6280 output (rail-by-rail
bring-up needs the meter on this side of the module connector). Power-tree
budget: the per-rail status-LED draw (~4 mA on 3V3, ~3 mA on 5 V).

## Local test vs board gates

`test_bringup_modules.py` runs offline: model completeness, the design_rules
slice, part/spice slices, and the gate invariants this sheet owns (10 SY6280
switches, the 10 gated POWER rails, the RSET set {13k, 6.8k}, the status LEDs
and their series R, the per-rail testpoints, the power-draw notes). The
cross-board EN-source link and the module consumers stay at board level
(`schgen board`).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_modules/test_bringup_modules.py -q
```
