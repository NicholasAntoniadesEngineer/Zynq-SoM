"""Top-level pipeline orchestrator.

Stages (see plan §"Generation pipeline"):

    0. Audit       — component-completeness check; can run standalone
                     via ``--audit-only``.
    1. Catalog     — register shared symbol libraries.
    2. Build       — declarative block builders return Block objects.
    3. Rules       — (Stage 5) production-grade rule classes mutate blocks.
    4. Layout      — region packer + cluster + place + auto-paginate.
    5. Route       — pin-aware A* router + bus grouping + junctions.
    6. Emit        — sheet → .kicad_sch + project file.
    7. Validate    — page_bounds + overlap + routing + ERC.
    8. Outputs     — (Stage 8) BOM.csv + io_assignment.csv + reference_circuits.md.

Stage 4 currently implements Stages 0-7 end-to-end for the Power block only.
Additional blocks land in Stage 6, the root sheet in Stage 7.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from zynq_eda.core.emit import emit_sheet
from zynq_eda.core.layout import SymbolGeometryCache
from zynq_eda.core.layout.place import place_block
from zynq_eda.core.validate.audit import run_audit, summary_line
from zynq_eda.core.validate.erc import run_erc
from zynq_eda.core.validate.overlap import validate_overlap
from zynq_eda.core.validate.page_bounds import validate_page_bounds
from zynq_eda.core.validate.report import ValidationReport


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CARRIER_OUTPUT_DIR = REPO_ROOT / "boards" / "carrier"


def run_carrier(
    *,
    output_dir: Path | None,
    only_block: str | None,
    audit_only: bool,
    skip_erc: bool,
    allow_incomplete: bool,
) -> int:
    """Generate the carrier board. Returns the process exit code."""
    resolved_output_dir = output_dir or DEFAULT_CARRIER_OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    print("=== zynq_eda carrier generator ===")
    print(f"Output dir: {resolved_output_dir}")
    print()

    # --- Stage 0: Audit -----------------------------------------------------
    print("Stage 0: Component-completeness audit...")
    audit_report = run_audit()
    audit_report_path = resolved_output_dir / "audit_report.md"
    audit_report.write_markdown(audit_report_path, title="Carrier — Component Completeness Audit")
    print(f"  {summary_line(audit_report)}")
    print(f"  report: {audit_report_path.relative_to(REPO_ROOT)}")

    if audit_report.error_count > 0 and not allow_incomplete:
        print()
        print(
            f"AUDIT FAILED with {audit_report.error_count} errors. "
            "Re-run with --allow-incomplete to proceed anyway."
        )
        return 1

    if audit_only:
        print()
        print("--audit-only: stopping after Stage 0.")
        return 0 if audit_report.error_count == 0 else 1

    # --- Stage 1: Catalog (register symbol libraries) -----------------------
    from zynq_eda.projects import carrier as carrier_project

    print()
    print("Stage 1: Loading symbol libraries...")
    geometry_cache = SymbolGeometryCache()
    libraries_to_load = tuple(
        lib_path
        for lib_path in carrier_project.SHARED_SYMBOL_LIBRARIES
        if lib_path.exists()
    )
    if not libraries_to_load:
        print("  no shared libraries found; only KiCad built-in libs available")
    else:
        geometry_cache.register_libraries(libraries_to_load)
        print(f"  registered {len(libraries_to_load)} library file(s)")

    # --- Stage 2: Build blocks ---------------------------------------------
    print()
    print("Stage 2: Building blocks...")
    blocks = carrier_project.build_blocks(only=only_block)
    print(f"  built {len(blocks)} block(s): {', '.join(b.name for b in blocks)}")

    # --- Stages 4-6: Layout + Emit ------------------------------------------
    print()
    print("Stages 4-6: Layout + emit per block...")
    sheets_dir = resolved_output_dir / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    block_validation = ValidationReport()
    parent_uuid = str(uuid.uuid4())

    for block in blocks:
        print(f"  block {block.name!r} ({block.title}):")
        sheet = place_block(block, geometry_cache=geometry_cache)

        # In-memory validators run before emission so a broken sheet doesn't
        # overwrite a known-good file.
        bounds_results = validate_page_bounds(sheet)
        overlap_results = validate_overlap(sheet)
        block_validation.extend(bounds_results)
        block_validation.extend(overlap_results)
        print(
            f"    placed: {len(sheet.symbols)} symbols, {len(sheet.wires)} wires, "
            f"{len(sheet.labels)} labels, {len(sheet.hierarchical_labels)} hlabels"
        )
        print(
            f"    in-memory validators: bounds={len(bounds_results)}, "
            f"overlap={len(overlap_results)}"
        )

        sheet_path = sheets_dir / f"{block.name}.kicad_sch"
        sheet_uuid = str(uuid.uuid4())
        stats = emit_sheet(
            sheet,
            sheet_path,
            parent_uuid=parent_uuid,
            sheet_uuid=sheet_uuid,
        )
        print(f"    emitted: {stats.output_path.relative_to(REPO_ROOT)}")

    # --- Stage 7: Validation report (in-memory + ERC) ----------------------
    print()
    print("Stage 7: Validation...")
    if not skip_erc:
        for block in blocks:
            sheet_path = sheets_dir / f"{block.name}.kicad_sch"
            erc_results, erc_errors, erc_warnings = run_erc(sheet_path)
            block_validation.extend(erc_results)
            print(
                f"  ERC {block.name}: errors={erc_errors}, warnings={erc_warnings}"
            )
    else:
        print("  --skip-erc: skipping kicad-cli ERC")

    validation_path = resolved_output_dir / "validation_report.md"
    block_validation.write_markdown(validation_path, title="Carrier — Validation Report")
    print(
        f"  total: errors={block_validation.error_count}, "
        f"warnings={block_validation.warning_count}"
    )
    print(f"  report: {validation_path.relative_to(REPO_ROOT)}")

    if block_validation.error_count > 0:
        print()
        print(
            f"VALIDATION FAILED with {block_validation.error_count} errors. "
            f"See {validation_path.relative_to(REPO_ROOT)}"
        )
        return 1

    print()
    print("All sheets generated cleanly.")
    return 0
