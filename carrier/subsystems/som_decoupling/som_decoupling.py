from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

C0805 = "Capacitor_SMD:C_0805_2012Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"

BULK_VAL = register(
    "som_decoupling.bulk", "22u", "F",
    "Charge reservoir at the DF40 power-pin entry, 25 V X5R 0805 (LCSC "
    "C45783), reusing a carrier-stocked ratings-verified MLCC.",
    "datasheet")
BULK_LCSC = "C45783"

HF_VAL = register(
    "som_decoupling.hf", "100n", "F",
    "High-frequency bypass at the DF40 power-pin entry, 50 V X7R 0603 (LCSC "
    "C14663).",
    "datasheet")
HF_LCSC = "C14663"

N_BULK_PER_RAIL = register(
    "som_decoupling.n_bulk", 2, "count",
    "Two 22 uF per rail at the connector entry. This is SUPPLEMENTAL entry "
    "bulk, never a substitute for each carrier IC's own local decoupling — "
    "moving an IC's bypass here would be an electrical regression.",
    "policy")

N_HF_PER_RAIL = register(
    "som_decoupling.n_hf", 4, "count",
    "Four 100 nF per rail, giving 6 caps per rail and 18 across the three "
    "rails. All placed bottom-side in the SoM shadow (LAW 6): the shortest path "
    "to the DF40 power pins and the correct use of that keepout region.",
    "policy")

# +5V_SOM/+3V3 are carrier-DELIVERED, +3V3_SC is SoM-SOURCED and only TAPPED:
# bypassing at the distribution node is correct in BOTH directions.
RAILS: tuple[str, ...] = ("+5V_SOM", "+3V3", "+3V3_SC")


def circuit() -> Circuit:
    c = Circuit("som_decoupling",
                "SoM power-entry decoupling under the DF40 mezzanine")
    n = 1
    for rail in RAILS:
        for _ in range(N_BULK_PER_RAIL):
            c.part(f"C{n}", "Device:C", BULK_VAL, C0805, LCSC=BULK_LCSC)
            c.net(rail, f"C{n}.1")
            c.net("GND", f"C{n}.2")
            n += 1
        for _ in range(N_HF_PER_RAIL):
            c.part(f"C{n}", "Device:C", HF_VAL, C0603, LCSC=HF_LCSC)
            c.net(rail, f"C{n}.1")
            c.net("GND", f"C{n}.2")
            n += 1
    return c
