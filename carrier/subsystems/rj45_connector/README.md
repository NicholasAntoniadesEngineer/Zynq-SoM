# rj45_connector — carrier ADAPTER for the reusable 8P8C RJ45 jack subsystem

THIN ADAPTER. The portable circuit lives in the project-agnostic library
[`subsystems/rj45_connector/`](../../../subsystems/rj45_connector/README.md)
(netlist + README + SPICE + local test). This package is the carrier-specific
GLUE: it imports the library subsystem and BINDS its abstract ports/rails to the
carrier's REAL net names via a `META` contract, returning the bound `Circuit`.
The board build discovers it exactly as the flat layout did (`circuit()` exposed
via `__init__`), and the binding reproduces the EXACT net names the hand-written
sheet used, so the emitted `carrier/schematic/rj45_connector.kicad_sch` and its
golden render stay byte-identical.

## Package contents (4-artifact parity with the generic library)

| file | role |
|------|------|
| `rj45_connector.py`      | the THIN ADAPTER — `META` (bind/notes) + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`            | re-exports `circuit, META` so discovery + the bind test import the package |
| `rj45_connector.cir`     | thin SPICE subckt — the CARRIER external nets as subckt pins, pointing at the library `.cir` for the real passive network |
| `test_rj45_connector.py` | byte-identical-BIND guard — adapter nets == `_lib.circuit(META)` nets; carrier names appear; no abstract leak |
| `README.md`              | this file |

## The carrier bind (generic subsystem + META)

The generic subsystem's abstract INTERFACE is mapped to the carrier nets by
`META["bind"]`:

| abstract net | carrier net | role |
|--------------|-------------|------|
| `+VLED`      | `+3V3`         | the two housing LEDs, a steady port-present indicator off the ALWAYS-ON +3V3 rail (330R each, NOT DIP-gated) |
| `GND`        | `GND`          | identity (LED cathodes return to signal GND) |
| `CHASSIS_GND`| `CHASSIS_GND`  | identity (shield/shell J1.13 + four M3 corner mounts to the chassis island) |
| `RJ45_MDI0/1/2/3_P/N` | `ETH_LINE_MDI_0/1/2/3_P/N` | the four 1000BASE-T pairs, line-side, facing the ethernet magnetics' MEDIA side |

The two housing-LED anode nodes (`RJ45_LED_L` / `RJ45_LED_R`) stay INTERNAL to
the library sheet — private SIGNAL wiring, never bound here.

This adapter is the PEER that BINDS the line-side MDI pairs (the `ethernet`
subsystem declares an `expects` deferral on them naming "rj45_connector (wave
2)"); by binding both subsystems to the same `ETH_LINE_MDI_x` nets, that
deferral resolves to BOUND on both sheets — so this adapter does NOT itself
defer them (no `expects`; no named bus). `META["notes"]` carries the carrier
house-style power-tree draw prose.

The full per-net rationale lives in the adapter module docstring
(`rj45_connector.py`); the device + passive network is documented in the library
README at [`../../../subsystems/rj45_connector/README.md`](../../../subsystems/rj45_connector/README.md).

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/rj45_connector/test_rj45_connector.py -q
```

The board-level gates (full power tree, board ERC, the cross-sheet link/port-
driver graph, the golden renders) stay aggregated by `schgen board`.
