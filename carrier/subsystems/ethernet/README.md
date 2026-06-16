# ethernet — carrier ADAPTER for the reusable HX5008NL magnetics subsystem

THIN ADAPTER. The portable circuit lives in the project-agnostic library
[`subsystems/ethernet/`](../../../subsystems/ethernet/README.md) (netlist +
README + SPICE + local test). This package is the carrier-specific GLUE: it
imports the library subsystem and BINDS its abstract ports/rails to the
carrier's REAL net names via a `META` contract, returning the bound `Circuit`.
The board build discovers it exactly as the flat layout did (`circuit()` exposed
via `__init__`), and the binding reproduces the EXACT net names the hand-written
sheet used, so the emitted `carrier/schematic/ethernet.kicad_sch` and its golden
render stay byte-identical.

## Package contents (4-artifact parity with the generic library)

| file | role |
|------|------|
| `ethernet.py`      | the THIN ADAPTER — `META` (bind/expects) + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`      | re-exports `circuit, META` so discovery + the bind test import the package |
| `ethernet.cir`     | thin SPICE subckt — the CARRIER external nets as subckt pins, pointing at the library `.cir` for the real passive network |
| `test_ethernet.py` | byte-identical-BIND guard — adapter nets == `_lib.circuit(META)` nets; carrier names appear; no abstract leak |
| `README.md`        | this file |

## The carrier bind (generic subsystem + META)

The generic subsystem's abstract INTERFACE is mapped to the carrier nets by
`META["bind"]`:

| abstract net | carrier net | role |
|--------------|-------------|------|
| `CHASSIS_GND` | `CHASSIS_GND` | identity (chassis-ground island; the Bob-Smith 1n/2kV barrier cap bypasses to it) |
| `MDI0/1/2/3_P/N` | `ETH_PHY_MDI0/1/2/3_P/N` | CHIP / PHY-side 1000BASE-T pairs facing the SoM PHY (RTL8211F via J1) |
| `MX0/1/2/3_P/N`  | `ETH_LINE_MDI_0/1/2/3_P/N` | MEDIA / RJ45-side pairs to the jack (1:1 in-phase: +<->+) |

The four CHIP-side centre taps + the four media-side Bob-Smith centre taps
(`MCT1..MCT4`) and the shared trunk (`BS_COMMON`) stay INTERNAL to the library
sheet — private SIGNAL wiring, never bound here.

`META["expects"]` declares the media-side pairs (`MX0..3_P`) as deferred onto the
SEPARATE `rj45_connector` subsystem (wave 2): only the P net of each pair need be
named — the reciprocal N inherits the deferral via the diff-pair complement.
That deferral resolves to BOUND because `rj45_connector` binds the same
`ETH_LINE_MDI_x` nets. No power rail to budget, no named bus -> no buses/notes
override.

The full per-net rationale lives in the adapter module docstring
(`ethernet.py`); the device + passive network is documented in the library
README at [`../../../subsystems/ethernet/README.md`](../../../subsystems/ethernet/README.md).

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/ethernet/test_ethernet.py -q
```

The board-level gates (full power tree, board ERC, the cross-sheet link/port-
driver graph, the golden renders) stay aggregated by `schgen board`.
