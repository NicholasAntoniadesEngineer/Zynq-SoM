"""Top-level pipeline orchestrator.

Stages (see plan §"Generation pipeline"):

    0. Audit       — component-completeness check; can run standalone
                     via ``--audit-only``.
    1. Catalog     — load parts + refcircuits + symbols into memory.
    2. Build       — declarative block builders return Block objects
                     (no coordinates yet).
    3. Rules       — production-grade rule classes mutate blocks with
                     required passives (decoupling, termination, etc.).
    4. Layout      — region packer + cluster + place + auto-paginate.
    5. Route       — pin-aware A* router + bus grouping + junctions.
    6. Emit        — sheet → .kicad_sch + project file.
    7. Validate    — page_bounds + overlap + routing + refcircuit + bom + ERC.
    8. Outputs     — BOM.csv + io_assignment.csv + reference_circuits.md.

Stages 1-7 land block-by-block in later commits. This module currently
implements Stage 0 (audit) and dispatches the other stages to placeholder
functions that report "not yet implemented" so the CLI runs end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from zynq_eda.core.validate.audit import run_audit, summary_line


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "boards" / "carrier"


def run_carrier(
    *,
    output_dir: Path | None,
    only_block: str | None,
    audit_only: bool,
    skip_erc: bool,
    allow_incomplete: bool,
) -> int:
    """Generate the carrier board.

    Returns the process exit code (0 = success, 1 = strict failures, 2 = bad args).
    """
    resolved_output_dir = output_dir or DEFAULT_OUTPUT_DIR
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== zynq_eda carrier generator ===")
    print(f"Output dir: {resolved_output_dir}")
    print()

    # Stage 0: Audit (always)
    print("Stage 0: Component-completeness audit...")
    audit_report = run_audit()
    audit_report_path = resolved_output_dir / "audit_report.md"
    audit_report.write_markdown(
        audit_report_path,
        title="Carrier — Component Completeness Audit",
    )
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

    # Stages 1-8: not yet implemented
    print()
    print("Stage 1+: not yet implemented (catalog/build/rules/layout/route/emit/validate).")
    print("These land in Stages 3-9 of the roadmap. Use --audit-only for now.")
    if only_block:
        print(f"(--only {only_block!r} acknowledged; will dispatch once block builders land.)")
    if skip_erc:
        print("(--skip-erc acknowledged; will skip kicad-cli ERC once emit lands.)")
    return 0
