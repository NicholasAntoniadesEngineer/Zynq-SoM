# mechanical — M3 mounting holes + chassis-GND island

A carrier-LOCAL sheet (not a reusable library subsystem, not a thin adapter) owning the board's mechanical fab-art that has no electrical interface to bind: the four M3 corner mounting holes (`H1..H4`) and their `CHASSIS_GND` bond. On the Zynq-7000 SoM carrier it gives the holes their own placement cluster so the PCB placer can corner-force them to the four board corners.

## Interface

This sheet is carrier-LOCAL, so there is no bind contract. It declares exactly one net and drives it:

- `CHASSIS_GND` — the chassis-ground island. Each of the four mounting holes bonds its single pin to this net (`H1.1 .. H4.1 -> CHASSIS_GND`). The net classes as `GROUND`, the only class `Circuit.mounting_hole()` accepts.

No `GND` net is declared on this sheet (see Design).

## Design

**Own sheet for own placement cluster.** The PCB placer groups footprints per subsystem and draws each subsystem's ratsnest as a local bundle. Keeping the four holes on their own `mechanical` sheet makes them their own mechanical cluster, which the placer corner-forces to the four board corners rather than crowding any signal subsystem's mid-board zone.

**Mounting hole = plated chassis bond, never a rail.** Each hole is created via `Circuit.mounting_hole("CHASSIS_GND")`: a KiCad `Mechanical:MountingHole_Pad` symbol on the `MountingHole:MountingHole_3.2mm_M3_Pad` footprint — real plated copper with a netlisted pin so the chassis bond is ERC- and netlist-gate verifiable and the placement engine can place it. `mounting_hole()` hard-rejects any non-`GROUND` net (tying a hole to a rail such as `+3V3` would be a LAW-0 short). The holes are `BOM=exclude` fab-art, never a BOM line.

**CHASSIS_GND is a deliberately-separate copper island.** `CHASSIS_GND` collects the connector shells, the RJ45 Bob-Smith trunk, and these M3 holes. It is intentionally NOT netlisted to signal `GND`: a schematic bond would DC-merge the two islands everywhere, defeating the isolation the island exists to provide. The board netlist gate would then see one merged net and hide a real electrical mistake. Accordingly this sheet declares ONLY `CHASSIS_GND` and contains ONLY the four holes — no bonding device of any kind.

**Single-point chassis bond is a copper stitch, NOT a netlisted part.** `CHASSIS_GND` and `GND` are joined at EXACTLY ONE point — a single-point "star" stitch (a bonding pad / 0 Ω jumper / via stitch) placed in copper near the power-entry and mounting reference so chassis noise cannot circulate through the signal-return path. This is a LAYOUT-STAGE requirement realised in copper by the layout engineer, never a netlisted device. Do NOT add a netlisted `GND`↔`CHASSIS_GND` tie (merges the islands) and do NOT omit the stitch (the chassis island would float — every connector shell and the Bob-Smith trunk would have no DC reference).

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| H1..H4 | MountingHole_M3 | `Mechanical:MountingHole_Pad` (fp `MountingHole:MountingHole_3.2mm_M3_Pad`) | — (BOM-excluded fab-art) |

## Build & test

`test_mechanical.py` proves the four holes exist and all bond to `CHASSIS_GND`, that `CHASSIS_GND` is a GROUND net, that the holes are BOM-excluded, that every pin is netted-or-NC, and that no netlisted `GND`↔`CHASSIS_GND` bond part exists (only `CHASSIS_GND` is declared).

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/mechanical/test_mechanical.py -q
```

Board-level gates (full netlist merge, board ERC, the LAW-5 PCB ratsnest/placement gate proving the corner cluster, the golden render) stay aggregated by `schgen board`.
