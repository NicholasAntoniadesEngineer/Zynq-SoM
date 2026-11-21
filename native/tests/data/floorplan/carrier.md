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
| J1 | (136.5, 94.5) rot 180 | (21, 3.5) | 19.8 x 3.78 mm |
| J2 | (136.5, 129.5) rot 180 | (21, 38.5) | 19.8 x 3.78 mm |
| J3 | (154.5, 112) rot 90 | (3, 21) | 3.78 x 19.8 mm |

Derived board: **168 x 163 mm**; SoM origin at **(49, 66.5)** (centered). All coordinates below are board-frame mm, origin top-left, +y down (KiCad convention).

Outline derivation: SoM 50x42 + 7mm halo + 11mm connector band/edge -> core 86x78; component area 6062mm2 / 0.6 fill -> area floor 123x111; + 3mm perimeter keepout -> 130x120 mm (rounded up to 5mm grid); then bounded search over aspects 1, 1.0833, 1.1, 1.2, 1.3, 1.4 -> 168x163 mm (the smallest feasible board FOUND by this bounded aspect/grid search and greedy packing order, not a global minimum; holding the REAL 2-sided packed blocks with the estimated cross-subsystem airwire 16194 <= LAW-5 budget 16383 mm — honest routing headroom, the gate is not relaxed), SoM 50x42 centered.

## Edge connectors (pinned to edges by their mating direction)

| edge | sheet | block (x, y, w x h) | connector(s) | notes |
|---|---|---|---|---|
| N | microsd | (38.7776, 1.5, 19.4743 x 30.2967) | TF-01A (microSD push-pull) |  |
| N | pd_input | (58.5519, 1.5, 24.4554 x 22.0264) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| N | usbc_otg | (84.7123, 1.5, 24.168 x 22.2682) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| N | usb_jtag_connector | (110.33, 1.5, 10.9881 x 17.9341) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| N | usb_uart_connector | (122.768, 1.5, 10.9881 x 12.6341) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| W | rj45_connector | (1.5, 37.4833, 27.02 x 19.4) |  |  |
| W | lcd | (1.5, 58.3383, 23.71 x 44.655) | AFC07-S40FCA-00 (FFC 40-pin 0.5mm (LCD)) |  |
| W | camera | (1.5, 103.293, 16.0301 x 29.0751) | SFW15R-1STE1LF (FFC 15-pin 1mm (camera)) |  |
| E | motor_pwm | (121.94, 93.7726, 44.5601 x 19.8) |  |  |
| E | motor_sense | (145.575, 34.1352, 20.925 x 58.6874) | XT60PW-M (XT60 ESC power inlet (horizontal)), XT60PW-M (XT60 ESC power inlet (horizontal)) |  |
| E | board_qwiic | (155.365, 25.9303, 11.1351 x 6.9999) |  |  |
| S | hdmi_tx | (11.7501, 134.197, 17.1547 x 27.3027) | HDMI-019S (HDMI receptacle) |  |
| S | hdmi_rx | (48.9048, 144.797, 23.9645 x 16.7026) | HDMI-019S (HDMI receptacle) |  |
| S | pmod | (75.8693, 146.916, 41.765 x 14.584) | DS1024-2x6R2 (PMOD 2x6 socket), DS1024-2x6R2 (PMOD 2x6 socket) |  |
| S | pmod_expansion | (118.334, 140.447, 39.435 x 21.053) | DS1024-2x6R2 (PMOD 2x6 socket) |  |

## Interior blocks (zone = dominant SoM connector side, or the power cluster)

| sheet | anchor | block (x, y, w x h) | parts | est mm2 | notes |
|---|---|---|---|---|---|
| board_aux | E | (133, 52, 7.78 x 30.183) | 18 | 234.8 |  |
| board_services | W | (14, 12, 22.8 x 21.06) | 9 | 480.2 |  |
| bringup_en | E | (81, 111, 19.5 x 7.5) | 15 | 146.2 |  |
| bringup_en_modules | E | (61, 34, 39.1 x 12.45) | 54 | 486.8 |  |
| bringup_modules | E | (135, 11, 17.9 x 22.516) | 71 | 403 |  |
| bringup_rails | E | (58, 47, 41.81 x 16.894) | 23 | 706.3 |  |
| debug_boot | N | (61, 125, 31.58 x 16.25) | 10 | 513.2 |  |
| ethernet | @rj45_connector | (29, 35, 21.745 x 25.2576) | 10 | 549.2 |  |
| fmc | S | (28, 61, 18.685 x 61.63) | 8 | 1151.6 |  |
| hdmi_rx_term | S | (68, 112.59, 11.805 x 7.805) | 10 | 92.1 |  |
| mechanical | E | (131, 73, 13 x 13) | 4 | 169 |  |
| power | E | (114.36, 114, 53.2104 x 23.9349) | 51 | 1273.6 |  |
| power_mon | @power_som | (33, 125, 26.7565 x 12.1635) | 10 | 325.5 |  |
| power_som | E | (106, 69, 23.9349 x 24.335) | 23 | 582.5 |  |
| uart_bridge | @usb_uart_connector | (123, 15, 10.805 x 16.78) | 10 | 181.3 |  |
| usb_jtag | E | (102, 36, 29.1402 x 32.246) | 19 | 939.7 |  |
| usb_pd | @pd_input | (66, 24, 10.28 x 8.18) | 6 | 84.1 |  |
| user_io | S | (101, 94, 13.06 x 39.87) | 17 | 520.7 |  |

## Routing constraint classes (JLC06161H-3313 — from native/src/constraints.cpp)

| class | nets | geometry (track/gap mm) | match budget |
|---|---|---|---|
| DP100_DIFF | 50 | 0.1148 / 0.2032 | intra-pair <= 0.127..1.27 mm; inter-pair <= 0.127..1.27 mm |
| DP100_TMDS | 16 | 0.1148 / 0.2032 | intra-pair <= 2.9972 mm; inter-pair <= 2.9972 mm |
| DP90_USB | 8 | 0.1455 / 0.2032 | intra-pair <= 3.81 mm; inter-pair <= 3.81 mm |
| I2C | 10 | - | - |
| SD_1V8 | 6 | - | bus to CLK <= 2.5 mm (policy) |

Full per-net table: `carrier/manufacturing/layout_constraints.csv` (+ the `.kicad_dru` rules).

## Power and thermal (worst-case declared draws — powertree analysis)

| regulator | sheet | rail | I out (A) | est dissipation |
|---|---|---|---|---|
| SY6280AAC (U1) | board_aux | +3V3 -> +3V3_AUX | 0.211 | negligible |
| SY6280AAC (U1) | bringup_modules | +3V3 -> +3V3_HDMI_TX | 0.006 | negligible |
| SY6280AAC (U10) | bringup_modules | +5V -> +5V_LCD | 0.453 | negligible |
| SY6280AAC (U2) | bringup_modules | +3V3 -> +3V3_HDMI_RX | 0.005 | negligible |
| SY6280AAC (U3) | bringup_modules | +3V3 -> +3V3_LCD | 0.104 | negligible |
| SY6280AAC (U4) | bringup_modules | +3V3 -> +3V3_CAM | 0.304 | negligible |
| SY6280AAC (U5) | bringup_modules | +3V3 -> +3V3_SD | 0.254 | negligible |
| SY6280AAC (U6) | bringup_modules | +5V -> +5V_USB | 0.503 | negligible |
| SY6280AAC (U7) | bringup_modules | +3V3 -> +3V3_PMOD | 0.204 | negligible |
| SY6280AAC (U8) | bringup_modules | +3V3 -> +3V3_USER_LED | 0.016 | negligible |
| SY6280AAC (U9) | bringup_modules | +5V -> +5V_HDMI_TX | 0.058 | negligible |
| TLV75725PDYDR (U1) | fmc | +3V3 -> +2V5_VADJ | 0.400 | ~0.32 W |
| SY6280AAC (U3) | motor_pwm | +5V -> +5V_MOTOR_IO | 0.000 | negligible |
| TPS26631PWPR (U1) | pd_input | +VBUS_IN -> +VIN | 1.319 | negligible |
| SY6280AAC (U1) | pmod_expansion | +3V3 -> +3V3_PMODX | 0.104 | negligible |
| LM61460AANRJRR (U1) | power | +VIN_SYS -> +5V_REG | 2.744 | ~1.52 W |
| LM61460AANRJRR (U2) | power | +5V -> +3V3_REG | 2.245 | ~0.82 W |
| AP2112K-1.8 (U3) | power | +3V3 -> +1V8_REG | 0.006 | negligible |
| LM61460AANRJRR (U4) | power_som | +VIN_SYS -> +5V_SOM | 2.154 | ~1.11 W |
| AP2112K-3.3TRG1 (U4) | usb_jtag | +5V_DBG -> +3V3_DBG | 0.045 | ~0.08 W |

Numbers are the power-tree gate's worst-case declared draws (`carrier/reports/power_tree.txt`); regulators above ~0.3 W want copper pours + stitching vias.
