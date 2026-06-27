# som/ — Zynq-7000 System-on-Module

A hand-authored Zynq-7000 system-on-module (SoM) KiCad project. Open
`som/Zynq_SoM.kicad_pro` in KiCad 9 or later. This project is maintained by
hand in the KiCad schematic and board editors; it is not generated.

## Layout

```
som/
  Zynq_SoM.kicad_pro / .kicad_sch / .kicad_pcb   # the module project
  Zynq_SoM.pdf                                    # rendered schematic
  schematic/                                      # the 16 hierarchical sub-sheets
  lib/                                            # custom symbols, footprints, 3D models
  manufacturing/                                  # fabrication + assembly outputs
  fp-lib-table                                    # project footprint library table
  Zynq_SoM.kicad_dru                              # design-rule constraints
  Jobset.kicad_jobset                             # KiCad jobset for output generation
```

`Zynq_SoM.kicad_sch` is the root sheet; the design is split across the 16
hierarchical sub-sheets in `schematic/`, organized by function: the Zynq PS/PL
banks (`zynq_PS_b500_b501`, `zynq_PL_b13`, `zynq_b33_b34_b35`, `zynq_config`,
`zynq_ddr`, `zynq_power`), DDR3L memory (`DDR3L`), Ethernet PHY, USB HS PHY,
eMMC, power (`Power`, `power_architecture`), the system controller, sensors,
and the J1/J2/J3 mezzanine connectors (`connectors`).

## Custom libraries (`lib/`)

The project pins its own libraries so the design is self-contained:

- `lib/zynq_eda.kicad_sym` — schematic symbols for the SoM's parts (Zynq,
  DDR, PHYs, sensors, regulators).
- `lib/generated/` — generated interface symbols (FMC, HDMI, MIPI, PMOD,
  LVDS-LCD, XADC, STM32 breakout) and the `connector_banks/` symbols that
  pin out the mezzanine connector banks.
- `lib/zynq_som.pretty/` — the custom footprints, including the
  `HRS_DF40C-100DP-0.4V_51_` mezzanine connector and the Zynq/DDR BGAs.
  Registered via `fp-lib-table` as the `fp` library.
- `lib/3d/` — STEP/WRL models for the custom and passive footprints.

## SoM ↔ carrier interface contract

The SoM mates to the carrier board over three Hirose DF40 100-pin mezzanine
connectors, **J1**, **J2**, and **J3** — 300 pins total. The pin assignment on
these connectors is the electrical contract between the two boards:

- J1 carries the supply rails (VIN, +3V3, +1V8), USB, JTAG, SDIO, the STM32
  system-controller signals, and the Ethernet MDI pairs.
- J2 and J3 carry the Zynq bank I/O (VCCO rails plus the bank 13/33/34/35
  IO_Lxx differential and single-ended lines).

This contract is **extracted programmatically** from this project, never
hand-copied. `schgen som-interface` reads `som/Zynq_SoM.kicad_sch` and writes
`carrier/som_interface.json` — the per-connector pin→net map the carrier
subsystems bind against. The carrier's FPGA pin constraints
(`carrier/fpga/Zynq_Carrier_pins.xdc`, produced by `schgen xdc`) are derived
and cross-checked against the same contract, so the Vivado pin map cannot drift
from the module's actual pinout.

The dependency runs one way: this SoM project is the upstream source of truth.
Edits here flow into `som_interface.json` and the carrier on the next
extraction; the SoM is never edited to match the carrier.
