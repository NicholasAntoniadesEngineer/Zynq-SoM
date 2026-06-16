# power — carrier ADAPTER for the reusable multi-rail regulator-tree subsystem

This is a **thin carrier adapter**, not a netlist. The portable circuit — the
`+VIN -> +5V buck (LM61460) -> +3V3 buck (LM61460) -> +1V8 LDO` regulator tree
with its PG LEDs — lives in the **project-agnostic library
[`subsystems/power/`](../../../subsystems/power/README.md)**. This package is the
carrier-specific GLUE: it imports the library subsystem, BINDS its abstract
ports/rails to the carrier's real net names, and returns the bound `Circuit`. The
board build discovers it exactly as before (`circuit()` exposed here), and the
binding reproduces the EXACT net names the hand-written sheet used, so the emitted
`carrier/schematic/power.kicad_sch` and its golden render are byte-unchanged.

## Package contents

| file | role |
|------|------|
| `power.py`      | the ADAPTER — `META` (the bind contract) + `circuit()` returning `_lib.circuit(META)` |
| `power.cir`     | thin SPICE wrapper — the carrier-bound subckt that simply instantiates the library `subsystems/power/power.cir` subckt |
| `test_power.py` | byte-identical-BIND guard (the adapter's nets == `lib.circuit(META)` nets, the bind renames only externals, draw-notes survive) |
| `README.md`     | this file |

## The carrier bind (`META`)

The ONE carrier-specific surface of this subsystem (full per-net rationale is in
the `power.py` module docstring):

| abstract subsystem net | carrier real net | note |
|------------------------|------------------|------|
| `+VIN`          | `+VIN_SYS`   | buck input is the POST-shunt rail (RS1 in `power_mon`) |
| `+VOUT_5V_REG`  | `+5V_REG`    | buck-1 output cluster (reg-side of RS2) |
| `+VOUT_5V`      | `+5V`        | board +5V rail (post-RS2), the measured consumers |
| `+VOUT_3V3_REG` | `+3V3_REG`   | buck-2 output cluster (reg-side of RS3) |
| `+VOUT_3V3`     | `+3V3`       | board +3V3 rail (post-RS3) |
| `+VOUT_1V8_REG` | `+1V8_REG`   | LDO output cluster (reg-side of RS4) |
| `+VOUT_1V8`     | `+1V8`       | board +1V8 rail (post-RS4) |
| `GND`           | `GND`        | identity; also the LM61460 heat path |
| `EN_VOUT_5V`    | `EN_5V0`     | rail enable, **bind deferred to bringup** (DIP-AND-STM32 cell) |
| `EN_VOUT_3V3`   | `EN_3V3`     | rail enable, **bind deferred to bringup** |
| `EN_VOUT_1V8`   | `EN_1V8`     | rail enable, **bind deferred to bringup** |

The three EN ports carry an `expects` deferral (they bind on the bringup sheets —
the wave-2 DIP-AND-STM32 rail-enable cells, dossier section 3.1) so a standalone
link reports them as awaiting-bringup, never a silent open. The `notes` overrides
restore the carrier's exact dossier wording for the per-rail draw budgets so
`carrier/reports/power_tree.txt` stays byte-identical to the hand sheet.

The INTERNAL signal nets (LM61460 SW/FB/BOOT/BIAS/VCC/RT + the +3V3 buck control
nodes + the PG-LED/FET nodes) stay VERBATIM in the library — private regulator
wiring, NEVER bound.

## The library subsystem

Everything portable — the schematic-emitting netlist, the full local
electrical-correctness test, the SPICE subckt of the regulator passive network,
the thermal/FB/ratings rationale, and the abstract `INTERFACE`/`RAILS`/`PORTS` —
lives in **[`subsystems/power/`](../../../subsystems/power/README.md)**. Read that
README for the regulator topology, the 2026-06-14 LMR33630->LM61460 re-spec, the
2026-06-16 U1/U2 thermal fix, and the FB-divider derivations.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/power/test_power.py -q
```

This adapter test proves only the BIND contract is faithful (the carrier nets the
board build sees match `lib.circuit(META)` exactly). The deep electrical proofs
run in the library's own `subsystems/power/test_power.py`; the cross-board gates
(EN linker graph, full power-tree headroom, thermal join, board ERC, netlist
merge) stay aggregated by `schgen board`.
