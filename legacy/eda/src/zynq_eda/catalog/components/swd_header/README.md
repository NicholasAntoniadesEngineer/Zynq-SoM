# SWD header - HANXIA HX-PZ1.27-2x5P-TP

2x5 (10-position) 1.27 mm pitch through-hole male pin header following the ARM Cortex Debug Connector standard (ARM Debug Interface v5.2). Used to expose the carrier's STM32 power-controller MCU's SWD interface.

## Pin assignment (ARM Cortex Debug Connector, 10-pin SWD subset)

| Pin | Net | Notes |
|---|---|---|
| 1 | +3V3 (VTREF) | Target I/O reference voltage |
| 2 | SWDIO | Serial wire data (bidirectional) |
| 3 | GND | |
| 4 | SWCLK | Serial wire clock (host -> target) |
| 5 | GND | |
| 6 | SWO | SWO trace output (target -> host) |
| 7 | KEY | Mechanically blanked (no electrical connection) |
| 8 | NC / TDI | NC for pure SWD |
| 9 | GNDDetect | GND (target-present sense) |
| 10 | nRESET | Target reset (open-drain) |

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| SWDIO | 10k 0402 to +3V3 | ARM ADI v5.2: SWDIO target-side pull-up to VTREF |
| nRESET | 10k 0402 to +3V3 | nRESET pull-up: target boots normally when debugger is removed |
| nRESET | 100n 0402 to GND | Debounce against probe glitches (ST AN2606) |

## Layout constraints

- Place 10k SWDIO and nRESET pull-ups within 10 mm of the header.
- SWD trace length under 50 mm; signals run at up to 10 MHz.
- Pin 7 (KEY) must remain mechanically blanked.
- Route SWD signals away from LVDS LCD and HDMI clocks - SWD probes are unshielded.

## Carrier usage

Block: `jtag_swd` (1 instance, J2). Exposes `STM32_SWDIO`, `STM32_SWCLK`, `STM32_NRST` for J-Link / ST-Link debug of the on-carrier STM32 power-controller MCU.
