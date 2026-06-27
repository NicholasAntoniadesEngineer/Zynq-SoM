# som_decoupling — SoM power-entry decoupling under the DF40 mezzanine

Carrier-local subsystem that bypasses three SoM-rail nets at the DF40 mezzanine
connector. It is the rail-entry decoupling network — bulk charge reservoirs plus
high-frequency bypass, GND-referenced — placed directly beneath the plugged-in
module so each rail presents a low-impedance source at the connector power pins.

## Interface

Carrier-local: every net is a global rail merged by name, with no abstract ports.
This sheet adds only shunt decoupling; the rails themselves are driven elsewhere.

| Net        | Direction                | Notes                                                              |
|------------|--------------------------|--------------------------------------------------------------------|
| `+5V_SOM`  | carrier → SoM            | SoM main power input, delivered across the DF40                    |
| `+3V3`     | carrier → SoM            | SoM bank / general 3.3 V supply, delivered across the DF40         |
| `+3V3_SC`  | SoM → carrier            | SoM system-controller 3.3 V (TPS7A20 LDO on the module), tapped here |
| `GND`      | return                   | common return                                                      |

`+5V_SOM` and `+3V3` are carrier-sourced (from the `power` / `power_som`
regulators) and delivered to the SoM. `+3V3_SC` is SoM-sourced — generated on the
module by its own TPS7A20 LDO (~300 mA) and only tapped by the carrier here; the
carrier does not supply it. A rail is bypassed at its distribution node whether it
is delivered to or received from the SoM, so all three are decoupled identically
at the DF40 entry.

## Design

- **Bypass at the connector entry.** Each rail crosses the DF40 power pins; the
  textbook position for its bulk + HF network is right at that entry, beneath the
  connector, so the load sees a low-impedance source for its transient draw.

- **Per-rail network.** Each rail gets 2 × 22 µF bulk (charge reservoir) + 4 ×
  100 nF HF bypass to GND — 6 caps per rail, 18 caps across the three rails. Bulk
  holds charge for slower transients; the distributed HF caps lower the
  high-frequency shunt impedance at the pins.

- **Parts reuse the carrier's stocked, ratings-verified MLCCs.** Bulk is 22 µF
  25 V X5R 0805 (the 25 V rating gives generous margin on 3.3–5 V rails despite
  X5R DC bias derating); HF is 100 nF 50 V X7R 0603. Both are existing carrier
  part numbers, so no new BOM line is introduced.

- **Bottom-side placement in the SoM shadow (LAW 6).** Every cap is placed on the
  bottom side directly under the mezzanine footprint — a keepout that can hold
  only low-profile passives and is otherwise dead space. This is both the shortest
  path to the DF40 power pins and the correct use of that region; the placer grids
  the caps under the SoM core. The top-side DF40 receptacles sit on a different
  layer and do not conflict.

- **Supplemental, not a replacement.** This is entry/bulk decoupling at the
  connector. Each carrier IC keeps its own local decoupling at the IC; the shared
  `+3V3` / `+3V3_SC` bypass caps that live at their loads stay there. Relocating an
  IC's bypass cap under the SoM would strip local decoupling and is an electrical
  regression (LAW 0).

## Parts

The 18 caps are numbered C1…C18 grouped by rail: each rail takes 2 bulk (22 µF)
then 4 HF (100 nF), so the references interleave rather than splitting into one
value block.

| Ref                    | Value  | Lib/Part | Footprint                       | LCSC   |
|------------------------|--------|----------|---------------------------------|--------|
| C1–C2, C7–C8, C13–C14  | 22u    | Device:C | Capacitor_SMD:C_0805_2012Metric | C45783 |
| C3–C6, C9–C12, C15–C18 | 100n   | Device:C | Capacitor_SMD:C_0603_1608Metric | C14663 |

Rail assignment by reference: `+5V_SOM` = C1–C6, `+3V3` = C7–C12, `+3V3_SC` =
C13–C18. C45783 = 22 µF 25 V X5R 0805; C14663 = 100 nF 50 V X7R 0603.

## Build & test

`test_som_decoupling.py` runs the subsystem-local slices (model completeness,
design-rules, part-rules, ratings, SPICE ↔ netlist) plus the network-shape check
that every rail carries exactly 2 × 22 µF + 4 × 100 nF to GND.

```
pytest carrier/subsystems/som_decoupling/test_som_decoupling.py
```
