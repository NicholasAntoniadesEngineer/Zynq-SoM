from __future__ import annotations

from schgen.core.model import Circuit


def circuit() -> Circuit:
    c = Circuit("m1_rc", "M1 RC divider (engine-placed smoke test)")
    c.part("R1", "Device:R", "10k")
    c.part("R2", "Device:R", "10k")
    c.part("C1", "Device:C", "100n")
    c.net("+3V3", "R1.1")
    c.port("MID", "R1.2", "R2.1", "C1.1",
           expect="schgen smoke sheet — divider mid-point has no board "
                  "consumer by design")
    c.net("GND", "R2.2", "C1.2")
    return c
