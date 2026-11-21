# esc_power

ESC power path: XT60 in/out, fuse, reverse/inrush/over-current protection, shunt, INA237 (0x44), star tie.

The design rationale, the datasheet basis of every value and the test method are in the board study `README.md` of the motor-control carrier. This file lists the interface and the parts.

## Interface

- `+VBAT_RAW`
- `+VBAT_F`
- `+VBAT_MID`
- `+VBAT_P`
- `+VBAT_OUT`
- `GND_PWR`
- `GND`
- `+VDD_MON`
- `IMON`
- `PWR_EN`
- `PWR_FLT_N`
- `VBAT_SENSE`
- `I2C_SDA`
- `I2C_SCL`
- `ALERT_N`

## Parts

| ref | value | part or symbol | LCSC |
|---|---|---|---|
| J1 | XT60PW-M | XT60PW-M | catalogue |
| J2 | XT60PW-M | XT60PW-M | catalogue |
| F1 | 40A | 0456040.DR | catalogue |
| D1 | SMBJ28A | SMBJ28A | catalogue |
| D2 | SMBJ28A | SMBJ28A | catalogue |
| C1 | 100n/100V | Device:C | C15725 |
| Q1 | IPT007N06N | IPT007N06N | catalogue |
| Q2 | IPT007N06N | IPT007N06N | catalogue |
| U2 | LM74930QRGERQ1 | LM74930QRGERQ1 | catalogue |
| D3 | SS54 | Device:D_Schottky | C22452 |
| C6 | 100n/100V | Device:C | C15725 |
| C7 | 1u | Device:C | C15849 |
| R4 | 100R | Device:R | C22775 |
| C8 | 1u/100V | Device:C | C282823 |
| R5 | 49.9R | Device:R | C114625 |
| R6 | 4k7 | Device:R | C23162 |
| R7 | 15k | Device:R | C22809 |
| C9 | 1u | Device:C | C15849 |
| R8 | 4k7 | Device:R | C23162 |
| R9 | 10k | Device:R | C25804 |
| R10 | 10k | Device:R | C25804 |
| R11 | 100k | Device:R | C25803 |
| R12 | 100k | Device:R | C25803 |
| R13 | 10k | Device:R | C25804 |
| C10 | 100n | Device:C | C14663 |
| R14 | 10k | Device:R | C25804 |
| RS1 | 0.5mR | RLM25FEGMR50M | catalogue |
| U1 | INA237AIDGSR | INA237AIDGSR | catalogue |
| C2 | 100n | Device:C | C14663 |
| R1 | 10k | Device:R | C25804 |
| C3 | 470u | RVT1H471M1213 | catalogue |
| C4 | 470u | RVT1H471M1213 | catalogue |
| C5 | 100n/100V | Device:C | C15725 |
| RT1 | 0.5mR | RLM25FEGMR50M | catalogue |
| D4 | red | Device:LED | C2286 |
| R2 | 5.1k | Device:R | C23186 |
| R3 | 5.1k | Device:R | C23186 |
| C11 | 100n/100V | Device:C | C15725 |
| TP1 | +VBAT_RAW | Connector:TestPoint | - |
| TP2 | +VBAT_OUT | Connector:TestPoint | - |
| TP3 | GND_PWR | Connector:TestPoint | - |
| TP4 | GND | Connector:TestPoint | - |
| TP5 | +VBAT_F | Connector:TestPoint | - |
| TP6 | +VBAT_MID | Connector:TestPoint | - |
| TP7 | +VBAT_P | Connector:TestPoint | - |
| TP8 | PWR_EN | Connector:TestPoint | - |
| TP9 | PROT_IMON | Connector:TestPoint | - |
| TP10 | VSENSE_DIV | Connector:TestPoint | - |
