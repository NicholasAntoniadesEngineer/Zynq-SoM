# DS3231 - Extremely Accurate I2C RTC/TCXO

Analog Devices (formerly Maxim) DS3231SN# - precision RTC with integrated TCXO and crystal (no external crystal load caps needed). +/- 2 ppm accuracy from 0-40 deg C, battery-backed timekeeping via CR1220 / CR2032 coin cell.

The local datasheet is the Adafruit DS3231 Precision RTC breakout learn-guide bundle (2024-06-03) - it contains the official Analog Devices electrical / pinout summary plus a full reference schematic of a working breakout, which is what the refcircuit follows.

## Pin assignment

| Pin | Net | Notes |
|---|---|---|
| 1 | 32kHz | 32.768 kHz square-wave output (open-drain) |
| 2 | VCC | +3V3 supply (2.3-5.5 V range) |
| 3 | INT/SQW | Alarm interrupt or 1 Hz output (open-drain) |
| 4 | RST_N | Power-fail / reset output (open-drain, internal 50k pull-up) |
| 5-12 | N.C. | Tie directly to GND per datasheet |
| 13 | GND | |
| 14 | VBAT | Backup battery input (direct to CR2032, no dropper R) |
| 15 | SDA | I2C data |
| 16 | SCL | I2C clock |

I2C slave address (factory-fixed): **0x68**. No external strap pins.

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| VCC - GND | 100n 0402 X7R | VCC decoupling (Adafruit ref schematic) |
| VBAT - GND | CR2032 holder | Primary cell - direct connection, NO current-limit R |
| VBAT - GND | 100n 0402 X7R | Decoupling against long-trace noise |
| SDA / SCL | 4k7 0402 to +3V3 | I2C pull-ups (shared bus) |
| 32kHz | 10k 0402 to +3V3 | Open-drain output pull-up |
| INT/SQW | 10k 0402 to +3V3 | Open-drain output pull-up |

Note: **RST_N already has an internal 50k pull-up** (datasheet) - no external pull-up required. The chip's trickle charger is disabled by default; CR2032 is a primary cell and cannot be charged.

## Layout constraints

- Place the 0.1 uF VCC bypass within 5 mm of pin 2.
- Keep the VBAT trace short and quiet - no switching signals should cross it.
- Tie pins 5-12 directly to the GND plane (single via per pin).
- Avoid placing high-current switching regulators within 10 mm of the DS3231 - the internal TCXO is temperature-sensitive.

## Carrier usage

Catalog instance count: 1 (per `IC_INSTANCE_COUNT`). Provides battery-backed real-time clock on the carrier's I2C management bus (shared with INA226 power monitors and on-board EEPROMs). The accompanying CR2032 holder is the only physical battery on the carrier.
