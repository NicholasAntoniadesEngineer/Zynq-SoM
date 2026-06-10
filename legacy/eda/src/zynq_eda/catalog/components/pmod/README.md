# PMOD header - XFCN PM254R-12-08-H85

Digilent-standard 2x6 (12-position) right-angle female pin header on 2.54 mm pitch. Pure mechanical part; PMOD daughtercards carry any required active circuitry.

## Pin assignment (Digilent PMOD Type 1A)

| Pin | Net | Notes |
|---|---|---|
| 1 | PMODn_IO0 | GPIO (3.3 V LVCMOS) |
| 2 | PMODn_IO1 | GPIO |
| 3 | PMODn_IO2 | GPIO |
| 4 | PMODn_IO3 | GPIO |
| 5 | GND | |
| 6 | +3V3 | 1 A max per PMOD |
| 7 | PMODn_IO4 | GPIO |
| 8 | PMODn_IO5 | GPIO |
| 9 | PMODn_IO6 | GPIO |
| 10 | PMODn_IO7 | GPIO |
| 11 | GND | |
| 12 | +3V3 | |

## External parts

None at the connector itself - PMOD daughtercards own their level translation, buffering, and pull-ups. The PMOD refcircuit declares an empty `external_parts` and the audit explicitly allows that via `_ZERO_EXTERNAL_ALLOWED` in `audit.py`.

## Layout constraints

- 3.3 V LVCMOS only - do **not** drive 5 V into PMOD pins.
- Series-terminate (33 ohm) at the SoM end for clocks >= 25 MHz (Digilent PMOD Spec Sec 4).
- Place PMOD connectors edge-aligned with the carrier outline so daughtercards fold cleanly off the board.

## Carrier usage

Block: `pmod` (2 instances - J1 / J2). Each PMOD has 8 GPIOs routed via Zynq PL bank 35 through the SoM J3 mate. Slot index 0 corresponds to PMOD0, slot index 1 to PMOD1.
