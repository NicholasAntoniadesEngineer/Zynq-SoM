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

Derived board: **149 x 149 mm**; SoM origin at **(49.5, 53.5)** (centered). All coordinates below are board-frame mm, origin top-left, +y down (KiCad convention).

Outline derivation: SoM 50x42 + 7mm halo + 11mm connector band/edge -> core 86x78; component area 5857mm2 / 0.6 fill -> area floor 121x110; + 3mm perimeter keepout -> 130x120 mm (rounded up to 5mm grid); then bounded search over aspects 1, 1.0833, 1.1, 1.2, 1.3, 1.4 -> 149x149 mm (the smallest feasible board FOUND by this bounded aspect/grid search and greedy packing order, not a global minimum; holding the REAL 2-sided packed blocks with the estimated cross-subsystem airwire 6297 mm; advisory airwire reference 7599 mm, not an acceptance constraint), SoM 50x42 centered.

## Edge connectors (pinned to edges by their mating direction)

| edge | sheet | block (x, y, w x h) | connector(s) | notes |
|---|---|---|---|---|
| N | esc_power | (14.3909, 1.5, 66.11 x 47.18) | XT60PW-M (XT60 ESC power inlet (horizontal)), XT60PW-M (XT60 ESC power inlet (horizontal)) |  |
| N | pd_input | (85.5009, 1.5, 24.9604 x 22.0264) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| E | usb_uart_connector | (136.477, 66.1424, 11.0232 x 16.7151) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| S | microsd | (68.4075, 120.653, 20.185 x 26.8467) | TF-01A (microSD push-pull) |  |

## Interior blocks (zone = dominant SoM connector side, or the power cluster)

| sheet | anchor | block (x, y, w x h) | parts | est mm2 | notes |
|---|---|---|---|---|---|
| board_control | E | (82, 37, 38.55 x 13.77) | 33 | 530.8 |  |
| bringup_en | E | (82, 29, 19.5 x 7.5) | 15 | 146.2 |  |
| can_bus | S | (13, 54, 8.52 x 44.56) | 11 | 379.7 |  |
| debug_boot | N | (103, 54, 18.76 x 40.63) | 11 | 762.2 |  |
| esc_io | E | (23, 53, 23.89 x 41.66) | 41 | 995.3 |  |
| ethernet | N | (34, 98, 29.7676 x 21.745) | 11 | 647.3 |  |
| mechanical | E | (97, 124, 13 x 13) | 4 | 169 |  |
| power | E | (93.62, 97.3, 53.6604 x 24.44) | 51 | 1311.5 |  |
| power_mon | E | (72, 110, 21.32 x 6.64) | 10 | 141.6 |  |
| power_som | E | (65.22, 99.45, 28.1 x 9.6) | 20 | 269.8 |  |
| rj45_connector | E | (45, 122, 20.41 x 20.77) | 3 | 423.9 |  |
| uart_bridge | @usb_uart_connector | (125, 66, 10.805 x 16.78) | 10 | 181.3 |  |
| vbat_supply | E | (123, 24, 22.24 x 39.7) | 35 | 882.9 |  |

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
