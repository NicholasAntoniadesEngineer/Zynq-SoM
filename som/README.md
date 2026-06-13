# som/ — the Zynq SoM (hand-authored, source of truth)

The System-on-Module: a hand-designed Zynq-7000 KiCad project. Open
`som/Zynq_SoM.kicad_pro` in KiCad 9+.

```
som/
  Zynq_SoM.kicad_pro / .kicad_sch / .kicad_pcb   # the module project
  Zynq_SoM.pdf                                    # rendered schematic
  lib/                                            # custom symbols / footprints / 3D
  manufacturing/                                  # SoM fab/assembly outputs
  fp-lib-table                                    # footprint library table
```

## Why the carrier reads this project

The carrier does **not** hand-copy any SoM pinout. It extracts the truth
**live** from this KiCad project:

- `schgen som-interface` → `carrier/som_interface.json` — the J1/J2/J3
  mezzanine contract (300 pins) the carrier subsystems bind against.
- `schgen xdc` → the Vivado pin map — J-pin → Zynq ball, read from this
  project's netlist.

So this project is the **upstream source of truth**: edits here ripple into
the generated carrier on the next `schgen board`. It is never hand-edited to
match the carrier — the dependency runs one way only.
