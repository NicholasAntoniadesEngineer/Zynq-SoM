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

Derived board: **180 x 165 mm**; SoM origin at **(55, 67.5)** (centered). All coordinates below are board-frame mm, origin top-left, +y down (KiCad convention).

Outline derivation: SoM 50x42 + 7mm halo + 11mm connector band/edge -> core 86x78; component area 7759mm2 / 0.6 fill -> area floor 135x122; + 3mm perimeter keepout -> 145x130 mm (rounded up to 5mm grid); then bounded search over aspects 1, 1.1, 1.1154, 1.2, 1.3, 1.4 -> 180x165 mm (the smallest feasible board FOUND by this bounded aspect/grid search and greedy packing order, not a global minimum; holding the REAL 2-sided packed blocks with the estimated cross-subsystem airwire 19785 mm; advisory airwire reference 17061 mm, not an acceptance constraint), SoM 50x42 centered.

## Edge connectors (pinned to edges by their mating direction)

| edge | sheet | block (x, y, w x h) | connector(s) | notes |
|---|---|---|---|---|
| N | hdmi_rx | (31.9206, 1.5, 24.2225 x 17.0826) | HDMI-019S (HDMI receptacle) |  |
| N | pmod | (61.1432, 1.5, 46.765 x 14.839) | DS1024-2x6R2 (PMOD 2x6 socket), DS1024-2x6R2 (PMOD 2x6 socket) |  |
| N | pmod_expansion | (112.908, 1.5, 37.795 x 23.019) | DS1024-2x6R2 (PMOD 2x6 socket) |  |
| W | pd_input | (1.5, 12.9509, 16.6982 x 36.2062) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| W | usb_jtag_connector | (1.5, 54.1571, 13.8891 x 18.3051) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| W | lcd | (1.5, 77.4622, 23.71 x 45.155) | AFC07-S40FCA-00 (FFC 40-pin 0.5mm (LCD)) |  |
| E | microsd | (153.758, 61.1073, 24.7417 x 25.17) | TF-01A (microSD push-pull) |  |
| S | usb_uart_connector | (13.1804, 149.866, 10.9551 x 13.6342) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| S | hdmi_tx | (29.1355, 136.197, 17.1547 x 27.3027) | HDMI-019S (HDMI receptacle) |  |
| S | motor_sense | (51.2902, 139.825, 39.575 x 23.675) | XT60PW-M (XT60 ESC power inlet (horizontal)), XT60PW-M (XT60 ESC power inlet (horizontal)) |  |
| S | usbc_otg | (95.8652, 141.432, 25.1551 x 22.0682) | TYPE-C-31-M-12 (USB-C receptacle) |  |
| S | camera | (126.02, 143.37, 22.5248 x 20.1301) | SFW15R-1STE1LF (FFC 15-pin 1mm (camera)) |  |

## Interior blocks (zone = dominant SoM connector side, or the power cluster)

| sheet | anchor | block (x, y, w x h) | parts | est mm2 | notes |
|---|---|---|---|---|---|
| board_aux | E | (127, 61, 25.7 x 10.76) | 18 | 276.5 |  |
| board_qwiic | E | (98, 52, 7.5101 x 12.3141) | 3 | 92.5 |  |
| board_services | E | (76, 18, 35.81 x 16.05) | 11 | 574.8 |  |
| bringup_en | E | (26, 80, 5.2 x 23.4) | 15 | 121.7 |  |
| bringup_en_modules | E | (26, 53, 39.1 x 12.45) | 54 | 486.8 |  |
| bringup_modules | E | (43, 29, 20.1 x 23.09) | 71 | 464.1 |  |
| bringup_rails | E | (33, 66, 19.1 x 43.1) | 21 | 823.2 |  |
| debug_boot | N | (87, 120, 33.59 x 18.27) | 10 | 613.7 |  |
| ethernet | N | (127, 73, 21.745 x 29.7676) | 11 | 647.3 |  |
| fmc | E | (107, 58, 18.935 x 61.63) | 8 | 1167 |  |
| hdmi_rx_term | @hdmi_rx | (74, 113.59, 11.805 x 7.805) | 10 | 92.1 |  |
| mechanical | E | (122, 127, 13 x 13) | 4 | 169 |  |
| motor_pwm | @motor_sense | (27, 115, 45.3101 x 20.05) | 13 | 908.5 |  |
| power | E | (149.695, 86.5773, 24.44 x 53.6604) | 51 | 1311.5 |  |
| power_mon | E | (92.7202, 37.6165, 35.4666 x 12.6785) | 10 | 449.7 |  |
| power_som | E | (68, 36, 24.4202 x 24.44) | 20 | 596.8 |  |
| rj45_connector | E | (128, 105, 20.41 x 20.77) | 3 | 423.9 |  |
| uart_bridge | @usb_uart_connector | (11, 137, 16.78 x 10.805) | 10 | 181.3 |  |
| usb_jtag | E | (129, 28, 32.512 x 30.8202) | 19 | 1002 |  |
| usb_pd | @pd_input | (64, 27, 10.28 x 8.18) | 6 | 84.1 |  |
| user_io | S | (21, 6, 9.8 x 46.44) | 17 | 455.1 |  |

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
