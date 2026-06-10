# Tactile switch - XUNPU TS-1002S-06026C

6 x 6 mm SMD momentary push-button (4-pin metal dome). Pads 1+2 are electrically common, pads 3+4 are electrically common; pressing the button shorts the two pairs.

## Pin assignment

| Pin | Net | Notes |
|---|---|---|
| 1, 2 | SW | One terminal (electrically common) |
| 3, 4 | GND | Other terminal (electrically common) |

Electrical rating: 50 mA / 12 V DC, 100k mechanical cycles.

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| SW | 10k 0402 to +3V3 | Pull-up - button shorts SW to GND when pressed |
| SW - GND | 100n 0402 X7R | Hardware debounce (RC ~ 1 ms with 10k pull-up) + ESD shunt |

## Layout constraints

- Place the 100 nF debounce cap within 5 mm of the switch so the RC network sees the bounce node directly.
- Position the switch on the carrier edge or top side for user access; provide silkscreen labelling.
- Route the GPIO trace from switch to host SoM as a short, low-impedance signal; avoid running parallel to clocks (tactile switches are ESD entry points).

## Carrier usage

Catalog instance count: 4 (per `IC_INSTANCE_COUNT`). Block `boot_switches` (1 instance, SW2) uses it as the active-low PS reset push-button (`ZYNQ_PS_SRST_N`). Three additional instances are reserved for user-defined input keys (mapped in carrier blocks but not yet wired).
