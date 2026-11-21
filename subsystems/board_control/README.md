# board_control

Board control: rail DIP, TCA9535 status expander (I2C 0x20), user LEDs and button, PUDC strap.

The design rationale, the datasheet basis of every value and the test method are in the board study `README.md` of the motor-control carrier. This file lists the interface and the parts.

## Interface

- `+3V3_SC`
- `+3V3`
- `GND`
- `I2C_SCL`
- `I2C_SDA`
- `INT_N`
- `DIP_5V0`
- `DIP_3V3`
- `DIP_1V8`
- `FLT_PD_N`
- `ALERT_PMON_N`
- `FLT_BAT_N`
- `ALERT_ESC_N`
- `OE_SENSE_N`
- `PUDC`
- `PWR_REQ`
- `PWR_FLT_N`
- `+5V`
- `+5V_FAN`
- `FAN_PWM`
- `FAN_TACH`

## Parts

| ref | value | part or symbol | LCSC |
|---|---|---|---|
| SW1 | DIP-4 | DSHP04TSGER | catalogue |
| U1 | TCA9535PWR | TCA9535PWR | catalogue |
| C1 | 100n | Device:C | C14663 |
| R1 | 4k7 | Device:R | C23162 |
| R2 | 4k7 | Device:R | C23162 |
| R3 | 10k | Device:R | C25804 |
| R4 | 100k | Device:R | C25803 |
| D1 | green | Device:LED | C12624 |
| D2 | red | Device:LED | C2286 |
| R5 | 1k | Device:R | C21190 |
| R6 | 1k | Device:R | C21190 |
| SW2 | USER | TS-1187A-B-A-B | catalogue |
| R7 | 10k | Device:R | C25804 |
| R8 | 1k | Device:R | C21190 |
| R9 | 100k | Device:R | C25803 |
| TP1 | XP16 | Connector:TestPoint | - |
| TP2 | XP17 | Connector:TestPoint | - |
| U2 | SY6280AAC | SY6280AAC | catalogue |
| Q1 | AO3400A | AO3400A | catalogue |
| J1 | ZX-SH1.0-4PWT | ZX-SH1.0-4PWT | catalogue |
| R10 | 13k | Device:R | C22797 |
| C2 | 10u | Device:C | C15850 |
| C3 | 10u | Device:C | C15850 |
| R11 | 100k | Device:R | C25803 |
| R12 | 10k | Device:R | C25804 |
| R13 | 1k | Device:R | C21190 |
| TP10 | +5V_FAN | Connector:TestPoint | - |
| TP11 | PWR_REQ | Connector:TestPoint | - |
| TP5 | I2C_SCL | Connector:TestPoint | - |
| TP6 | I2C_SDA | Connector:TestPoint | - |
| TP7 | +3V3_SC | Connector:TestPoint | - |
| TP8 | INT_N | Connector:TestPoint | - |
| TP9 | PUDC | Connector:TestPoint | - |
