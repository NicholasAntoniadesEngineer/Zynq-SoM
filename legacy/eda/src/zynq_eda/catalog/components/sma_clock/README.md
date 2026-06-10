# SMA clock - Kinghelm KH-SMA-P-8496

SMA female PCB right-angle 50 ohm connector for external clock input to the Zynq XADC or PL MRCC clock-capable pin.

## Pin assignment

| Pin | Net | Notes |
|---|---|---|
| CENTER | XADC_CLK_AC (AC-coupled side) | 50 ohm signal path through 10 nF cap |
| SHELL / lugs | GND | Coax shield + mechanical mounting |

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| CENTER -> XADC_CLK_AC | 10n 0402 X7R series | UG480 / AR# 53353: AC coupling for external clock |
| XADC_CLK_AC - GND | 49R9 0402 1% | 50 ohm parallel termination (closest E96 to 50 ohm) |

(For sine-wave or sub-MHz sources, swap 10 nF for 100 nF and add a 1.65 V mid-rail bias divider downstream of the termination - left unpopulated by default for CMOS sources.)

## Layout constraints

- 50 ohm controlled-impedance microstrip from connector to XADC pin; continuous GND reference.
- AC-coupling cap and termination resistor within 5 mm of the SMA centre pin.
- All four mechanical lugs to GND with short, low-inductance traces.
- Avoid 90 degree corners on the signal trace - use 45 degree turns or smooth curves.

## Carrier usage

Catalog instance count: 2 (per `IC_INSTANCE_COUNT` in `components/__init__.py`). Reserved for future use as external clock input to the Zynq XADC and/or PL MRCC pins. The carrier blocks do not currently place an `SMA_CLOCK` instance in the schematic; the refcircuit is staged for the next-iteration clocking block.
