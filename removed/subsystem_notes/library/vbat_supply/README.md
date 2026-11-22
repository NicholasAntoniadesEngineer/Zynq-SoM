# vbat_supply

Battery logic feed: TPS26631 eFuse + LM61460 8 V pre-regulator + supply selector.

The design rationale, the datasheet basis of every value and the test method are in the board study `README.md` of the motor-control carrier. This file lists the interface and the parts.

## Interface

- `+VBAT`
- `+VBAT_D`
- `FLT_N`
- `+VDD_LOGIC`
- `+VBAT_SW`
- `GND`
- `+VPRE`
- `+VIN_USB`
- `+VIN`

## Parts

| ref | value | part or symbol | LCSC |
|---|---|---|---|
| U1 | TPS26631PWPR | TPS26631PWPR | catalogue |
| D2 | SS54 | Device:D_Schottky | C22452 |
| C13 | 4u7/100V | Device:C | C49451356 |
| C14 | 470u | RVT1H471M1213 | catalogue |
| R1 | 100k | Device:R | C25803 |
| R2 | 10k | Device:R | C25804 |
| R3 | 5.1k | Device:R | C23186 |
| R4 | 5.49k | Device:R | C188263 |
| C1 | 47n | Device:C | C1622 |
| R5 | 100k | Device:R | C25803 |
| C2 | 100n/100V | Device:C | C15725 |
| C3 | 4u7/100V | Device:C | C49451356 |
| C4 | 4u7/100V | Device:C | C49451356 |
| C5 | 100n/100V | Device:C | C15725 |
| C6 | 100n/100V | Device:C | C15725 |
| U2 | LM61460AANRJRR | LM61460AANRJRR | catalogue |
| C7 | 1u | Device:C | C15849 |
| R6 | 10R | Device:R | C22859 |
| C8 | 1u | Device:C | C15849 |
| R7 | 22k | Device:R | C31850 |
| C9 | 100n | Device:C | C14663 |
| L1 | 10uH | Device:L | C37429 |
| C10 | 22u | Device:C | C45783 |
| C11 | 22u | Device:C | C45783 |
| R8 | 47.5k | Device:R | C23061 |
| R9 | 6.8k | Device:R | C23212 |
| C12 | 22p | Device:C | C1653 |
| R10 | 1k | Device:R | C21190 |
| D1 | red | Device:LED | C2286 |
| R11 | 1k | Device:R | C21190 |
| J1 | A2541WV-2x3P | Connector_Generic:Conn_02x03_Odd_Even | C225518 |
| TP1 | +VBAT_SW | Connector:TestPoint | - |
| TP2 | +VPRE | Connector:TestPoint | - |
| TP3 | +VIN | Connector:TestPoint | - |
| TP4 | +VBAT_D | Connector:TestPoint | - |
