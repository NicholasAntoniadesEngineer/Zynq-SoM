# bringup_en_modules — module EN AND-cells (carrier-local subsystem)

The eleven **module** enable cells of the staged bring-up power-gating scheme:
the same uniform `SN74LVC1G08` 2-input AND gate as `bringup_en`, one per gated
module, implementing the "**DIP is the master, software is a veto**" contract
(`carrier/research/bringup_power_gating.md` sections 3.1/3.2).

This is a **carrier-local** subsystem (real carrier net names, no abstract
interface / `bind` map); it is folded into a per-name package only for
4-artifact parity with the generic `subsystems/<name>/` library.

## The uniform cell

```
 +3V3_SC                       +3V3_SC
    |                             |
   [DIP pos n]                 [100k pullup]      SN74LVC1G08 (VCC=+3V3_SC)
    |________ A _________________ |              .----------.
              |                   +---- B ------>|A      Y  |--> EN_<module>
            [100k pulldown]       |              |B         |
              |             TCA9535 P0x          '----------'
             GND            (Hi-Z at reset => B=1)
```

**AND, not OR.** The DIP (`A`) is the master; the TCA9535 expander port (`B`)
can only veto. At POR every TCA9535 port is an input, so the `B` pull-up holds
`B = 1` and stage-3 bring-up works on the switches alone — software can never
force a probe-shorted module ON.

## Cells on this sheet (10 module gates + 1 spare provision)

| cell | A net (from DIP) | B net (TCA9535) | Y net (enable) | B pull-up |
|------|------------------|-----------------|----------------|-----------|
| HDMI_TX   | `BU_DIP_HDMI_TX`    | `BU_OVR_HDMI_TX`    | `EN_HDMI_TX`    | 100k ↑ |
| HDMI_RX   | `BU_DIP_HDMI_RX`    | `BU_OVR_HDMI_RX`    | `EN_HDMI_RX`    | 100k ↑ |
| LCD       | `BU_DIP_LCD`        | `BU_OVR_LCD`        | `EN_LCD`       | 100k ↑ |
| CAM       | `BU_DIP_CAM`        | `BU_OVR_CAM`        | `EN_CAM`       | 100k ↑ |
| SD        | `BU_DIP_SD`         | `BU_OVR_SD`         | `EN_SD`        | 100k ↑ |
| USB       | `BU_DIP_USB`        | `BU_OVR_USB`        | `EN_USB`       | 100k ↑ |
| PMOD      | `BU_DIP_PMOD`       | `BU_OVR_PMOD`       | `EN_PMOD`      | 100k ↑ |
| USER_LED  | `BU_DIP_USER_LED`   | `BU_OVR_USER_LED`   | `EN_USER_LED`  | 100k ↑ |
| LCD_BL (spare) | `BU_DIP_SPARE` | `BU_OVR_LCD_BL`    | `EN_LCD_BL`    | **none** |
| HDMI_TX_5V | `BU_DIP_HDMI_TX_5V` | `BU_OVR_HDMI_TX_5V` | `EN_HDMI_TX_5V` | 100k ↑ |
| LCD_5V    | `BU_DIP_LCD_5V`     | `BU_OVR_LCD_5V`     | `EN_LCD_5V`    | 100k ↑ |

**The spare LCD-backlight cell has NO B pull-up here** — its `B` (TCA9535 P10)
carries the dossier's 100k pull**DOWN** on `bringup_rails`, so the
`EN_LCD_BL` provision defaults **OFF** until software raises P10.

The two **round-5 5 V gates** (`HDMI_TX_5V` / `LCD_5V`) ride a third DIP
(`SW6` on `bringup_rails`) and the next free expander ports (P12/P13), added
honestly rather than overloading an in-use position. Same uniform cell.

## Rails / straps

| net | role |
|-----|------|
| `+3V3_SC` | POWER — gate `VCC`; every (non-spare) `B` 100k pull-up ties here. Always-on SoM SC rail. |
| `GND` | GROUND — gate GND (pin 3), every `A` 100k pulldown bottom. |
| `EN_*` (11) | PORT — push-pull active-high enables; bind to the `bringup_modules` SY6280 load-switch EN pins (the spare binds to `lvds_lcd_power`). |

Per cell: a **100k pulldown** on `A`, a **100k pull-up** to `+3V3_SC` on `B`
(except the spare), one **100 nF** decoupling cap per gate — all live **here**
so each cell is electrically complete on this sheet.

## Parts

| ref | value | part | LCSC |
|-----|-------|------|------|
| U1..U11 | SN74LVC1G08 | `74xGxx:74LVC1G08` (SOT-23-5) | C7666 |
| R | 100k | `Device:R` 0603 (11 A-pulldowns + 10 B-pull-ups = 21) | C25803 |
| C | 100n | `Device:C` 0603 (one per gate VCC) | C14663 |

Every `Y` net carries a **testpoint**. Power-tree budget: 5 mA on `+3V3_SC`
(11 LVC gates + the 100k pull networks).

## Local test vs board gates

`test_bringup_en_modules.py` runs offline: model completeness, the
`design_rules` DECAP/STRAP/EP slice (0 findings, 11 supply pins), part/spice
slices, and the cell invariants this sheet owns (the 11 EN nets, the per-cell
100k pulldown, the 10 B pull-ups + the **one** spare with no pull-up, the
testpoints). The cross-board EN→SY6280 link stays at board level
(`schgen board`).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_en_modules/test_bringup_en_modules.py -q
```
