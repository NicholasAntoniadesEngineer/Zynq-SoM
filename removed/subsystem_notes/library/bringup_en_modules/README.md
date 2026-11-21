# bringup_en_modules — module EN AND-cells (DIP-AND-software-override)

The eleven per-module enable cells of the staged bring-up power-gating scheme on
the Zynq-7000 SoM carrier. Each cell is a uniform `SN74LVC1G08` 2-input AND gate
that combines a DIP switch position (`A`) with a software override input (`B`) to
drive one module enable (`Y`), implementing the "DIP is master, software is a
veto" contract. This is a carrier-local subsystem: it uses real carrier net names
and has no abstract `bind` map.

## Interface

Carrier-local — drives concrete carrier nets, no abstract ports/bind map:

- `+3V3_SC` (POWER, in) — always-on SoM SC rail; gate `VCC` and every non-spare
  `B` 100k pull-up tie here. Alive from default VBUS before USB-PD negotiation.
- `GND` (GROUND) — gate GND (pin 3) and every `A` 100k pulldown bottom.
- `BU_DIP_*` (in, from `bringup_rails` DIP switches) — the `A` master inputs.
- `BU_OVR_*` (in, from `bringup_rails` TCA9535 expander ports) — the `B` override
  inputs.
- `EN_*` (out, 11 nets) — 3.3 V CMOS push-pull active-high enables; ten bind to the
  `bringup_modules` SY6280 load-switch EN pins, one (`EN_LCD_BL`) is a reserved hook.

Every `EN_*` net carries a testpoint so each enable is probeable on the bench.

## Design

**DIP-AND-software, not OR.** Each cell ANDs a DIP position (`A`) with a software
override (`B`). The DIP is the master and software can only veto (force-OFF): a
module turns on only when its DIP is closed AND software has not pulled `B` low.
At power-on-reset the TCA9535 expander ports are inputs, so the `B` 100k pull-up
to `+3V3_SC` holds `B = 1` and stage-1 bring-up works on the switches alone.
Software can never force a probe-shorted module ON behind a human.

**Gate part.** `SN74LVC1G08DBVR` (single 2-input AND, SOT-23-5; pinout 1=A, 2=B,
3=GND, 4=Y, 5=VCC). Inputs are 5.5 V tolerant; the output is 32 mA rail-to-rail
push-pull, driving any regulator or load-switch EN pin directly. `VCC = +3V3_SC`
so the cells are alive on the default rail before PD. One 100 nF decoupling cap
per gate.

**Per-cell pulls.** Each `A` input carries a 100k pulldown to `GND`, so an open
DIP reads as 0 (module OFF) and a closed DIP as 1. Each `B` input (except the
spare) carries a 100k pull-up to `+3V3_SC` so a Hi-Z override reads as 1 (no
veto). Both pulls live here at the gate so every cell is electrically complete on
this sheet.

**Cell map.** Ten cells drive module enables; one is a reserved spare:

| cell | A (DIP) | B (override) | Y (enable) | B pull-up |
|------|---------|--------------|------------|-----------|
| HDMI_TX    | `BU_DIP_HDMI_TX`    | `BU_OVR_HDMI_TX`    | `EN_HDMI_TX`    | 100k ↑ |
| HDMI_RX    | `BU_DIP_HDMI_RX`    | `BU_OVR_HDMI_RX`    | `EN_HDMI_RX`    | 100k ↑ |
| LCD        | `BU_DIP_LCD`        | `BU_OVR_LCD`        | `EN_LCD`        | 100k ↑ |
| CAM        | `BU_DIP_CAM`        | `BU_OVR_CAM`        | `EN_CAM`        | 100k ↑ |
| SD         | `BU_DIP_SD`         | `BU_OVR_SD`         | `EN_SD`         | 100k ↑ |
| USB        | `BU_DIP_USB`        | `BU_OVR_USB`        | `EN_USB`        | 100k ↑ |
| PMOD       | `BU_DIP_PMOD`       | `BU_OVR_PMOD`       | `EN_PMOD`       | 100k ↑ |
| USER_LED   | `BU_DIP_USER_LED`   | `BU_OVR_USER_LED`   | `EN_USER_LED`   | 100k ↑ |
| LCD_BL (spare) | `BU_DIP_SPARE`  | `BU_OVR_LCD_BL`     | `EN_LCD_BL`     | none |
| HDMI_TX_5V | `BU_DIP_HDMI_TX_5V` | `BU_OVR_HDMI_TX_5V` | `EN_HDMI_TX_5V` | 100k ↑ |
| LCD_5V     | `BU_DIP_LCD_5V`     | `BU_OVR_LCD_5V`     | `EN_LCD_5V`     | 100k ↑ |

**Spare cell (EN_LCD_BL).** A reserved gated-EN hook whose output lands on a
testpoint only — it has no consumer subsystem. The LCD backlight is enabled and
dimmed directly by STM32 PWM into the SY7201 EN/PWM pin; that PWM must NOT pass
through this DIP-AND gate, which would chop it. The hook is available for a future
non-PWM backlight enable. This is the one cell with no `B` pull-up here: its `B`
(TCA9535 P10) carries a 100k pull-down on `bringup_rails`, so `EN_LCD_BL` defaults
OFF until software raises P10.

**5 V module gates.** `HDMI_TX_5V` and `LCD_5V` take `A` from the `bringup_rails`
SW6 DIP positions 1/2 and `B` from TCA9535 ports P12/P13 — the same uniform cell.

Static load on `+3V3_SC` is budgeted at 5 mA (11 LVC gates plus the 100k pull
networks).

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1..U11 | SN74LVC1G08 | `74xGxx:74LVC1G08` (SOT-23-5) | C7666 |
| R (A pulldowns, 11) | 100k | `Device:R` 0603 | C25803 |
| R (B pull-ups, 10) | 100k | `Device:R` 0603 | C25803 |
| C (one per gate VCC) | 100n | `Device:C` 0603 | C14663 |

## Build & test

`test_bringup_en_modules.py` runs offline: model completeness, the `design_rules`
DECAP/STRAP/EP slice, part/spice slices, and the cell invariants this sheet owns
(the 11 EN nets, the per-cell 100k pulldown, the 10 B pull-ups plus the one spare
with no pull-up, the testpoints). The cross-board EN→SY6280 link is checked at
board level.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_en_modules/test_bringup_en_modules.py -q
```
