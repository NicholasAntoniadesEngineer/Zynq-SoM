from __future__ import annotations

from schgen.core.model import Circuit

N_MOUNTING_HOLES = 4


def circuit() -> Circuit:
    # CHASSIS_GND stays a separate island — a netlisted GND tie DC-merges it.
    # SINGLE-POINT STAR STITCH is LAYOUT-only (README; copper_debt CD-04 anchor).
    c = Circuit("mechanical", "Mechanical: M3 mounts + chassis-GND bond "
                "(fiducials are PCB-only, emitted by the placer)")
    c.net("CHASSIS_GND")
    for _ in range(N_MOUNTING_HOLES):
        c.mounting_hole("CHASSIS_GND")
    return c
