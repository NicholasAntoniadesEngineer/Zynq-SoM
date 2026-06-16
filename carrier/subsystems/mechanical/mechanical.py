"""mechanical — board-MECHANICAL fab-art (M3 mounting holes + chassis bond)."""
from __future__ import annotations
from schgen.core.model import Circuit
N_MOUNTING_HOLES = 4
def circuit() -> Circuit:
    c = Circuit("mechanical", "Mechanical: M3 mounting holes + chassis-GND bond + fiducials")
    c.net("CHASSIS_GND")
    for _ in range(N_MOUNTING_HOLES):
        c.mounting_hole("CHASSIS_GND")
    return c
