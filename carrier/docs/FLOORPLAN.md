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

Derived board: **182 x 156 mm**; SoM origin at **(56, 63)** (centered). All coordinates below are board-frame mm, origin top-left, +y down (KiCad convention).

Outline derivation: SoM 50x42 + 7mm halo + 11mm connector band/edge -> core 86x78; component area 6051mm2 / 0.6 fill -> area floor 123x111; + 3mm perimeter keepout -> 130x120 mm (rounded up to 5mm grid); then bounded search over aspects 1, 1.0833, 1.1, 1.2, 1.3, 1.4 -> 182x156 mm (the smallest feasible board FOUND by this bounded aspect/grid search and greedy packing order, not a global minimum; holding the REAL 2-sided packed blocks with the estimated cross-subsystem airwire 19661 mm; advisory airwire reference 16681 mm, not an acceptance constraint), SoM 50x42 centered.

## Edge connectors (pinned to edges by their mating direction)

| edge | sheet | block (x, y, w x h) | connector(s) | notes |
|---|---|---|---|---|
| N | usb_uart_connector | (19.9796, 1.5, 10.9881 x 12.6341) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| N | hdmi_rx | (35.9677, 1.5, 20.9645 x 16.9576) | HDMI-019S (HDMI receptacle) |  |
| N | pmod | (61.9322, 1.5, 46.765 x 14.839) | DS1024-2x6R2 (PMOD 2x6 socket), DS1024-2x6R2 (PMOD 2x6 socket) |  |
| N | pmod_expansion | (113.697, 1.5, 37.045 x 22.253) | DS1024-2x6R2 (PMOD 2x6 socket) |  |
| W | pd_input | (1.5, 10, 16.6982 x 35.7012) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| W | usb_jtag_connector | (1.5, 50.7012, 12.9121 x 17.8001) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| W | lcd | (1.5, 73.5013, 23.71 x 44.655) | AFC07-S40FCA-00 (FFC 40-pin 0.5mm (LCD)) |  |
| E | microsd | (155.758, 56.8052, 24.7417 x 24.7743) | TF-01A (microSD push-pull) |  |
| S | hdmi_tx | (19.6216, 127.197, 17.1547 x 27.3027) | HDMI-019S (HDMI receptacle) |  |
| S | motor_sense | (41.7813, 127.575, 57.2251 x 26.925) | XT60PW-M (XT60 ESC power inlet (horizontal)), XT60PW-M (XT60 ESC power inlet (horizontal)) |  |
| S | usbc_otg | (104.011, 133.432, 24.1682 x 21.0682) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| S | camera | (133.18, 134.37, 22.5248 x 20.1301) | SFW15R-1STE1LF (FFC 15-pin 1mm (camera)) |  |

## Interior blocks (zone = dominant SoM connector side, or the power cluster)

| sheet | anchor | block (x, y, w x h) | parts | est mm2 | notes |
|---|---|---|---|---|---|
| board_aux | E | (19, 56, 11.86 x 16.804) | 18 | 199.3 |  |
| board_qwiic | E | (61, 117, 12.9741 x 6.9999) | 3 | 90.8 |  |
| board_services | E | (146, 115, 33.18 x 15.537) | 9 | 515.5 |  |
| bringup_en | E | (92, 108, 8.2 x 14.4) | 15 | 118.1 |  |
| bringup_en_modules | E | (142, 60, 8.2 x 54) | 54 | 442.8 |  |
| bringup_modules | E | (101, 119, 43.06 x 9.596) | 71 | 413.2 |  |
| bringup_rails | E | (128, 51, 12.84 x 67.514) | 21 | 866.9 |  |
| debug_boot | N | (94, 35, 31.58 x 16.25) | 10 | 513.2 |  |
| ethernet | N | (32, 51, 21.745 x 29.5176) | 11 | 641.9 |  |
| fmc | E | (108, 53, 18.685 x 61.63) | 8 | 1151.6 |  |
| hdmi_rx_term | @hdmi_rx | (75, 109.09, 11.805 x 7.805) | 10 | 92.1 |  |
| mechanical | E | (72, 18, 13 x 13) | 4 | 169 |  |
| motor_pwm | @motor_sense | (34, 82, 19.8 x 44.0601) | 13 | 872.4 |  |
| power | E | (127, 26, 53.6604 x 24.1899) | 51 | 1298 |  |
| power_mon | E | (86, 18, 26.7565 x 12.1635) | 10 | 325.5 |  |
| power_som | E | (69, 32, 24.1899 x 24.4202) | 20 | 590.7 |  |
| rj45_connector | E | (34, 30, 19.4 x 19.76) | 3 | 383.3 |  |
| uart_bridge | @usb_uart_connector | (20, 15, 10.805 x 16.78) | 10 | 181.3 |  |
| usb_jtag | E | (151, 82, 30.5652 x 31.996) | 19 | 978 |  |
| usb_pd | @pd_input | (64, 107, 10.28 x 8.18) | 6 | 84.1 |  |
| user_io | S | (55, 21, 13.06 x 39.87) | 17 | 520.7 |  |

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
