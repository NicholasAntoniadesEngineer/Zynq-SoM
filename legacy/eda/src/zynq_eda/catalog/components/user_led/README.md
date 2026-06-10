# User LED - YONGYUTAI YLED0603G

Green 0603 SMD chip LED used as user-facing status indicator (boot LEDs, heartbeat, fault, etc.). Vf 2.6-3.2 V @ 5 mA, lambda 510-531 nm, 173-358 mcd.

## Pin assignment

| Pin | Net | Notes |
|---|---|---|
| 1 (Anode) | Driven via 330R series resistor from host GPIO | |
| 2 (Cathode) | GND | |

## External parts (per refcircuit)

| Net | Component | Justification |
|---|---|---|
| ANODE -> GPIO | 330R 0402 1% | Limit If to 1.2-2.1 mA at Vf 2.9-2.6 V from 3.3 V GPIO |

Series-resistor sizing:
- I @ Vf_max (3.2 V): (3.3 - 3.2) / 330 = 0.3 mA (worst-case binning, low)
- I @ Vf_typ (2.9 V): (3.3 - 2.9) / 330 = 1.2 mA
- I @ Vf_min (2.6 V): (3.3 - 2.6) / 330 = 2.1 mA

Well within Zynq PL LVCMOS33 sink limit (~12 mA per pin) and bright enough indoors at 173 mcd minimum.

## Layout constraints

- Place series resistor right next to the LED on the same layer; keep GPIO trace direct.
- Orient LED with anode (marked side) toward the series resistor.
- Add silkscreen labelling (e.g. `D1 - HEARTBEAT`).
- For LED indicator bars, match spacing across all LEDs (e.g. 2 mm pitch).

## Carrier usage

Catalog instance count: 4 (per `IC_INSTANCE_COUNT`). Reserved for board-status indicators - heartbeat, power-good, fault, and user-defined LEDs - placed by the parent block (no dedicated `user_led` block; LEDs are instanced as `IcInstance`s inside the carrier's status / heartbeat block).
