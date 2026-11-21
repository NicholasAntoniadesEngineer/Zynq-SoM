# can_bus

CAN bus port: TCAN1042HGV transceiver (70 V bus fault), switched 120R termination, two daisy-chain connectors.

The design rationale, the datasheet basis of every value and the test method are in the board study `README.md` of the motor-control carrier. This file lists the interface and the parts.

## Interface

- `+5V`
- `+3V3`
- `GND`
- `GND_BUS`
- `CAN_TX`
- `CAN_RX`

## Parts

| ref | value | part or symbol | LCSC |
|---|---|---|---|
| U1 | TCAN1042HGVDR | TCAN1042HGVDR | catalogue |
| C2 | 100n | Device:C | C14663 |
| C1 | 100n | Device:C | C14663 |
| R1 | 10k | Device:R | C25804 |
| R2 | 120R | Device:R | C22787 |
| SW1 | DIP-4 | DSHP04TSGER | catalogue |
| D1 | NUP2105LT1G | NUP2105LT1G | catalogue |
| J1 | ZX-SH1.0-4PWT | ZX-SH1.0-4PWT | catalogue |
| J2 | ZX-SH1.0-4PWT | ZX-SH1.0-4PWT | catalogue |
| TP1 | CAN_H | Connector:TestPoint | - |
| TP2 | CAN_L | Connector:TestPoint | - |
