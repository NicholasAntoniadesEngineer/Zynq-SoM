# LVDS LCD connector - XUNPU FPC-05F-40PH20

40-pin 0.5 mm pitch right-angle SMT FFC receptacle. Pure mechanical part; the carrier owns LVDS termination, panel power decoupling, and EDID pull-ups.

## Pin assignment (single-link 4-lane LVDS panel)

| Pin | Net | Notes |
|---|---|---|
| 1, 6, 9, 12, 15, 18, 21, 23, 31-40 | GND | |
| 2, 3 | +3V3 | Panel logic supply |
| 4, 5 | EDID_SDA / SCL | I2C for panel EDID (3.3 V) |
| 7, 8 | LVDS_CLK -/+ | 100 ohm differential clock pair |
| 10, 11 | LVDS_DA0 -/+ | LVDS data lane 0 |
| 13, 14 | LVDS_DA1 -/+ | LVDS data lane 1 |
| 16, 17 | LVDS_DA2 -/+ | LVDS data lane 2 |
| 19, 20 | LVDS_DA3 -/+ | LVDS data lane 3 |
| 22 | RESET_N | Active-low panel reset |
| 24 | STBY_N | Active-low panel standby |
| 25 | PWM | Backlight PWM |
| 26 | BL_EN | Backlight enable (default off) |
| 27-30 | +12V | Backlight power |

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| LVDS_CLK +/- | 100R 0402 differential | Far-end LVDS termination (IEEE 1596.3) |
| LVDS_DATA0 +/- | 100R 0402 differential | Far-end LVDS termination |
| +3V3 - GND | 10u 0603 + 100n 0402 | Panel logic decoupling at FFC |
| +12V - GND | 10u 0603 | Backlight bulk decoupling |
| EDID_SDA/SCL | 4k7 0402 to +3V3 | EDID I2C pull-ups |
| BL_EN | 100k 0402 to GND | Default-off backlight pull-down |

## Layout constraints

- LVDS pairs: 100 ohm differential, intra-pair skew under 0.1 mm, inter-pair under 1 mm.
- Place LVDS terminations within 5 mm of the connector on the receiver side.
- Reference all LVDS pairs to an unbroken GND plane; no plane splits beneath pairs.
- Separate +12V backlight power from +3V3 logic supply (different layers if possible) to avoid PWM noise.

## Carrier usage

Block: `lvds_lcd` (1 instance). Drives a single-link 4-lane LVDS panel from Zynq PL bank 13 at 350 mV LVDS_25. Backlight controlled by `ZYNQ_LCD_BL_EN` + PWM dimming on `ZYNQ_LCD_PWM`. EDID I2C exposed to PS firmware for panel identification.
