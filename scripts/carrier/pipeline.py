"""Orchestrator for the hierarchical carrier schematic generator."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from scripts.carrier.blocks import all_block_factories
from scripts.carrier.build_logs import CarrierBuildLog
from scripts.carrier import gen_refcircuits_doc
from scripts.carrier.registry import bom_io
from scripts.carrier.refcircuits import REFCIRCUITS
from scripts.carrier.sheets.project import emit_project_file
from scripts.carrier.sheets.root import emit_hierarchical_project
from scripts.carrier.validate import run_all


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
CARRIER_OUTPUT_DIR = SCRIPTS_DIR / "carrier_template"
BUILD_LOG_PATH = CARRIER_OUTPUT_DIR / "carrier_build_logs.txt"
VALIDATION_REPORT_PATH = CARRIER_OUTPUT_DIR / "validation_report.md"


def _io_section_count(io_csv_path: Path) -> int:
    distinct_destinations: set[str] = set()
    with open(io_csv_path, encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            destination = row.get("destination", "")
            if destination and destination != "NOT_ASSIGNED":
                distinct_destinations.add(destination)
    return len(distinct_destinations)


def _bom_token_count(bom_csv_path: Path) -> tuple[int, int]:
    total_parts = 0
    distinct_tokens = 0
    with open(bom_csv_path, encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            distinct_tokens += 1
            total_parts += int(row.get("quantity", "0") or 0)
    return total_parts, distinct_tokens


def run(*, skip_erc: bool = False) -> int:
    """Generate all carrier artefacts and validate; return process exit code."""
    build_log = CarrierBuildLog(BUILD_LOG_PATH)
    build_log.start_run()

    print("Step 1/6: Generating io_assignment.csv ...")
    io_row_count = bom_io.emit_io_assignment_csv()
    print(f"  -> wrote {io_row_count} pin assignments")
    build_log.log_io_assignment(
        rows=io_row_count,
        sections=_io_section_count(CARRIER_OUTPUT_DIR / "io_assignment.csv"),
    )

    print("Step 2/6: Generating carrier_BOM.csv ...")
    board_cost_usd = bom_io.emit_bom_csv()
    parts_count, distinct_tokens = _bom_token_count(CARRIER_OUTPUT_DIR / "carrier_BOM.csv")
    print(f"  -> total board cost: ${board_cost_usd:.2f}")
    build_log.log_bom(
        parts=parts_count,
        distinct_tokens=distinct_tokens,
        total_usd=board_cost_usd,
    )

    print("Step 3/6: Fetching local datasheets + generating reference_circuits.md ...")
    from scripts.carrier.datasheets.fetch_datasheets import (
        ensure_datasheets_fetched,
        ensure_datasheets_present,
    )

    ensure_datasheets_fetched()
    ensure_datasheets_present()
    refcircuits_line_count = gen_refcircuits_doc.emit_refcircuits_md()
    print(f"  -> wrote {refcircuits_line_count} lines ({len(REFCIRCUITS)} ICs documented)")
    build_log.log_refcircuits_doc(
        line_count=refcircuits_line_count,
        ic_count=len(REFCIRCUITS),
    )

    print("Step 4/6: Building hierarchical schematic blocks ...")
    block_factories = all_block_factories()
    built_blocks = {
        block_name: block_factory()
        for block_name, block_factory in block_factories.items()
    }
    root_result = emit_hierarchical_project(
        blocks=built_blocks,
        output_dir=CARRIER_OUTPUT_DIR,
    )
    for block_stats in root_result.block_stats:
        build_log.log_block(block_stats)
    build_log.log_root_sheet(
        child_sheet_count=root_result.child_sheet_count,
        hierarchical_pin_count=root_result.hierarchical_pin_count,
        root_path=root_result.root_schematic_path,
    )
    print(
        f"  -> root sheet + {root_result.child_sheet_count} sub-sheets "
        f"({root_result.hierarchical_pin_count} hierarchical pins)"
    )

    print("Step 5/6: Writing carrier_template.kicad_pro ...")
    emit_project_file(
        project_path=CARRIER_OUTPUT_DIR / "carrier_template.kicad_pro",
        root_schematic_filename="carrier_template.kicad_sch",
        root_uuid=root_result.root_uuid,
        block_names=tuple(built_blocks.keys()),
    )

    print("Step 6/6: Running validation ...")
    schematic_paths = tuple(
        CARRIER_OUTPUT_DIR / "sheets" / f"{block_name}.kicad_sch"
        for block_name in built_blocks
    )
    strict_failures, warning_count = run_all(
        schematic_paths=schematic_paths,
        root_schematic_path=root_result.root_schematic_path,
        report_path=VALIDATION_REPORT_PATH,
        skip_erc=skip_erc,
    )
    build_log.log_validation(
        strict_failures=strict_failures,
        warning_count=warning_count,
        report_path=VALIDATION_REPORT_PATH,
    )
    if not skip_erc:
        from scripts.carrier.validate.erc import run_erc

        _erc_results, erc_error_count, erc_warning_count = run_erc(
            root_result.root_schematic_path
        )
        build_log.log_erc(
            error_count=erc_error_count,
            warning_count=erc_warning_count,
        )

    if strict_failures > 0:
        build_log.write_partial()
        print()
        print(
            "Generation FAILED - validation report at "
            f"{VALIDATION_REPORT_PATH.relative_to(REPO_ROOT)}"
        )
        print(f"Build log: {BUILD_LOG_PATH.relative_to(REPO_ROOT)}")
        return 1

    artefact_paths = [
        root_result.root_schematic_path,
        CARRIER_OUTPUT_DIR / "carrier_template.kicad_pro",
        CARRIER_OUTPUT_DIR / "carrier_BOM.csv",
        CARRIER_OUTPUT_DIR / "io_assignment.csv",
        CARRIER_OUTPUT_DIR / "reference_circuits.md",
        VALIDATION_REPORT_PATH,
        BUILD_LOG_PATH,
    ]
    build_log.finish(artifact_paths=artefact_paths)

    print()
    print("All artefacts generated successfully:")
    for artefact_path in artefact_paths:
        print(f"  {artefact_path.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    skip_erc = "--skip-erc" in sys.argv
    return run(skip_erc=skip_erc)


if __name__ == "__main__":
    raise SystemExit(main())
