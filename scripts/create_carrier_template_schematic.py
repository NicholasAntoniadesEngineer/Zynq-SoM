"""Top-level entry point for the carrier_template schematic generator.

Orchestrates the new scripts/carrier/ package:
    1. Generate io_assignment.csv from SoM connector pin data
    2. Generate carrier_BOM.csv aggregated from ReferenceCircuit specs
    3. Generate reference_circuits.md (per-IC design intent doc)
    4. Generate carrier_template.kicad_sch (hierarchical/flat schematic)
    5. Run full validation pass (Rules A-I + C11-C13)
    6. Atomic-commit output only if all strict rules pass

Usage:
    python scripts/create_carrier_template_schematic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.carrier import bom_io
from scripts.carrier import gen_refcircuits_doc
from scripts.carrier import generator


def main() -> int:
    print("Step 1/4: Generating io_assignment.csv ...")
    n_io = bom_io.emit_io_assignment_csv()
    print(f"  -> wrote {n_io} pin assignments")
    print()

    print("Step 2/4: Generating carrier_BOM.csv ...")
    cost = bom_io.emit_bom_csv()
    print(f"  -> total board cost: ${cost:.2f}")
    print()

    print("Step 3/4: Generating reference_circuits.md ...")
    n_lines = gen_refcircuits_doc.emit_refcircuits_md()
    print(f"  -> wrote {n_lines} lines (15 ICs documented)")
    print()

    print("Step 4/4: Generating carrier_template.kicad_sch ...")
    exit_code = generator.generate()
    if exit_code != 0:
        print()
        print("Generation FAILED - validation report at scripts/carrier_template/validation_report.md")
        return exit_code

    print()
    print("All artefacts generated successfully:")
    print("  scripts/carrier_template/carrier_template.kicad_sch    (schematic)")
    print("  scripts/carrier_template/carrier_template.kicad_pro    (project)")
    print("  scripts/carrier_template/carrier_BOM.csv               (master BOM with LCSC)")
    print("  scripts/carrier_template/io_assignment.csv             (SoM pin -> carrier interface)")
    print("  scripts/carrier_template/reference_circuits.md         (per-IC datasheet design intent)")
    print("  scripts/carrier_template/validation_report.md          (last validation report)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
