# JTAG header - Megastar ZX-PM2.54-2-7PY

2x7 (14-position) 2.54 mm pitch through-hole male pin header following the Xilinx Platform Cable USB / DLC9LP pinout (UG470).

## Pin assignment (Xilinx 14-pin JTAG header)

| Pin | Net | Notes |
|---|---|---|
| 1 | +3V3 (VREF) | Host I/O reference voltage |
| 2 | TMS | Test mode select |
| 3 | GND | |
| 4 | TCK | Test clock (host -> DUT) |
| 5 | GND | |
| 6 | TDO | Test data out (DUT -> host) |
| 7 | GND | |
| 8 | TDI | Test data in (host -> DUT) |
| 9 | GND | |
| 10-14 | N.C. | Unused on this carrier |

(KiCad symbol collapses the redundant GND pins; the block sheet exposes VCC/TDI/GND/TMS/TCK/TDO.)

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| TMS | 10k 0402 to +3V3 | IEEE 1149.1 TMS pull-up (TAP -> Test-Logic-Reset when probe is absent) |
| TDI | 10k 0402 to +3V3 | IEEE 1149.1 TDI pull-up |
| TCK | 22R 0402 series | Optional damping resistor (UG470 Sec 3) |

## Layout constraints

- Keep all JTAG traces under 50 mm; isolate from PS clocks (memory clock, USB ref clock) by 10+ mm.
- Place 10k pull-ups on TMS and TDI within 5 mm of the header.
- Pin 1 (VREF) clearly marked - incorrect cable orientation drives 3.3 V into TDO.
- Stitch header GND pins to the carrier GND plane with multiple vias for TCK return-current control.

## Carrier usage

Block: `jtag_swd` (1 instance, J1). Routes the Zynq PS JTAG signals (`ZYNQ_PS_JTAG_*`) directly to the SoM J1 mate. Use case: Xilinx programming cables (Platform Cable USB II, JTAG-SMT2-NC) attach here for PS-side debug and bitstream load.
