# 24LC256T-I/SN - HDMI DDC EDID EEPROM

Microchip 24LC256T-I/SN (SOIC-8, LCSC C5458), strapped for the HDMI
DDC bus at +5V on the HDMI-TX port. The HDMI 1.4 spec (Sec 8.1.4) and
VESA E-DDC (Sec 2.2.5) mandate that the EDID ROM responds to I2C
address 0xA0/0xA1 (7-bit 0x50) — so this part shares the same silicon
as `components/eeprom_24lc256` but with all address straps grounded
and a different supply rail.

Datasheet (in this folder): Microchip DS21203P, 2007.

## Rails

| Rail  | Pin       | Direction | Notes                                                       |
|-------|-----------|-----------|-------------------------------------------------------------|
| `+5V` | VCC (8)   | input     | Same +5V node as TPD12S016 5V_OUT (TX role) to share DDC pull-ups|
| `GND` | VSS (4)   | -         | System ground (HDMI DDC/CEC ground at connector pin 17)     |

## Key external parts

Per DS Section 2.0 + HDMI 1.4 Sec 8.1:

| From pin | To net | Part token        | Qty | Why                                              |
|----------|--------|-------------------|-----|--------------------------------------------------|
| VCC      | GND    | `100n_0402_X7R`   | 1   | V_CC decoupling within 5mm of pin 8              |

NO external SDA/SCL pull-ups: TPD12S016 SDA_B and SCL_B have
internal 1.75k pull-ups to 5V_OUT (TPD12S016 DS Sec 7.1). Adding
external 2.2k would parallel down to ~970 ohm, below the 1.6k HDMI
1.4 DDC minimum-sink impedance.

I2C straps (HDMI 1.4 Sec 8.1.4 + VESA E-DDC):

| Strap pin | Tied to | Result                                                |
|-----------|---------|-------------------------------------------------------|
| A0        | GND     | A0 = 0                                                |
| A1        | GND     | A1 = 0                                                |
| A2        | GND     | A2 = 0 (full 7-bit EDID addr 0x50; control 0xA0/0xA1) |
| WP        | GND     | Write protect disabled (Zynq PS writes EDID at boot)  |

## Layout constraints

* Place the EEPROM on the HDMI cable side of TPD12S016, between
  TPD12S016 SDA_B/SCL_B and HDMI connector pins 15/16.
* Route DDC SDA/SCL traces <= 20mm with V_CC decoupling within 5mm of
  pin 8 to stay within the HDMI 1.4 DDC capacitive-load budget.
* EDID EEPROM V_CC MUST come from the same +5V node that supplies
  TPD12S016 5V_OUT in the TX role — that ensures the DDC pull-ups
  and the EEPROM share a single 5V reference and the EEPROM's bus
  goes high-Z cleanly when the source disables 5V_OUT.

## Carrier usage

* `blocks/hdmi_tx.py` instantiates one 24LC256 EDID EEPROM on the
  DDC bus between TPD12S016_TX's SDA_B/SCL_B and HDMI connector pins
  15/16. The Zynq PS firmware programs an EDID payload (typically
  256-512 bytes) at first boot via the controller-side DDC bus
  (translated through the TPD12S016 to the +5V cable-side).
