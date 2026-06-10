# FMC LPC connector - Hirose FX10A-168P-SV(91)

168-position 0.5 mm stacking connector used as the carrier-side mate to the SoM. The carrier projects the **VITA 57.1 LPC FMC** pinout on top of the FX10A so off-the-shelf FMC LPC daughtercards plug into the same connector that the SoM stacks onto.

## Pin assignment (subset, see `projects/carrier/blocks/fmc_lpc.py` for the full VITA 57.1 LPC map)

| VITA LPC pin | Net | Notes |
|---|---|---|
| C30 / C31 | FMC_SCL / FMC_SDA | Management I2C (3.3 V open-drain) |
| C35, C37 | +12V | Carrier-sourced power |
| C36/38/40, D35/37/39 | +VADJ | Bank voltage (carrier ties to +1V8) |
| C39, D36/38/40 | +3V3 | Auxiliary supply |
| H2 | FMC_PRSNT_N | Daughtercard present (pulled high by carrier) |
| G6..G37, D8..D33, C10..C27, H7..H38 | LA00..LA33 P/N | 34 LA pairs (single-ended or LVDS) |
| H4/H5, G2/G3 | CLK0/CLK1 M2C P/N | Clock pairs from daughtercard to carrier |
| D29..D33 | JTAG passthrough | TCK / TMS / TDI / TDO / TRST_N |
| Cn, Dn, Gn, Hn (alternating) | GND | Per VITA 57.1 |

## External parts (per refcircuit)

| Net | Component | Quantity | Justification |
|---|---|---|---|
| +3V3 - GND | 100n 0402 X7R | 4 | One per +3V3 pin (VITA 57.1 Sec 5.3) |
| +VADJ - GND | 100n 0402 X7R | 6 | One per VADJ pin |
| +12V - GND | 100n 0402 X7R | 2 | One per +12V pin |
| +3V3 - GND | 10u 0603 X7R | 1 | Bulk decoupling |
| +VADJ - GND | 10u 0603 X7R | 1 | Bulk decoupling |
| FMC_SCL/SDA | 4k7 0402 to +3V3 | 2 | Management I2C pull-ups |
| FMC_PRSNT_N | 10k 0402 to +3V3 | 1 | Present-detect pull-up |

## Layout constraints

- Decouple every VCC/VADJ pin group within 3 mm of the connector body.
- LA pairs: 100 ohm differential, intra-pair skew under 0.1 mm, inter-pair under 1 mm.
- CLK0/CLK1 M2C pairs: 100 ohm differential, length <= 50 mm, no layer changes.
- VADJ is hard-tied to +1V8 on this carrier (no auto-negotiation).
- Multiple GND vias under the connector body for high-speed return current.

## Carrier usage

Block: `fmc_lpc` (1 instance). Provides the carrier's FMC LPC expansion socket - daughtercards (FMC-ADC, FMC-DAC, etc.) plug onto the carrier and consume +12V/+3V3/+VADJ + 34 LA pairs + 4 clock pairs via Zynq PL bank 13 through the SoM J2 mate.
