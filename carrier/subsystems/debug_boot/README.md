# debug_boot — Zynq JTAG + STM32 SWD headers, boot-request DIP, reset (carrier-local)

A **carrier-local** schgen subsystem: the carrier's debug + boot-control front
panel. It binds verbatim `ZYNQ_T*` / `STM32_*` net names from
`carrier/som_interface.json` (J1) and rides the carrier rails directly, so there
is no abstract-interface / bind contract (board-specific by construction).

## Package contents

| file | role |
|------|------|
| `debug_boot.py`      | the NETLIST — `circuit()`, carrier nets |
| `debug_boot.cir`     | SPICE subckt — the strap / pull-up resistor network, J1/SWD pins + rails as subckt pins |
| `test_debug_boot.py` | LOCAL electrical-correctness test (offline; model completeness + strap pulls + NCs) |
| `README.md`          | this file |

## Purpose

Four hand-soldered debug/boot facilities, all verified against the SoM netlist:

1. **Zynq JTAG** — Xilinx-standard 2×7 2.00 mm header (Molex 87831-1420) on the
   dedicated `ZYNQ_T*` nets, with 4k7 insurance pull-ups on TMS/TDI to VREF
   (= +3V3 = VCCO_0). Odd row = GND shield. Pin 12 NC, pin 14 SRST NC (not
   exported by the SoM — owned by the on-module STM32).
2. **STM32 SWD** — ARM Cortex 10-pin 1.27 mm header on the SC's PA13/PA14 (J1
   names `STM32_GPIO6`=SWDIO / `STM32_GPIO5`=SWCLK). VTref on the **always-on**
   `+3V3_SC`, so debug works with the main rails down. SWO (pin 6), KEY (pin 7
   absent), TDI (pin 8) are explicit NCs.
3. **Boot-request DIP** (DIP-4):
   - pos1 drives `STM32_BOOT0` high through **100R** against the SoM's 1k5
     pull-down (closed + reset = USB DFU over the carrier Type-C);
   - pos2/3 are BOOTSEL request straps to `STM32_GPIO7`/`STM32_GPIO8` (SC
     firmware decodes 00/01/10/11 → JTAG/QSPI/SD/reserved and drives the
     on-module Zynq BMODE pins), each with a 10k defined-high pull-up;
   - pos4 spare (`BOOT_SPARE`), same 10k defined-high pattern.
4. **Reset tact** — momentary on `STM32_NRST`; resetting the SC re-runs power/
   boot sequencing = whole-system reset (RC debounce lives on the SoM).

## Parts

| ref | value | part / footprint | LCSC | role |
|-----|-------|------------------|------|------|
| J1 | (JTAG) | `878311420` (use_part) | C240854 | 2×7 2.00 mm JTAG header |
| J2 | HX_JN1.27-2x5 | `HX_JN1.27-2x5_TP_H4.9` (use_part) | C42372555 | ARM 10-pin SWD header |
| SW1 | DIP-4 | `DSHP04TSGER` (use_part) | C319050 | boot-request DIP |
| SW2 | RESET | `TS-1187A-B-A-B` (use_part) | C318884 | reset tact |
| R1, R2 | 4k7 | `Device:R` / R_0603 | C23162 | JTAG TMS/TDI insurance pulls (→ +3V3) |
| R3 | 100R | `Device:R` / R_0603 | C22775 | BOOT0 series strap |
| R4, R5, R6 | 10k | `Device:R` / R_0603 | C25804 | BOOTSEL0/1 + spare defined-high (→ +3V3_SC) |

No active parts → no decoupling caps in this subsystem.

## Interface (carrier nets — straps & headers)

### Rails

| net | class | meaning |
|-----|-------|---------|
| `+3V3` | POWER | JTAG VREF (VCCO_0 level) + TMS/TDI 4k7 pull-ups |
| `+3V3_SC` | POWER | always-on SC rail: SWD VTref + BOOT0/BOOTSEL pull-ups |
| `GND` | GROUND | JTAG odd-row shield, SWD GND pins, reset contacts |

### Ports (merge with J1 / the SWD header at board link)

| port | source | meaning |
|------|--------|---------|
| `ZYNQ_TMS` | J1.4, R1.2 | Zynq TAP TMS (+ 4k7 pull-up) |
| `ZYNQ_TCK` | J1.6 | Zynq TAP TCK |
| `ZYNQ_TDO` | J1.8 | Zynq TAP TDO |
| `ZYNQ_TDI` | J1.10, R2.2 | Zynq TAP TDI (+ 4k7 pull-up) |
| `STM32_GPIO6` | J2.2 | PA13 = SWDIO |
| `STM32_GPIO5` | J2.4 | PA14 = SWCLK |
| `STM32_NRST` | J2.10, SW2.1/2 | reset (shared header pin 10 + reset button) |
| `STM32_BOOT0` | SW1.1 | DIP pos1 → 100R → BOOT0_SET |
| `STM32_GPIO7` | SW1.2, R4.2 | BOOTSEL0 request strap |
| `STM32_GPIO8` | SW1.3, R5.2 | BOOTSEL1 request strap |

### Strap-resistor map (the electrical contract)

| signal | pull | rail | when |
|--------|------|------|------|
| ZYNQ_TMS | 4k7 up | +3V3 | insurance vs floating bus, no probe attached |
| ZYNQ_TDI | 4k7 up | +3V3 | insurance vs floating bus |
| STM32_BOOT0 | 100R series → BOOT0_SET → DIP → +3V3_SC | +3V3_SC | closed = +3.1 V at BOOT0 vs SoM 1k5 pull-down |
| STM32_GPIO7 (BOOTSEL0) | 10k up | +3V3_SC | defined-high before SC enables internal pulls |
| STM32_GPIO8 (BOOTSEL1) | 10k up | +3V3_SC | defined-high |
| BOOT_SPARE (DIP pos4) | 10k up | +3V3_SC | reserved, defined-high |

`BOOT0_SET`, `BOOT_SPARE` are private internal nets (DIP node + spare strap);
`STM32_NRST` is shared between the SWD header pin 10 and the reset button.

## Power-tree budget

- `+3V3_SC` 4 mA: BOOT0 strap ~2 mA when closed (3.3 V / (100R + 1k5)) + 3× 10k
  BOOTSEL/spare pulls.
- `+3V3` 2 mA: JTAG TMS/TDI 4k7 insurance pulls when driven.

## Notes

- **Zynq boot mode is NOT strapped directly** on the carrier — the Zynq mode
  straps live on the SoM QSPI nets and are STM32-driven. The carrier only
  *requests* boot mode via the BOOTSEL straps the SC firmware reads.
- **VM0/VM1** are already strapped on-SoM (10k) — the carrier must not re-strap.
- **PA13/PA14** (SWD) are reserved for debug; SC firmware must never reconfigure
  them as GPIO.
- **JTAG pin 14 NC** → no probe-driven PS_SRST (a SoM-rev limitation).

## Local test

`test_debug_boot.py` runs the subsystem-LOCAL slices offline (model
completeness, the `design_rules` STRAP slice, the strap/pull-up resistor census,
the intentional NCs, the `.cir` ↔ netlist passive match). Cross-board gates stay
aggregated by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/debug_boot/test_debug_boot.py -q
```
