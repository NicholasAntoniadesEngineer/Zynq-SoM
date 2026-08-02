from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

N_MOUNTING_HOLES = 4

CHASSIS_BOND_POINTS = register(
    "mechanical.chassis_bond", 1, "count",
    "CHASSIS_GND is a separate copper island (connector shells + the M3 "
    "mounting ring) joined to signal GND at EXACTLY ONE point — a SINGLE-POINT "
    "STAR STITCH that is LAYOUT-only (bonding pad / 0R / via stitch near power "
    "entry). A netlisted GND tie would DC-merge two deliberately separate nets "
    "(LAW 0), so the bond is absent from the netlist by design and copper_debt "
    "CD-04 measures it against the EMITTED board instead.",
    "policy")


def circuit() -> Circuit:
    c = Circuit("mechanical", "Mechanical: M3 mounts + chassis-GND bond "
                "(fiducials are PCB-only, emitted by the placer)")
    c.net("CHASSIS_GND")
    for _ in range(N_MOUNTING_HOLES):
        c.mounting_hole("CHASSIS_GND")
    return c
