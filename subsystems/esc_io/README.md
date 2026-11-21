# esc_io

8-ch ESC signal interface: 5 V PWM/DShot drive, read-back, idle bias, telemetry input.

The design rationale, the datasheet basis of every value and the test method are in the board study `README.md` of the motor-control carrier. This file lists the interface and the parts.

## Interface

- `+5V`
- `PWR_REQ`
- `PWR_EN`
- `+3V3`
- `GND`
- `GND_ESC`
- `OE_N`
- `OE_SENSE_N`
- `PWM_IN0`
- `FB0`
- `PWM_IN1`
- `FB1`
- `PWM_IN2`
- `FB2`
- `PWM_IN3`
- `FB3`
- `PWM_IN4`
- `FB4`
- `PWM_IN5`
- `FB5`
- `PWM_IN6`
- `FB6`
- `PWM_IN7`
- `FB7`
- `IDLE_SEL`
- `+5V_SERVO`
- `TLM_RX`

## Parts

| ref | value | part or symbol | LCSC |
|---|---|---|---|
| U1 | SN74HCT245PWR | SN74HCT245PWR | catalogue |
| C1 | 100n | Device:C | C14663 |
| R1 | 10k | Device:R | C25804 |
| SW1 | DIP-4 | DSHP04TSGER | catalogue |
| RN1 | 4D03WGJ0330T5E | 4D03WGJ0330T5E | catalogue |
| RN2 | 4D03WGJ0330T5E | 4D03WGJ0330T5E | catalogue |
| J1 | HX_PZ2.54-3x8P_ZZ | HX_PZ2.54-3x8P_ZZ | catalogue |
| D1 | SRV05-4 | Power_Protection:SRV05-4 | C2836319 |
| D2 | SRV05-4 | Power_Protection:SRV05-4 | C2836319 |
| U3 | SY6280AAC | SY6280AAC | catalogue |
| R2 | 13k | Device:R | C22797 |
| C2 | 10u | Device:C | C15850 |
| C3 | 10u | Device:C | C15850 |
| R3 | 100k | Device:R | C25803 |
| U4 | SN74LVC125ADR | SN74LVC125ADR | catalogue |
| U5 | SN74LVC125ADR | SN74LVC125ADR | catalogue |
| C4 | 100n | Device:C | C14663 |
| C5 | 100n | Device:C | C14663 |
| R4 | 10k | Device:R | C25804 |
| R5 | 10k | Device:R | C25804 |
| R6 | 10k | Device:R | C25804 |
| R7 | 10k | Device:R | C25804 |
| R8 | 10k | Device:R | C25804 |
| R9 | 10k | Device:R | C25804 |
| R10 | 10k | Device:R | C25804 |
| R11 | 10k | Device:R | C25804 |
| U6 | SN74LVC1G08 | 74xGxx:74LVC1G08 | C7666 |
| R12 | 100k | Device:R | C25803 |
| C6 | 100n | Device:C | C14663 |
| J2 | ZX-SH1.0-4PWT | ZX-SH1.0-4PWT | catalogue |
| R13 | 1k | Device:R | C21190 |
| R14 | 10k | Device:R | C25804 |
| D3 | SRV05-4 | Power_Protection:SRV05-4 | C2836319 |
| U7 | SN74LVC1G08 | 74xGxx:74LVC1G08 | C7666 |
| C7 | 100n | Device:C | C14663 |
| D4 | blue | Device:LED | C2288 |
| R16 | 1k | Device:R | C21190 |
| R15 | 10k | Device:R | C25804 |
| TP1 | +5V_SERVO | Connector:TestPoint | - |
| TP2 | ESC_BIAS | Connector:TestPoint | - |
| TP3 | OE_BUF_N | Connector:TestPoint | - |
