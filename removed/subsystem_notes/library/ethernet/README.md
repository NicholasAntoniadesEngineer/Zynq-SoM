# ethernet — HX5008NL 1000BASE-T magnetics + Bob-Smith termination

A project-agnostic, reusable schgen subsystem providing the Pulse HX5008NL single-port
1:1 gigabit Ethernet magnetics module with its media-side Bob-Smith (IEEE 802.3 §40.7.1)
HF common-mode termination. It supplies the transformer isolation between the Zynq-7000
SoM's PHY and the RJ45 jack on the carrier. The RJ45 jack itself is a separate subsystem
(`rj45_connector`); this package owns only the magnetics and the Bob-Smith network and
exposes the media-side pairs as ports for the jack to bind.

## Interface

The subsystem declares its interface as abstract net names and knows nothing about any
consuming board. A project supplies the standard `META` dict (`schgen.core.subsystem.Meta`)
and forwards it to `ethernet.circuit(meta)`.

- `bind` — `{abstract_net: real_board_net}`, renames every externally-visible net in
  place, order-preserving. POWER/GROUND/PORT only; a SIGNAL key, a typo, or a collision is
  a hard `CircuitError`. Binding to the exact names a hand-written sheet uses yields a
  byte-identical emitted sheet.
- `expects` — `{abstract_port: deferral}`, threads a project's linker deferral onto a port
  via `meta.expect_kw`. Used to tell the linker which sheet binds the media-side pairs
  (the `rj45_connector` sheet). Only the P net of a pair is named; the reciprocal N
  inherits the deferral.

With `meta=None` the subsystem keeps its abstract names so `test_ethernet.py` runs offline.

**Rail (GROUND)**

| abstract | meaning |
|----------|---------|
| `CHASSIS_GND` | chassis-ground island, kept separate from any signal GND; the Bob-Smith trunk bypasses to it through the single barrier cap C5. Star-bonded to signal ground by the consuming board. |

**Ports (PORT — all 100 Ω differential pairs)**

| abstract | side | meaning |
|----------|------|---------|
| `MDI0_P/N` … `MDI3_P/N` | CHIP (PHY-facing) | the four 1000BASE-T pairs facing the SoC/PHY; bind to the host PHY's MDI lanes. |
| `MX0_P/N` … `MX3_P/N` | MEDIA (RJ45-facing) | the four pairs facing the RJ45 jack; bind to the `rj45_connector` subsystem via `expects`. |

The 1:1 winding is in phase, so `+` couples to `+` (`MDIn_P ↔ MXn_P`).

`MCT1..MCT4` (media centre taps) and `BS_COMMON` (the Bob-Smith trunk) are private SIGNAL
wiring and are never part of the interface.

The carrier adapter is `carrier/subsystems/ethernet.py`.

## Design

- **Magnetics part.** T1 is the Pulse HX5008NLT (LCSC C962544), a 24-pad single-port 1:1
  gigabit magnetics module, referenced from the global `parts/HX5008NLT/` dossier (verified
  pad-for-pad against Pulse datasheet PS-0118.001-D Rev A, Sheet 2). Its `ALT_LCSC` field
  carries the HX5008NLTP-CND clone C47575004 as a stock-floor fallback. The pinout is:

  ```
      CHIP / PHY side                MEDIA / RJ45 side
      1  TCT1                        24 MCT1
      2  TD1+   3  TD1-              23 MX1+   22 MX1-
      4  TCT2                        21 MCT2
      5  TD2+   6  TD2-              20 MX2+   19 MX2-
      7  TCT3                        18 MCT3
      8  TD3+   9  TD3-              17 MX3+   16 MX3-
      10 TCT4                        15 MCT4
      11 TD4+  12 TD4-              14 MX4+   13 MX4-
  ```

  Per channel the chip pair `TDn` maps to abstract `MDIn`, the media pair `MXn` to abstract
  `MXn`, the media centre tap `MCTn` to the Bob-Smith trunk, and the chip centre tap `TCTn`
  to a no-connect.

- **Differential typing.** Every MDI and MX pair is typed as a 100 Ω `diff_pair` for
  1000BASE-T. Typing is done in abstract names; `bind` rebinds each pair's `pair_with`
  complement through the rename map so bound pairs stay consistent for the SI pair-join.

- **Bob-Smith termination.** Each media centre tap carries a 75 Ω ∥ 1 nF into the shared
  `BS_COMMON` trunk (IEEE 802.3 §40.7.1 common-mode HF return). The trunk bypasses to the
  chassis island through one 1 nF / 2 kV barrier cap (C5). C5 is the single element bridging
  the signal and chassis domains and is the isolation barrier.

- **Caps are 2 kV.** All five 1 nF caps (C1..C5) are genuine 2 kV X7R 1206 parts
  (IEC 60950/62368 hi-pot); the 2 kV rating forces the 1206 body. The value is drawn `1n`
  for schematic economy.

- **Chip-side centre taps are no-connects.** A voltage-mode-driver PHY (e.g. RTL8211F)
  self-biases its own transmit common mode, and a typical mezzanine exposes only the MDI
  pairs, so the four chip-side taps (pins 1/4/7/10) are explicit no-connects.

- **Chassis ground.** `CHASSIS_GND` is a separate island, star-bonded to signal ground by
  the consuming board; it is not a signal GND. It is the only externally-visible non-port
  net, since the magnetics are passive and self-isolating.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| T1 | HX5008NLT | `parts/HX5008NLT/` (24-pad 1:1 gigabit magnetics) | C962544 (alt C47575004) |
| R1..R4 | 75R | `Device:R` 0603 (Bob-Smith) | C4275 |
| C1..C4 | 1n | `Device:C` 1206 / 2 kV (Bob-Smith HF) | C9196 |
| C5 | 1n | `Device:C` 1206 / 2 kV (BS trunk → chassis, the isolation barrier) | C9196 |

## Build & test

`test_ethernet.py` runs the subsystem-local gate slices offline (abstract interface and
net classes, the pin-faithful HX5008NL mapping, model completeness, diff-pair typing, the
Bob-Smith network, part ratings incl. the 2 kV caps, the SPICE-subckt ↔ netlist passive
match, and the bind contract). Cross-board gates (link/port-driver graph, full SI
constraint set, board ERC, netlist merge) run at board level via `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/ethernet/test_ethernet.py -q
```
