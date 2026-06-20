# som_j3 — SoM mezzanine connector J3 (carrier-local subsystem)

The carrier side of the **J3** Hirose **DF40C-100DP-0.4V(51)** mezzanine
receptacle. J3 carries the **FPGA bank 33/34/35 IO + VCCO rails** half of the SoM
contract (LCD RGB888 + sync, camera CSI + control, FMC clocks/LA pairs, the
board-supervisor watchdog, the PUDC strap, and the bank-34/35 VCCO supply).

This is a **carrier-LOCAL** subsystem (the SoM side of the contract by
construction), foldered into a per-name package for 4-artifact parity with the
generic `subsystems/<name>/` library.

## How it is generated (never hand-typed)

`som_j3.py` loads the shared generator `carrier/som_conn_gen.py` and calls
`connector_circuit("J3", "som_j3", "SoM J3: FPGA bank 33/34/35 IO + VCCO rails")`.
The pin→net map comes from `carrier/som_interface.json`; the generator binds
every J3 pin verbatim, applies the wave-3 FUNCTION map (LCD/camera/FMC/watchdog
renames), the PUDC strap port, ties each `+VCCO_*` contact onto its carrier rail,
and types the camera/FMC diff pairs. No hand-typed pinout.

## Package contents

| file | role |
|------|------|
| `som_j3.py`       | the NETLIST — `circuit()` instantiating the DF40 receptacle bound to the J3 contract |
| `__init__.py`     | re-exports `circuit` |
| `som_j3.cir`      | SPICE subckt stub — externally-visible nets as pins; a pure connector carries no on-sheet passive network |
| `test_som_j3.py`  | LOCAL correctness test (offline: model completeness + design-rule slice + sheet invariants) |
| `README.md`       | this file |

## The connector — part

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J3 | DF40C-100DP-0.4V(51) | `parts/DF40C-100DP-0.4V_51/` (100 bare-number pins) | C531031 |

## Interface it carries (the J3 contract)

### Rails (POWER / GROUND)

| net | class | source / note |
|-----|-------|---------------|
| `+3V3`      | POWER  | VCCO source for Zynq bank **34** (LCD LVCMOS33). `+VCCO_34` merges onto the carrier +3V3 rail (SYS-1 in-fan rail tap). Declared draw 0.010 A. |
| `+2V5_VADJ` | POWER  | VCCO source for Zynq bank **35** (LVDS_25, camera/FMC). `+VCCO_35` merges onto the carrier +2V5_VADJ rail. Declared draw 0.050 A (sec 3.1 re-budget). |
| `GND`       | GROUND | ground. |

### Signal ports (PORT, 74 total)

Highlights (consumer sheet binds the same name):

- **LCD RGB888** (bank 34) — `LCD_R0..7`, `LCD_G0..7`, `LCD_B0..7`, `LCD_PCLK`, `LCD_HSYNC`, `LCD_VSYNC`, `LCD_DE`, `LCD_DISP`, `LCD_BL_PWM`.
- **Camera** (bank 33/35) — `CAM_CLK_{P,N}`, `CAM_D{0,1}_{P,N}` (typed `diff_pair` 100R MIPI CSI), plus control `CAM_SCL`, `CAM_SDA`, `CAM_EN`, `CAM_LED`.
- **FMC** (bank 35) — `FMC_CLK{0,1}_M2C_{P,N}`, `FMC_LA00_CC_{P,N}`, `FMC_LA01_CC_{P,N}`, `FMC_LA02..07_{P,N}` (typed `diff_pair` 100R).
- **Watchdog** (bank 33, +3V3 domain) — `WATCHDOG_RST_N` (TPS3823 RESET# → PL), `WATCHDOG_KICK` (PL → WDI). Relocated onto +3V3 PL pins so both share U3's 3.3 V domain.
- **PUDC** (bank 34) — `PUDC_34`: the pull-up-during-config pin, renamed to a function port here; its 10k-to-GND strap resistor lives on `bringup_rails` (connector sheets carry no discretes).
- **Bank-33/34/35 spares** — verbatim `IO_L*_33/34/35` ports kept for probe/expansion.

## Notes

- **Connector-only sheet**: no discretes; only the receptacle and its net binds.
- VCCO rails are real, sourced loads (carrier +3V3 / +2V5_VADJ), so they appear
  as power draws, not deferred orphans.
- Byte-identical: foldering this subsystem changed no emitted schematic or render.
