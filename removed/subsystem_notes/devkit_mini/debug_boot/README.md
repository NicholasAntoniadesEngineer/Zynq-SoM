# debug_boot — Zynq JTAG header, STM32 SWD header, boot-request DIP, and reset

`debug_boot` is the carrier's debug and boot-control front panel for the
Zynq-7000 SoM. It exposes a Xilinx-standard JTAG header on the dedicated Zynq TAP
nets, an ARM Cortex SWD header on the on-module STM32 system controller (SC), a
4-pole boot-request DIP, and a system reset button. It carries no active parts:
only headers, switches, and strap/pull resistors that ride the carrier rails
directly.

## Interface

This is a carrier-LOCAL subsystem. It binds the `ZYNQ_T*` / `STM32_*` net names
from the carrier SoM J1 mapping (`expect="som_j1_connector"`) directly, so there
is no abstract bind contract — the ports below merge with J1 at board link.

### Rails

| net | class | role |
|-----|-------|------|
| `+3V3` | POWER | JTAG VREF (VCCO_0 level) and TMS/TDI pull-up rail |
| `+3V3_SC` | POWER | always-on SC rail: SWD VTref and BOOT0/BOOTSEL pull-up rail |
| `GND` | GROUND | JTAG odd-row shield, SWD GND pins, reset/DIP contacts |

### Ports

| port | tied to | meaning |
|------|---------|---------|
| `ZYNQ_TMS` | J1.4, R1.2 | Zynq TAP TMS (+ 4k7 pull-up) |
| `ZYNQ_TCK` | J1.6 | Zynq TAP TCK |
| `ZYNQ_TDO` | J1.8 | Zynq TAP TDO |
| `ZYNQ_TDI` | J1.10, R2.2 | Zynq TAP TDI (+ 4k7 pull-up) |
| `STM32_GPIO6` | J2.2 | PA13 = SWDIO |
| `STM32_GPIO5` | J2.4 | PA14 = SWCLK |
| `STM32_NRST` | J2.10, SW2.1/2 | SC reset (SWD pin 10 + reset button) |
| `STM32_BOOT0` | SW1.1 | DIP pos1 → BOOT0 request |
| `STM32_GPIO7` | SW1.2, R4.2 | BOOTSEL0 request strap |
| `STM32_GPIO8` | SW1.3, R5.2 | BOOTSEL1 request strap |

Private internal nets: `BOOT0_SET` (DIP pos1 node into the 100R series strap) and
`BOOT_SPARE` (DIP pos4 reserved strap).

## Design

**Zynq JTAG header (J1, Molex 878311420).** A 2×7 2.00 mm header on the dedicated
`ZYNQ_T*` TAP nets. The odd row is the GND shield; pin 2 is VREF tied to `+3V3`
(VCCO_0 level). R1/R2 (4k7) provide insurance pull-ups on TMS and TDI to `+3V3`
so the TAP holds a defined state with no probe attached. Pin 12 and pin 14 (SRST)
are explicit NCs — the SoM does not export a probe-driven PS_SRST on J1.

**STM32 SWD header (J2, HX_JN1.27-2x5).** An ARM Cortex 10-pin 1.27 mm header on
the SC's PA13/PA14 (`STM32_GPIO6` = SWDIO, `STM32_GPIO5` = SWCLK). VTref (pin 1)
sits on the always-on `+3V3_SC`, so SWD works with the main rails down. Pins 6
(SWO), 7 (KEY), and 8 (TDI) are explicit NCs. Pin 10 carries `STM32_NRST`, shared
with the reset button.

**Boot-request DIP (SW1, DSHP04TSGER 4-pole).** Poles 1–4 pair with contacts 8–5.
Pos1 drives `STM32_BOOT0` high through R3 (100R series) from `+3V3_SC` against the
SoM's 1k5 pull-down: closed + reset selects USB DFU. The 100R is sized so the
closed divider (3.3 V across 100R + 1k5) holds BOOT0 at ~3.1 V, a logic high,
while limiting strap current to ~2 mA. Pos2/pos3 are BOOTSEL request straps to
`STM32_GPIO7`/`STM32_GPIO8`, each held high by a 10k pull-up (R4/R5) so the lines
are defined before the SC enables internal pulls; SC firmware decodes them and
drives the on-module Zynq BMODE pins. Pos4 is a reserved spare (`BOOT_SPARE`) with
the same 10k defined-high pattern (R6). Zynq boot mode is never strapped directly
on the carrier — the carrier only *requests* mode via these SC-read straps.

**Reset button (SW2, TS-1187A-B-A-B).** A momentary tact across `STM32_NRST` and
GND. Resetting the SC re-runs power and boot sequencing, giving a whole-system
reset; RC debounce lives on the SoM.

**Power budget.** `+3V3_SC` draws ~4 mA (BOOT0 strap ~2 mA closed plus the three
10k BOOTSEL/spare pulls); `+3V3` draws ~2 mA from the JTAG TMS/TDI insurance pulls
when driven.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| J1 | 2×7 JTAG | `878311420` | C240854 |
| J2 | HX_JN1.27-2x5 | `HX_JN1.27-2x5_TP_H4.9` | C42372555 |
| SW1 | DIP-4 | `DSHP04TSGER` | C3293144 |
| SW2 | RESET | `TS-1187A-B-A-B` | C318884 |
| R1, R2 | 4k7 | `Device:R` (R_0603) | C23162 |
| R3 | 100R | `Device:R` (R_0603) | C22775 |
| R4, R5, R6 | 10k | `Device:R` (R_0603) | C25804 |

## Build & test

`test_debug_boot.py` checks model completeness, the strap/pull-up resistor census,
the intentional NCs, and the `.cir` ↔ netlist passive match offline.

```bash
PYTHONPATH=. python3 -m pytest devkit_mini/subsystems/debug_boot/test_debug_boot.py -q
```
