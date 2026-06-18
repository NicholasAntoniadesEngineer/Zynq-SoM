# som_decoupling — SoM power-entry decoupling (under the DF40 mezzanine)

CARRIER-LOCAL subsystem. Bulk + high-frequency bypass on the three rails the
carrier **delivers to the SoM** across the DF40 mezzanine connector, placed on
the **bottom side directly under the SoM shadow** (LAW 6).

## Why

A delivered power rail must be bypassed at its distribution node so the load —
here the SoM, drawing transient current through the DF40 power pins — sees a
low-impedance source. The connector power entry, right beneath the mezzanine, is
the textbook position for that bulk + HF network.

It also makes correct use of the SoM keepout region: the area under a plugged-in
module can hold only low-profile passives and is otherwise dead space. Entry
decoupling there is exactly what belongs (LAW 6 — *"passives there are GOOD; use
the dead space"*). The build's placer grids these caps on B.Cu inside the SoM
core; the top-side DF40 receptacles are on a different layer and do not conflict.

This is **supplemental** entry/bulk decoupling at the connector. It does **not**
replace each carrier IC's own local decoupling — those caps stay at their ICs.
The shared `+3V3` / `+3V3_SC` bypass caps that live at their loads are
deliberately left there; moving them under the SoM would strip local decoupling
and is an electrical regression (LAW 0).

## Interface

| Net        | Dir | Notes                                            |
|------------|-----|--------------------------------------------------|
| `+5V_SOM`  | in  | SoM main power input (carrier → DF40)            |
| `+3V3`     | in  | SoM bank / general 3.3 V supply (carrier → DF40) |
| `+3V3_SC`  | in  | SoM system-controller 3.3 V supply (→ DF40)      |
| `GND`      | in  | return                                           |

All four are global rails merged by name; no abstract ports. The rails are
driven by the carrier regulators (`power`, `power_som`); this sheet only adds
shunt decoupling.

## Parts (reuse the carrier's stocked, ratings-verified MLCCs)

| Role | Value         | Footprint | LCSC   | Per rail | Total |
|------|---------------|-----------|--------|----------|-------|
| bulk | 22 µF 25 V X5R | 0805      | C45783 | 2        | 6     |
| HF   | 100 nF 50 V X7R| 0603      | C14663 | 4        | 12    |

Per rail: 2 × 22 µF + 4 × 100 nF. Three rails → **18 caps**.

## Verification

`test_som_decoupling.py` runs the subsystem-local slices (model completeness,
design-rules, part-rules, ratings, SPICE ↔ netlist) plus the network shape:
every rail carries exactly 2 × 22 µF + 4 × 100 nF to GND. Cross-board merge with
the DF40 rails, board ERC and the placement-under-SoM check stay at board level.
