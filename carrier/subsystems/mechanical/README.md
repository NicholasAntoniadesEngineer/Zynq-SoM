# mechanical — board-MECHANICAL fab-art (M3 mounting holes + chassis bond)

A **carrier-LOCAL, project-specific** sheet — NOT a reusable library subsystem
(there is no `subsystems/mechanical/`) and NOT a thin adapter. It owns the
board-mechanical fab-art that has no electrical interface to bind: the four **M3
corner mounting holes** (`H1..H4`) and their **CHASSIS_GND** bond.

## Why this sheet exists

The four M3 mounting holes used to live on the **rj45_connector** jack sheet (the
reusable `subsystems/rj45_connector/` library co-located them with the shield
entry so all `CHASSIS_GND` fab-art was on one sheet). But the PCB placer groups
footprints **per subsystem** and draws each subsystem's ratsnest as a local
bundle — so the holes were getting bundled with the Ethernet jack, dragged into
the jack's mid-board zone instead of sitting at the board corners where mounting
holes belong.

Pulling the holes onto their **own** sheet gives them their **own** placement
cluster. The placer **corner-forces** the four mounting holes to the four board
corners (it always has — see `schgen/generate/pcb.py` STEP 3), so as their own
mechanical cluster they land at the corners and no longer crowd the jack zone or
any other subsystem.

This is a **pure relocation**: the holes are net-for-net unchanged (still four
M3 holes, still bonded to `CHASSIS_GND`), they just live on the `mechanical`
sheet now. `rj45_connector` keeps J1's own shell tie (`J1.13 -> CHASSIS_GND`) and
the two housing-LED 330R resistors — only the holes moved.

## Package contents

| file | role |
|------|------|
| `mechanical.py`      | the NETLIST — `circuit()`, four `mounting_hole("CHASSIS_GND")` |
| `__init__.py`        | re-exports `circuit, N_MOUNTING_HOLES` (discovery + this test import the package) |
| `mechanical.cir`     | minimal SPICE stub — the `CHASSIS_GND` node as the only subckt pin (nothing to analyse; R-only interface stub) |
| `test_mechanical.py` | LOCAL test — four holes all on `CHASSIS_GND`, model completeness, no netlisted bond |
| `README.md`          | this file |

## The single-point chassis bond is a COPPER STITCH, not a netlisted part

`CHASSIS_GND` is the chassis-ground **island** — a net deliberately kept
**separate** from signal `GND`. The two are tied together at exactly **one**
point (a single-point / "star" bond) so chassis noise cannot circulate through
the signal-return path.

That bond is realised in **copper at PCB layout** — a stitch (a 0 Ω jumper pad,
a net-tie footprint, or a short trace placed by the layout engineer at the chosen
star point). It is **NOT** modelled here as a netlisted device, and you must
**not** add one:

> **LAW 0 — do not add a netlisted GND ↔ CHASSIS_GND bond.** A netlisted bond
> (a resistor/ferrite/jumper part wired `GND` to `CHASSIS_GND`) would **DC-merge
> two deliberately-separate nets** in the schematic netlist — the board netlist
> gate would then see one merged net, defeating the whole point of the island
> and hiding a real electrical mistake. The star is a layout decision, expressed
> in copper, not in the netlist.

Accordingly this sheet declares **only** `CHASSIS_GND` (no `GND` net at all) and
contains **only** the four holes — there is no bonding part of any kind.

A mounting hole is itself a chassis/earth bond, **never** a rail:
`Circuit.mounting_hole()` hard-rejects any non-GROUND net (tying a hole to, say,
`+3V3` would be a LAW-0 short). The holes are plated `Mechanical:MountingHole_Pad`
on the 3.2 mm-M3 plated footprint, **BOM-excluded** fab-art with a netlisted pin
so the chassis bond stays ERC/netlist-gate verifiable and the placer can place
them.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/mechanical/test_mechanical.py -q
```

The board-level gates (full netlist merge, board ERC, the LAW-5 PCB
ratsnest/placement gate that proves the holes are a corner-forced cluster, the
golden render) stay aggregated by `schgen board`.
