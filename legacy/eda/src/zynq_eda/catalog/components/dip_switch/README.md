# DIP switch - HANBO DS-04P

4-position SPST DIP switch on 1.27 mm pitch SMD package. Each switch has two solder pads (top + bottom); flipping the slide ON shorts the top pad to the bottom pad.

## Pin assignment

| Pin | Net | Notes |
|---|---|---|
| 1 | SW1 (BOOT_MODE_0) | Top pad - drives boot strap bit 0 |
| 2 | GND | Bottom pad of switch 1 |
| 3 | SW2 (BOOT_MODE_1) | Top pad - drives boot strap bit 1 |
| 4 | GND | Bottom pad of switch 2 |
| 5 | SW3 (BOOT_MODE_2) | Top pad - drives boot strap bit 2 |
| 6 | GND | Bottom pad of switch 3 |
| 7 | SW4 (BOOT_MODE_3) | Top pad - drives boot strap bit 3 |
| 8 | GND | Bottom pad of switch 4 |

Electrical rating: 100 mA / 50 V DC (non-switching), 25 mA / 24 V DC (switching). 1000 mechanical cycles.

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| SW1..SW4 | 10k 0402 to +3V3 | Zynq-7000 TRM Sec 6.3.6: strap pull-up (>= 4.7k, <= 20k) |

## Layout constraints

- Place 10k pull-ups within 10 mm of the DIP switch so the strap network is short.
- Provide silkscreen labelling (1 / 2 / 3 / 4 and ON marking) so boot mode is visible without instructions.
- Route strap traces to the SoM J1 mate via short, direct paths; do not loop or share vias with other PS signals.
- Boot straps are latched only at PS_POR_B release - not hot-swappable. Document in user guide.

## Carrier usage

Catalog instance count: 1 (per `IC_INSTANCE_COUNT`). Block `boot_switches` (1 instance, SW1) drives the Zynq PS `BOOT_MODE[3:0]` strap pins via the SoM J1 mate, selecting the boot source (QSPI / NAND / SD / JTAG) at power-on.
