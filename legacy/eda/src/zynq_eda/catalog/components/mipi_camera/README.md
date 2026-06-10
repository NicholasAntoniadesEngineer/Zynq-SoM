# MIPI camera connector - BOOMELE 1.0-15P

15-pin 1.0 mm pitch right-angle SMT FFC receptacle. Mechanically compatible with the Raspberry Pi V1/V2/V3 and HQ camera FFC. The carrier owns the camera I2C pull-ups and the GPIO0 default-reset bias.

## Pin assignment (Raspberry Pi camera-compatible)

| Pin | Net | Notes |
|---|---|---|
| 1, 4, 7, 10 | GND | |
| 2, 3 | CSI_D0 -/+ | MIPI CSI-2 data lane 0 |
| 5, 6 | CSI_D1 -/+ | MIPI CSI-2 data lane 1 |
| 8, 9 | CSI_CLK -/+ | MIPI CSI-2 clock pair |
| 11 | CAM_GPIO0 | Sensor reset (active low) |
| 12 | CAM_GPIO1 | LED strobe / shutter |
| 13 | CAM_SCL | I2C clock |
| 14 | CAM_SDA | I2C data |
| 15 | +3V3 | Sensor analog + I/O supply |

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| VCC_1V8 - GND | 100n 0402 X7R | Sensor 1.8 V I/O bypass (if used by module) |
| VCC_2V8 - GND | 100n 0402 X7R | Sensor analog supply bypass (if used) |
| CAM_SCL | 4k7 0402 to +3V3 | I2C SCL pull-up |
| CAM_SDA | 4k7 0402 to +3V3 | I2C SDA pull-up |
| CAM_GPIO0 | 100k 0402 to GND | Default-reset pull-down |

## Layout constraints

- CSI-2 data and clock pairs: 100 ohm differential, intra-pair skew under 0.05 mm.
- Trace length under 100 mm; unbroken GND reference plane.
- MIPI D-PHY termination is internal to the receiver (Zynq PL DCI or external MIPI PHY) - no external terminating resistors at the FFC.
- Place I2C pull-ups within 10 mm of the connector.

## Carrier usage

Block: `mipi_camera` (1 instance). Receives a 2-lane CSI-2 stream at LVDS_25 into Zynq PL bank 35. I2C addresses the sensor's register file; GPIO0/1 control reset and strobe.
