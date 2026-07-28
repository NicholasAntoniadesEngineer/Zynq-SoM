"""mechanical — board-MECHANICAL fab-art (M3 mounting holes + chassis bond).

CHASSIS_GND ISLAND + SINGLE-POINT STAR STITCH (audit 2026-06-19, LAW-0/LAW-6).
CHASSIS_GND is a DELIBERATELY-SEPARATE copper island (connector shells, the RJ45
Bob-Smith trunk, the M3 mounting holes). It is intentionally NOT netlisted to
signal GND — a schematic bond would DC-merge the two islands everywhere, which is
the very short the isolation exists to prevent (LAW 0). The two MUST instead be
joined at EXACTLY ONE point in copper: a single-point STAR STITCH (a small bonding
pad / 0R / via stitch) tying CHASSIS_GND to GND near the power-entry & mounting
reference. THIS IS A LAYOUT-STAGE REQUIREMENT, not a netlist one — the generated
board is unrouted so it cannot carry the stitch yet; it is recorded here and in
mechanical/README.md so the layout engineer places exactly one bond. Do NOT add a
netlisted tie (merges the islands) and do NOT omit it (the chassis island floats —
every connector shell + the Bob-Smith trunk would have no DC reference).

FIDUCIALS (GAP3, ASSEMBLY_NOTES): 5 optical registration marks (3 global in an
asymmetric L + 1 local pair flanking the densest 0.4 mm DF40) ARE emitted on the
board — but NOT here. A fiducial carries NO net and NO pin, so it is not a
schematic circuit part (a pinless part trips the per-sheet netlist "parts present"
gate). It is injected as a PCB-only synthetic FootprintInst in the placer
(schgen/generate/pcb/placement.py build_model, footprint
Fiducial:Fiducial_1mm_Mask2mm = 1 mm bare-copper dot + 2 mm mask), at FIXED
board-corner + SoM-keepout-corner positions. This subsystem emits ONLY the 4 M3
mounting holes + the chassis bond; see the placer for the fiducials.
"""
from __future__ import annotations

from schgen.core.model import Circuit

N_MOUNTING_HOLES = 4
def circuit() -> Circuit:
    c = Circuit("mechanical", "Mechanical: M3 mounts + chassis-GND bond "
                "(fiducials are PCB-only, emitted by the placer)")
    c.net("CHASSIS_GND")
    for _ in range(N_MOUNTING_HOLES):
        c.mounting_hole("CHASSIS_GND")
    return c
