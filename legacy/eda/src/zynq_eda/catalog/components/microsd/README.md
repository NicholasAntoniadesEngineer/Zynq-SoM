# microSD - Hirose DM3AT-SF-PEJM5

Push-push microSD card socket with mechanical card-detect switch. Used in the carrier's `microsd` block to expose the Zynq PS SD1 controller in 4-bit SDIO mode.

## Pin assignment

| Pin | Net | Notes |
|---|---|---|
| 1 | DAT2 | SDIO data |
| 2 | DAT3 (CD) | SDIO data 3 (also card-internal CD pull-up) |
| 3 | CMD | SDIO command line |
| 4 | VDD | +3V3 card supply |
| 5 | CLK | SDIO clock (host push-pull) |
| 6 | VSS | GND |
| 7 | DAT0 | SDIO data |
| 8 | DAT1 | SDIO data |
| A | DET_A | Mechanical CD switch terminal A (to GND) |
| B | DET_B | Mechanical CD switch terminal B (to host CD_N) |
| SH | SHIELD | Connector metal shield (to GND) |

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| VDD - GND | 4u7 0402 X5R | Bulk decoupling for card-insertion transient (SD Spec Part 1 Sec 6.3) |
| VDD - GND | 100n 0402 X7R | HF bypass |
| DAT0..3, CMD | 10k 0402 to VDD | SDIO pull-ups (SD Spec Part 1 Sec 6.5) |
| CD_SW | 10k 0402 to +3V3 | Card-detect pull-up |

## Layout constraints

- Length-match SDIO_CLK to CMD and DAT[0..3] within 5 mm.
- Keep total signal trace under 50 mm, route as a tight bundle over solid GND.
- Connector metal shield must be tied to the carrier GND plane with via fence.
- Series 22 ohm terminations on each SDIO line are inside the SoM - no carrier-side series Rs.

## Carrier usage

Block: `microsd` (1 instance). Routes the Zynq PS SD1 peripheral (`ZYNQ_SD1_*` nets) and the mechanical card-detect signal `ZYNQ_SD1_CD_N` to the host GPIO.
