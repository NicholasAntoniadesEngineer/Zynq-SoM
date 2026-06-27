# bringup_en — rail enable AND-cells (DIP master, software veto)

The three core-rail enable cells of the staged bring-up power-gating scheme on
the Zynq-7000 SoM carrier: one uniform `SN74LVC1G08` 2-input AND gate per rail
(+5V / +3V3 / +1V8). Each cell ANDs a DIP-switch master input against a software
override input, so a rail turns on only when the human switch is closed AND
software has not vetoed it. This is a carrier-local subsystem — it wires the
carrier's real net names directly and exposes no abstract bind map.

## Interface

`bringup_en` drives carrier nets directly (no `bind`/META contract). It owns one
gate per rail and emits the rail enable lines; the DIP and STM32-GPIO sources,
and the regulator EN sinks, live on other sheets and connect by net name.

| net | direction | role |
|-----|-----------|------|
| `BU_DIP_5V0` / `BU_DIP_3V3` / `BU_DIP_1V8` | in (port → A) | DIP master contact per rail, from `bringup_rails`. |
| `STM32_RAIL_EN_5V0` / `STM32_RAIL_EN_3V3` / `STM32_RAIL_EN_1V8` | in (port → B) | software override per rail, direct STM32 GPIO from `som_j3_connector`. |
| `EN_5V0` / `EN_3V3` / `EN_1V8` | out (port ← Y) | active-high 3.3 V CMOS push-pull enables, bind to `power` regulator EN pins. |
| `+3V3_SC` | power | gate VCC and the rail every B pull-up ties to. |
| `GND` | ground | gate GND and every A pulldown bottom. |

## Design

**AND, not OR — DIP is the master, software is a veto.** Each cell ANDs the DIP
contact (`A`) with the software override (`B`). Software can only force a rail
OFF; it can never force one ON. At power-on the STM32 GPIOs are Hi-Z, so the `B`
100k pull-up to `+3V3_SC` holds `B = 1` and stage-1 bring-up works on the DIP
switches alone, while an unprogrammed MCU can never turn a probe-shorted rail on
behind a human's back.

**Gate — `SN74LVC1G08DBVR` (SOT-23-5).** Single 2-input AND, pinout 1=A 2=B
3=GND 4=Y 5=VCC. Inputs are 5.5 V tolerant and the output is 32 mA rail-to-rail
push-pull, so it drives any regulator or load-switch EN pin directly. VCC is
`+3V3_SC`, the SoM system-controller rail that is alive from the default 5 V VBUS
before any carrier rail comes up, so the enable logic is live before the rails it
gates.

**Per-cell network (complete on this sheet).** `A` carries a 100k pulldown to
GND (closed DIP = logic 1, open DIP = 0). `B` carries a 100k pull-up to
`+3V3_SC` (Hi-Z source ⇒ enabled). One 100 nF decoupling cap sits on each gate
VCC. Both pulls live at the gate so each cell is electrically complete here.

**Direct GPIO vetoes for the core rails.** The three rail override inputs are
direct STM32 GPIOs (`STM32_RAIL_EN_*`), not TCA9535 expander ports, so the core
rails stay controllable even if the I2C bus is down. (The module load-switch
cells, whose B inputs come from the TCA9535, live on `bringup_modules`.)

**Enable drive.** `EN_*` are 3.3 V CMOS, active-high, push-pull. They bind to
the `power` regulator EN pins — the LM61460 EN/SYNC on the +5V and +3V3 bucks
(VIH ~1.2 V typ, abs-max 42 V) and the AP2112K EN on +1V8 — all of which accept
the 3.3 V drive rail-to-rail.

**Probeability.** Every `Y` enable net carries a testpoint, since stage-1
bring-up is debugged with a meter on the EN cells. Power-tree budget is 2 mA on
`+3V3_SC` (three LVC gates plus the 100k pull networks).

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1–U3 | SN74LVC1G08 | `74xGxx:74LVC1G08` (SOT-23-5) | C7666 |
| R (×6) | 100k | `Device:R` 0603 (A pulldown + B pull-up per cell) | C25803 |
| C (×3) | 100n | `Device:C` 0603 (one per gate VCC) | C14663 |

## Build & test

`test_bringup_en.py` runs offline: model completeness, the `+3V3_SC`/`GND`/`EN_*`
rail-and-port classes, the DECAP/STRAP/EP design-rule slice, the part and SPICE
slices, and the cell invariants this sheet owns (the 3 EN nets, per-cell 100k
pull-up + pulldown, per-Y testpoints).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/bringup_en/test_bringup_en.py -q
```
