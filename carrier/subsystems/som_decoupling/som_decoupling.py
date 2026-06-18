"""som_decoupling — SoM power-entry decoupling under the DF40 mezzanine (LAW 6).

The carrier DELIVERS three rails to the SoM across the DF40 mezzanine connector:
``+5V_SOM`` (the SoM's main power input), ``+3V3`` and ``+3V3_SC`` (bank / system-
controller supplies). A power rail should be bypassed AT its distribution node —
here the DF40 power-pin entry — so the SoM sees a low-impedance source for its
transient current draw. This sheet is that entry network: bulk charge reservoirs
+ high-frequency bypass on each delivered rail, GND-referenced.

PLACEMENT (LAW 6): every cap is placed on the BOTTOM side directly in the SoM
shadow — the area under the plugged-in mezzanine that can hold ONLY low-profile
passives and is otherwise dead space. Putting the rail-entry decoupling there is
both the textbook position (shortest path to the DF40 power pins, right beneath
the connector) AND the correct use of that keepout region (LAW 6: "passives there
are GOOD — use the dead space"). The build's placer grids them under the SoM core.

SCOPE — this is SUPPLEMENTAL entry/bulk decoupling at the connector, NOT a
substitute for each carrier IC's own local decoupling, which stays at its IC
(moving an IC's bypass cap away from it would be an electrical regression — the
shared +3V3/+3V3_SC caps that live at their loads are deliberately left there).

Parts reuse the carrier's already-stocked, ratings-verified MLCCs:
  * bulk : 22 uF 25 V X5R 0805  (LCSC C45783) — charge reservoir
  * HF   : 100 nF 50 V X7R 0603 (LCSC C14663) — high-frequency bypass
Per rail: 2x 22 uF bulk + 4x 100 nF HF (6 caps); three rails -> 18 caps.
"""

from __future__ import annotations

from schgen.core.model import Circuit

C0805 = "Capacitor_SMD:C_0805_2012Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"

BULK_VAL, BULK_LCSC = "22u", "C45783"     # 22 uF 25 V X5R 0805
HF_VAL, HF_LCSC = "100n", "C14663"        # 100 nF 50 V X7R 0603

# rail -> (n_bulk 22 uF, n_hf 100 nF). The three rails the carrier delivers to
# the SoM across the DF40 — bypassed at the connector power entry.
RAILS: tuple[tuple[str, int, int], ...] = (
    ("+5V_SOM", 2, 4),     # SoM main power input
    ("+3V3",    2, 4),     # SoM bank / general 3.3 V supply
    ("+3V3_SC", 2, 4),     # SoM system-controller 3.3 V supply
)


def circuit() -> Circuit:
    c = Circuit("som_decoupling",
                "SoM power-entry decoupling under the DF40 mezzanine")
    n = 1
    for rail, n_bulk, n_hf in RAILS:
        for _ in range(n_bulk):
            c.part(f"C{n}", "Device:C", BULK_VAL, C0805, LCSC=BULK_LCSC)
            c.net(rail, f"C{n}.1")
            c.net("GND", f"C{n}.2")
            n += 1
        for _ in range(n_hf):
            c.part(f"C{n}", "Device:C", HF_VAL, C0603, LCSC=HF_LCSC)
            c.net(rail, f"C{n}.1")
            c.net("GND", f"C{n}.2")
            n += 1
    return c
