# pl_expansion

PL expansion header: 32 spare bank IO on 2x20 2.54 mm, current-limited 3.3 V.

The design rationale, the datasheet basis of every value and the test method are in the board study `README.md` of the motor-control carrier. This file lists the interface and the parts.

## Interface

- `+3V3`
- `+3V3_XIO`
- `GND`
- `XIO1`
- `XIO2`
- `XIO3`
- `XIO4`
- `XIO5`
- `XIO6`
- `XIO7`
- `XIO8`
- `XIO9`
- `XIO10`
- `XIO11`
- `XIO12`
- `XIO13`
- `XIO14`
- `XIO15`
- `XIO16`
- `XIO17`
- `XIO18`
- `XIO19`
- `XIO20`
- `XIO21`
- `XIO22`
- `XIO23`
- `XIO24`
- `XIO25`
- `XIO26`
- `XIO27`
- `XIO28`
- `XIO29`
- `XIO30`
- `XIO31`
- `XIO32`

## Parts

| ref | value | part or symbol | LCSC |
|---|---|---|---|
| J1 | HX PZ2.54-2x20P ZZ | Connector_Generic:Conn_02x20_Odd_Even | C42372528 |
| U1 | SY6280AAC | SY6280AAC | catalogue |
| R1 | 13k | Device:R | C22797 |
| C1 | 100n | Device:C | C14663 |
| C2 | 10u | Device:C | C15850 |
| TP1 | +3V3_XIO | Connector:TestPoint | - |
