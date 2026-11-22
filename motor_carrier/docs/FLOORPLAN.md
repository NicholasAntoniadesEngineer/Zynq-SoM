# Floorplan

![floorplan](FLOORPLAN.svg)

## Sources (everything derived, nothing invented)

- SoM outline + connector positions: `som/Zynq_SoM.kicad_pcb` (Edge.Cuts bbox + connector footprints, parsed live)
- block sizes: per-part courtyards (`parts/<MPN>/<MPN>.kicad_mod` F.CrtYd; KiCad-standard footprints from the dims in their names), big parts raw + small parts x3.5 routing factor
- edge pinning + zones: connector parts in each sheet netlist + linker module-connector bindings (incl. `expect=` deferrals)
- electrical notes: `native/src/constraints.cpp` (JLC06161H-3313), `native/src/power_checks.cpp` analysis, typed ports (1.8V SDIO)

## Extracted SoM geometry

SoM outline: **50 x 42 mm**.

| conn | SoM PCB `(at)` | carrier-top view (SoM-rel) | pad extent |
|---|---|---|---|
| J1 | (136.5, 94.5) rot 180 | (29, 3.5) | 19.8 x 3.78 mm |
| J2 | (136.5, 129.5) rot 180 | (29, 38.5) | 19.8 x 3.78 mm |
| J3 | (154.5, 112) rot 90 | (47, 21) | 3.78 x 19.8 mm |

Derived board: **147 x 147 mm**; SoM origin at **(48.5, 52.5)** (centered). All coordinates below are board-frame mm, origin top-left, +y down (KiCad convention).

Outline derivation: SoM 50x42 + 7mm halo + 11mm connector band/edge -> core 86x78; component area 4549mm2 / 0.6 fill -> area floor 111x101; + 3mm perimeter keepout -> 120x110 mm (rounded up to 5mm grid); then bounded search over aspects 1, 1.0909, 1.1, 1.2, 1.3, 1.4 -> 147x147 mm (the smallest feasible board FOUND by this bounded aspect/grid search and greedy packing order, not a global minimum; holding the REAL 2-sided packed blocks with the estimated cross-subsystem airwire 6238 mm; advisory airwire reference 7497 mm, not an acceptance constraint), SoM 50x42 centered.

## Edge connectors (pinned to edges by their mating direction)

| edge | sheet | block (x, y, w x h) | connector(s) | notes |
|---|---|---|---|---|
| N | esc_power | (11.5, 1.5, 63.656 x 46.3) | XT60PW-M (XT60 ESC power inlet (horizontal)), XT60PW-M (XT60 ESC power inlet (horizontal)) |  |
| N | microsd | (80.161, 1.5, 19.4743 x 30.2967) | TF-01A (microSD push-pull) |  |
| N | pd_input | (104.635, 1.5, 24.4554 x 22.0264) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| E | usb_uart_connector | (132.866, 68.0059, 12.6342 x 10.9881) | TYPE-C-31-M-12 (USB-C receptacle) |  |

## Interior blocks (zone = dominant SoM connector side, or the power cluster)

| sheet | anchor | block (x, y, w x h) | parts | est mm2 | notes |
|---|---|---|---|---|---|
| board_control | E | (102, 40, 8.9 x 56.11) | 33 | 499.4 |  |
| bringup_en | E | (112, 65, 5.2 x 23.4) | 15 | 121.7 |  |
| can_bus | S | (14, 52, 7.78 x 43.694) | 11 | 339.9 |  |
| debug_boot | N | (58, 109, 31.58 x 16.25) | 11 | 513.2 |  |
| esc_io | E | (23, 53, 22.89 x 39.8) | 41 | 911 |  |
| ethernet | N | (28, 97, 29.5176 x 21.745) | 11 | 641.9 |  |
| mechanical | E | (119, 83, 13 x 13) | 4 | 169 |  |
| power | E | (92.4, 96.41, 53.6604 x 24.1899) | 51 | 1298 |  |
| power_mon | E | (89, 36, 9.166 x 13.198) | 10 | 121 |  |
| power_som | E | (64, 98.95, 28.1 x 9.1) | 20 | 255.7 |  |
| rj45_connector | E | (37, 121, 19.4 x 19.76) | 3 | 383.3 |  |
| uart_bridge | @usb_uart_connector | (121, 65, 10.805 x 16.78) | 10 | 181.3 |  |
| vbat_supply | E | (112, 26, 21.36 x 37.692) | 35 | 805.1 |  |

## Routing constraint classes (JLC06161H-3313 — from native/src/constraints.cpp)

| class | nets | geometry (track/gap mm) | match budget |
|---|---|---|---|
| DP100_DIFF | 16 | 0.1148 / 0.2032 | intra-pair <= 1.27 mm; inter-pair <= 1.27 mm |
| DP90_USB | 6 | 0.1455 / 0.2032 | intra-pair <= 3.81 mm; inter-pair <= 3.81 mm |
| I2C | 2 | - | - |
| SD_1V8 | 6 | - | bus to CLK <= 2.5 mm (policy) |

Full per-net table: `carrier/manufacturing/layout_constraints.csv` (+ the `.kicad_dru` rules).

## Power and thermal (worst-case declared draws — powertree analysis)

| regulator | sheet | rail | I out (A) | est dissipation |
|---|---|---|---|---|
| SY6280AAC (U2) | board_control | +5V -> +5V_FAN | 0.200 | negligible |
| SY6280AAC (U3) | esc_io | +5V -> +5V_MOTOR_IO | 0.000 | negligible |
| TPS26631PWPR (U1) | pd_input | +VBUS_IN -> +VIN_PD | 0.000 | negligible |
| LM61460AANRJRR (U1) | power | +VIN_SYS -> +5V_REG | 0.628 | ~0.35 W |
| LM61460AANRJRR (U2) | power | +5V -> +3V3_REG | 0.360 | ~0.13 W |
| AP2112K-1.8 (U3) | power | +3V3 -> +1V8_REG | 0.006 | negligible |
| LM61460AANRJRR (U4) | power_som | +VIN_SYS -> +5V_SOM | 2.154 | ~1.11 W |
| TPS26631PWPR (U1) | vbat_supply | +VBAT_D -> +VBAT_SW | 0.003 | negligible |
| LM61460AANRJRR (U2) | vbat_supply | +VBAT_SW -> +VPRE | 0.007 | negligible |

Numbers are the power-tree gate's worst-case declared draws (`carrier/reports/power_tree.txt`); regulators above ~0.3 W want copper pours + stitching vias.
