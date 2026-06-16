# bringup_en — rail EN AND-cells (carrier-local subsystem)

The three **rail** enable cells of the staged bring-up power-gating scheme:
one uniform `SN74LVC1G08` 2-input AND gate per rail, implementing the
"**DIP is the master, software is a veto**" contract
(`carrier/research/bringup_power_gating.md` sections 3.1/3.2).

This is a **carrier-local** subsystem (not a project-agnostic library package):
it wires the carrier's real net names directly, so there is no abstract
interface / `bind` map. It is folded into a per-name package only for
4-artifact parity with the generic `subsystems/<name>/` library.

## What it is

```
 +3V3_SC                       +3V3_SC
    |                             |
   [DIP pos n]                 [100k pullup]      SN74LVC1G08 (VCC=+3V3_SC)
    |________ A _________________ |              .----------.
              |                   +---- B ------>|A      Y  |--> EN_<rail>
            [100k pulldown]       |              |B         |
              |             STM32 GPIO           '----------'
             GND            (Hi-Z at reset => B=1)
```

**AND, not OR.** The DIP switch (`A`) is the master; software (`B`) can only
**force-OFF** (veto). At power-on the STM32 GPIOs are Hi-Z, so the `B` pull-up
holds `B = 1` and stage-1 bring-up works on the switches alone; software can
never force a probe-shorted rail ON behind a human's back.

## Cells on this sheet (3 rails)

| cell | A net (from DIP) | B net (from STM32 direct) | Y net (enable) |
|------|------------------|---------------------------|----------------|
| 5V0  | `BU_DIP_5V0` | `STM32_RAIL_EN_5V0` | `EN_5V0` |
| 3V3  | `BU_DIP_3V3` | `STM32_RAIL_EN_3V3` | `EN_3V3` |
| 1V8  | `BU_DIP_1V8` | `STM32_RAIL_EN_1V8` | `EN_1V8` |

The three rail vetoes are **direct STM32 GPIOs** (`STM32_RAIL_EN_5V0..1V8`),
not TCA9535 expander ports, so the core rails stay controllable even if the
I2C bus is down. (The ten module cells live on `bringup_en_modules`, B from
the TCA9535.)

## Rails / straps

| net | role |
|-----|------|
| `+3V3_SC` | POWER — gate `VCC`, and the rail that every `B` 100k pull-up ties to. The SoM system-controller rail, **always-on** (alive from default 5 V VBUS before any carrier rail). |
| `GND` | GROUND — gate GND (pin 3), every `A` 100k pulldown bottom. |
| `EN_5V0` / `EN_3V3` / `EN_1V8` | PORT — push-pull active-high 3.3 V CMOS enables; bind to the `power` regulator EN pins (TPS54302 / AP2112K). |

Per cell: a **100k pulldown** on `A` (closed DIP = logic 1) and a **100k
pull-up** to `+3V3_SC` on `B` (Hi-Z source ⇒ enabled) — both live **here at
the gate** so each cell is electrically complete on this sheet. One **100 nF**
decoupling cap per gate.

## Parts

| ref | value | part | LCSC |
|-----|-------|------|------|
| U1..U3 | SN74LVC1G08 | `74xGxx:74LVC1G08` (SOT-23-5, 1=A 2=B 3=GND 4=Y 5=VCC) | C7666 |
| R (×6) | 100k | `Device:R` 0603 (A pulldown + B pull-up per cell) | C25803 |
| C (×3) | 100n | `Device:C` 0603 (one per gate VCC) | C14663 |

Every `Y` net carries a **testpoint** (stage-1 bring-up is debugged with a
meter on the EN cells). Power-tree budget: 2 mA on `+3V3_SC` (3 LVC gates +
the 100k pull networks).

## Local test vs board gates

`test_bringup_en.py` runs offline: model completeness (every pin netted/NC),
the `design_rules` DECAP/STRAP/EP slice (0 findings, 3 supply pins checked),
the `part_rules` + `spice` slices, and the cell invariants this sheet owns
(the 3 EN nets, the per-cell 100k pull-up + pulldown, the testpoints). The
cross-board link / port-driver graph (the EN→regulator binding, the
DIP/GPIO sources) stays aggregated at board level (`schgen board`).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_en/test_bringup_en.py -q
```
