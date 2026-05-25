# 24LC256T-I/SN - 256-Kbit I2C EEPROM (board ID role)

Microchip 24LC256T-I/SN (SOIC-8, LCSC C5458), strapped as the board-ID
/ persistent-config EEPROM on the carrier's system I2C bus at +3V3.

A sibling folder (`components/eeprom_24lc256_edid`) reuses the same
silicon strapped for the HDMI DDC bus at +5V (mandatory I2C address
0x50 per HDMI 1.4 EDID).

Datasheet (in this folder): Microchip DS21203P, 2007.

## Rails

| Rail   | Pin       | Direction | Notes                                       |
|--------|-----------|-----------|---------------------------------------------|
| `+3V3` | VCC (8)   | input     | 2.5-5.5V range; carrier uses +3V3 system rail|
| `GND`  | VSS (4)   | -         | System ground                                |

## Key external parts

Per DS Section 2.0 (Electrical) and Section 2.2 (SDA pull-up sizing):

| From pin | To net | Part token        | Qty | Why                                              |
|----------|--------|-------------------|-----|--------------------------------------------------|
| VCC      | GND    | `100n_0402_X7R`   | 1   | V_CC decoupling within 5mm of pin 8              |
| SDA      | +3V3   | `4k7_0402_1%`     | 1   | I2C SDA pull-up (one set per bus)                |
| SCL      | +3V3   | `4k7_0402_1%`     | 1   | I2C SCL pull-up (one set per bus)                |

I2C straps (DS Section 5.0, "Device Addressing"):

| Strap pin | Tied to | Result                                                 |
|-----------|---------|--------------------------------------------------------|
| A0        | GND     | Address bit 0 = 0                                      |
| A1        | GND     | Address bit 1 = 0                                      |
| A2        | GND     | Address bit 2 = 0 (full 7-bit slave addr = 0x50)       |
| WP        | GND     | Write protect disabled (Zynq PS can program board ID)  |

## Layout constraints

* Place the 100nF V_CC decoupling within 5mm of pin 8.
* Keep SDA/SCL trace length <= 100mm to stay within the 400 pF total
  bus capacitance budget of the I2C-bus specification.

## Carrier usage

* `blocks/power_mon.py` (or wherever the system I2C bus is rooted) - 
  the EEPROM at I2C 0x50 shares the bus with INA226 power monitors
  and the DS3231 RTC. SDA/SCL are open-drain; only one device on the
  bus needs to supply pull-ups, so this refcircuit's 4k7 pull-ups are
  the canonical bus pull-ups.
