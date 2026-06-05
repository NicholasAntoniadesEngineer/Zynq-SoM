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
    8. Outputs     — BOM.csv + io_assignment.csv + reference_circuits.md.

Stage 4 currently implements Stages 0-7 end-to-end for the Power block only.
Additional blocks land in Stage 6, the root sheet in Stage 7. Stage 8
artifacts are emitted on every run, regardless of ERC outcome — they're
inputs to manual review, not products of validation.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from zynq_eda.core.emit import emit_project, emit_root_sheet, emit_sheet
from zynq_eda.core.layout import SymbolGeometryCache
from zynq_eda.core.layout.place import place_block
from zynq_eda.core.layout.root import _BlockSheetSpec, build_root_sheet
from zynq_eda.core.route.route_sheet import route_sheet
from zynq_eda.core.registry import (
    emit_bom,
    emit_io_assignment,
    emit_reference_circuits_md,
)
from zynq_eda.core.validate.audit import run_audit, summary_line
from zynq_eda.core.validate.connectivity import validate_connectivity
from zynq_eda.core.validate.external_parts import validate_external_part_pins
from zynq_eda.core.validate.erc import run_erc
from zynq_eda.core.validate.overlap import validate_overlap
from zynq_eda.core.validate.page_bounds import validate_page_bounds
from zynq_eda.core.validate.report import ValidationReport


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CARRIER_OUTPUT_DIR = REPO_ROOT / "boards" / "carrier"


def _assign_power_stamps(blocks) -> dict:
    """Map block.name → set of global power nets that block should drive.

    Each power-symbol net (GND, +3V3, …) needs exactly ONE PWR_FLAG stamp
    project-wide. Assign each declared power net (power_kind output/ground/input)
    to the FIRST block in build order that declares it, so the stamp lands once,
    on a sheet that genuinely carries the rail."""
    from zynq_eda.core.layout._constants import POWER_SYMBOL_LIB_IDS

    # Nets declared as a power OUTPUT anywhere are driven by that block's IC
    # power-output pin (e.g. an LDO's +3V3/+2V5/+1V8) — normally no PWR_FLAG.
    # BUT in this no-root-sheet-pins design the LDO's output net (emitted as a
    # local /power/<rail> hier-label) does NOT merge with the GLOBAL power-symbol
    # net the rail's CONSUMERS sit on (power:+3V3 symbols across 14 sheets). So a
    # rail that is ALSO consumed as a power INPUT elsewhere has an undriven global
    # symbol net and DOES need exactly one flag — only a rail that is output-only
    # (never consumed via a power symbol, e.g. +2V5/+1V8 here) can skip it.
    consumed_input: set[str] = {
        net.name
        for block in blocks
        for net in getattr(block, "external_nets", ())  # type: ignore[attr-defined]
        if net.power_kind == "input"
    }
    driven: set[str] = {
        net.name
        for block in blocks
        for net in getattr(block, "external_nets", ())  # type: ignore[attr-defined]
        if net.power_kind == "output"
    } - consumed_input

    assignment: dict[str, set[str]] = {}
    claimed: set[str] = set()
    # Only nets with NO reachable output driver need a flag: ground, then inputs.
    for kinds in (("ground",), ("input",)):
        for block in blocks:
            for net in getattr(block, "external_nets", ()):  # type: ignore[attr-defined]
                if net.power_kind not in kinds:
                    continue
                if net.name in claimed or net.name in driven:
                    continue
                if net.name not in POWER_SYMBOL_LIB_IDS:
                    continue  # only power-symbol nets need a flag
                assignment.setdefault(block.name, set()).add(net.name)
                claimed.add(net.name)
    return assignment


def _root_filename_stem(only_block: str | None) -> str:
    """Pick the root .kicad_sch / .kicad_pro filename stem.

    Always emit a single, stable "carrier" project name. The ``--only`` flag
    is an iteration shortcut (regenerate one sub-sheet), not a hint to
    rename the root project — KiCad workflows assume the project file name
    is stable across regenerations.
    """
    return "carrier"


def run_carrier(
    *,
    output_dir: Path | None,
    only_block: str | None,
    only_blocks: tuple[str, ...] | None = None,
    audit_only: bool,
    skip_erc: bool,
    allow_incomplete: bool,
    survey: bool = False,
) -> int:
    """Generate the carrier board. Returns the process exit code.

    When ``survey`` is set, the per-block layout loop never halts: every
    block is placed (placement failures are caught and recorded, not
    raised), validated *advisory-only* (``strict=False``), and emitted to
    ``sheets/`` regardless of findings — so all 27 sheets can be rendered
    and reconciled against the eye in one pass. The survey deliberately
    skips the root sheet / ERC / BOM stages and writes a per-block
    ``survey_report.md`` instead. This is a measurement mode; it never
    weakens the gating build (the default ``survey=False`` path is
    unchanged and still halts on the first finding).
    """
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
    blocks = carrier_project.build_blocks(only=only_block, only_blocks=only_blocks)
    print(f"  built {len(blocks)} block(s): {', '.join(b.name for b in blocks)}")

    # --- Stage 2.5: ExternalPart.from_pin reachability ---------------------
    # Every supporting part (decoupling cap, pull-up, series R) must attach
    # to a REAL symbol pin. A from_pin that names no pin is silently dropped
    # at layout time, hiding genuinely-missing circuitry. Gate the build on
    # it like overlap/bounds — a dropped part is a correctness defect.
    ext_part_results = validate_external_part_pins(blocks, geometry_cache)
    for r in ext_part_results:
        print(f"      EXTERNAL_PART: {r.message}")
    if ext_part_results:
        print()
        print(
            f"BUILD HALTED: {len(ext_part_results)} ExternalPart.from_pin "
            f"error(s) — supporting parts would be silently dropped. Fix the "
            f"refcircuit from_pin or the symbol (see messages above)."
        )
        return 1

    # --- Stages 4-6: Layout + Emit ------------------------------------------
    print()
    print("Stages 4-6: Layout + emit per block...")
    sheets_dir = resolved_output_dir / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    block_validation = ValidationReport()
    parent_uuid = str(uuid.uuid4())

    block_sub_sheets: list[tuple] = []  # (block, placed_sheet, relative_filename)
    survey_rows: list[tuple[str, int, int, str]] = []  # (name, bounds, overlap, note)

    # Assign each global power net ONE driving sheet (the first block that
    # produces it — power_kind output/ground — else the first that consumes it),
    # so exactly one PWR_FLAG stamp drives each net project-wide. Power symbols
    # are power-INPUT; without a flag, ERC fires power_pin_not_driven.
    stamp_assignment = _assign_power_stamps(blocks)

    for block in blocks:
        print(f"  block {block.name!r} ({block.title}):")
        try:
            # Convergent engine (Stages A–D): module solve → arrange → route →
            # label. Falls back to the legacy planner only if it raises (so a
            # block the new engine can't yet handle still builds in survey mode).
            try:
                sheet = route_sheet(
                    block, geometry_cache,
                    stamp_nets=stamp_assignment.get(block.name),
                )
            except Exception as route_error:  # noqa: BLE001
                if not survey:
                    raise
                print(
                    f"      ROUTE_SHEET FAILED ({type(route_error).__name__}: "
                    f"{route_error}); falling back to legacy place_block"
                )
                sheet = place_block(block, geometry_cache=geometry_cache)
        except Exception as place_error:  # noqa: BLE001 — survey must not abort
            if not survey:
                raise
            print(f"      PLACE FAILED: {type(place_error).__name__}: {place_error}")
            survey_rows.append(
                (block.name, -1, -1, f"place failed: {type(place_error).__name__}")
            )
            continue

        # Fail-fast: validate IMMEDIATELY after placement. If the sheet
        # violates any rule, halt before writing a broken .kicad_sch
        # to disk. Per the project's zero-overlap rule, any error here
        # means upstream placement needs to change — no warning, no
        # silent acceptance. In survey mode the findings are advisory
        # (strict=False) and never halt — the goal is to see them all.
        bounds_results = validate_page_bounds(sheet, geometry=geometry_cache)
        overlap_results = validate_overlap(
            sheet, geometry=geometry_cache, strict=not survey
        )
        block_validation.extend(bounds_results)
        block_validation.extend(overlap_results)
        # Connectivity — the electrical twin of overlap: every pin must
        # attach to a wire endpoint / label / no-connect / junction / pin.
        # ADVISORY for now (strict=False, never halts): the router does not
        # yet satisfy it on dense modules, so this surfaces the floating-pin
        # count per sheet for the router rebuild to drive to zero — exactly
        # the advisory→gated path overlap took. Calibrated faithful to KiCad
        # ERC pin_not_connected (a documented <=4-pin power-symbol geometry
        # edge case aside, tracked separately).
        connectivity_results = validate_connectivity(
            sheet, geometry=geometry_cache, strict=False
        )
        print(
            f"    placed: {len(sheet.symbols)} symbols, {len(sheet.wires)} wires, "
            f"{len(sheet.labels)} labels, {len(sheet.hierarchical_labels)} hlabels"
        )
        print(
            f"    in-memory validators: bounds={len(bounds_results)}, "
            f"overlap={len(overlap_results)}, floating_pins={len(connectivity_results)}"
        )
        for r in bounds_results:
            print(f"      BOUNDS: {r.message}")
        for r in overlap_results:
            print(f"      OVERLAP: {r.message}")
        if not survey and (bounds_results or overlap_results):
            # Persist whatever validation has accumulated so the user
            # can see the report, then halt the entire build.
            validation_path = resolved_output_dir / "validation_report.md"
            block_validation.write_markdown(
                validation_path, title="Carrier — Validation Report (PARTIAL)"
            )
            print()
            print(
                f"BUILD HALTED: block {block.name!r} produced "
                f"{len(bounds_results) + len(overlap_results)} validation "
                f"errors. No .kicad_sch emitted for this block or any "
                f"subsequent block. See "
                f"{validation_path.relative_to(REPO_ROOT)}."
            )
            return 1
        if survey:
            survey_rows.append(
                (block.name, len(bounds_results), len(overlap_results), "ok")
            )

        sheet_path = sheets_dir / f"{block.name}.kicad_sch"
        sheet_uuid = str(uuid.uuid4())
        # Aggregate per-IC lib_symbol pin-type overrides for this block.
        # Each override is (lib_id, pin_name, new_type) and corrects
        # mis-declared pin types in stock KiCad library symbols (e.g.
        # INA226 Vbus sense pin declared "input" instead of "passive").
        pin_type_overrides: list[tuple[str, str, str]] = []
        for ic in block.ics:
            for pin_name, new_type in ic.refcircuit.lib_symbol_pin_type_overrides:
                pin_type_overrides.append((ic.lib_id, pin_name, new_type))
        # A connector's power pins are PADS (physical connection points), not
        # power consumers — KiCad's stock/generated symbols mark them
        # "power_input", which fires bogus power_pin_not_driven on every pad
        # whose net has no in-sheet driver (J1 VBUS/GND, J5B GND_1/+3V3, …).
        # Override them to "passive": harmless on driven nets, clears the error
        # on undriven pads. (Real power consumers are ICs, handled above.)
        for conn in block.connectors:
            seen: set[str] = set()
            try:
                conn_pins = list(geometry_cache.all_pins(conn.lib_id))
            except Exception:  # noqa: BLE001
                conn_pins = []
            for pin in conn_pins:
                if "power" in str(pin.get("type", "")).lower():
                    nm = str(pin.get("name", "")).strip()
                    if nm and nm not in seen:
                        seen.add(nm)
                        pin_type_overrides.append((conn.lib_id, nm, "passive"))
        stats = emit_sheet(
            sheet,
            sheet_path,
            parent_uuid=parent_uuid,
            sheet_uuid=sheet_uuid,
            lib_symbol_pin_type_overrides=tuple(pin_type_overrides),
        )
        print(f"    emitted: {stats.output_path.relative_to(REPO_ROOT)}")
        block_sub_sheets.append((block, sheet, f"sheets/{block.name}.kicad_sch"))

    if survey:
        survey_path = resolved_output_dir / "survey_report.md"
        _write_survey_report(survey_path, survey_rows)
        emitted = sum(1 for _n, b, _o, note in survey_rows if note == "ok")
        total_overlap = sum(o for _n, _b, o, note in survey_rows if note == "ok")
        total_bounds = sum(b for _n, b, _o, note in survey_rows if note == "ok")
        failed = [n for n, _b, _o, note in survey_rows if note != "ok"]
        print()
        print(
            f"--survey: emitted {emitted}/{len(blocks)} sheet(s); "
            f"advisory totals: overlap={total_overlap}, bounds={total_bounds}"
            + (f", placement-failed={failed}" if failed else "")
        )
        print(f"  report: {survey_path.relative_to(REPO_ROOT)}")
        print("  render all: python -m zynq_eda.core.render --all")
        return 0

    # --- Stage 7: Root sheet + project file --------------------------------
    print()
    print("Stage 7: Root sheet + project file...")
    root_uuid = str(uuid.uuid4())
    root_sheet = build_root_sheet(
        title=carrier_project.CARRIER_TITLE,
        block_specs=[
            _BlockSheetSpec(block=blk, sub_sheet=sub, filename=fname)
            for (blk, sub, fname) in block_sub_sheets
        ],
    )
    root_bounds = validate_page_bounds(root_sheet, geometry=geometry_cache)
    root_overlap = validate_overlap(root_sheet, geometry=geometry_cache, strict=True)
    block_validation.extend(root_bounds)
    block_validation.extend(root_overlap)
    print(
        f"  root placed: {len(root_sheet.sheets)} sheet symbols, "
        f"{len(root_sheet.symbols)} drivers, {len(root_sheet.wires)} wires"
    )
    print(
        f"  root in-memory: bounds={len(root_bounds)}, overlap={len(root_overlap)}"
    )

    project_stem = _root_filename_stem(only_block)
    root_sheet_path = resolved_output_dir / f"{project_stem}.kicad_sch"
    root_stats = emit_root_sheet(
        root_sheet,
        root_sheet_path,
        root_uuid=root_uuid,
        project_name=project_stem,
    )
    print(f"  emitted: {root_stats.output_path.relative_to(REPO_ROOT)}")

    project_path = resolved_output_dir / f"{project_stem}.kicad_pro"
    emit_project(
        output_path=project_path,
        project_name=project_stem,
        root_schematic_filename=root_sheet_path.name,
        root_schematic_uuid=root_uuid,
    )
    print(f"  project: {project_path.relative_to(REPO_ROOT)}")

    # --- Stage 7b: ERC on the full hierarchy via the root ------------------
    print()
    print("Stage 7b: Validation (ERC on root)...")
    if not skip_erc:
        erc_results, erc_errors, erc_warnings = run_erc(root_sheet_path)
        block_validation.extend(erc_results)
        print(f"  ERC root: errors={erc_errors}, warnings={erc_warnings}")
    else:
        print("  --skip-erc: skipping kicad-cli ERC")

    validation_path = resolved_output_dir / "validation_report.md"
    block_validation.write_markdown(validation_path, title="Carrier — Validation Report")
    print(
        f"  total: errors={block_validation.error_count}, "
        f"warnings={block_validation.warning_count}"
    )
    print(f"  report: {validation_path.relative_to(REPO_ROOT)}")

    # --- Stage 8: Outputs (BOM CSV + IO assignment CSV + reference circuits MD) ----
    print()
    print("Stage 8: Output emitters (BOM / IO / reference circuits)...")
    from zynq_eda.catalog.registry.parts_registry import REGISTRY as _PARTS_REGISTRY

    class _CatalogView:
        """Adapter giving emit_bom an ``.all_parts()`` view of the registry."""

        @staticmethod
        def all_parts():
            return list(_PARTS_REGISTRY.values())

    bom_path = resolved_output_dir / "carrier_BOM.csv"
    emit_bom(
        blocks=blocks,
        root_sheet=root_sheet,
        sub_sheets=[sub for (_blk, sub, _fname) in block_sub_sheets],
        parts_catalog=_CatalogView,
        output_path=bom_path,
    )
    bom_row_count = _count_csv_rows(bom_path)
    print(
        f"  BOM:               {bom_path.relative_to(REPO_ROOT)} "
        f"({bom_row_count} rows)"
    )

    io_path = resolved_output_dir / "io_assignment.csv"
    emit_io_assignment(blocks=blocks, output_path=io_path)
    io_row_count = _count_csv_rows(io_path)
    print(
        f"  IO assignment:     {io_path.relative_to(REPO_ROOT)} "
        f"({io_row_count} rows)"
    )

    refcircuits_path = resolved_output_dir / "reference_circuits.md"
    emit_reference_circuits_md(blocks=blocks, output_path=refcircuits_path)
    ic_count = sum(len(b.ics) for b in blocks)
    print(
        f"  Reference circuits: {refcircuits_path.relative_to(REPO_ROOT)} "
        f"({ic_count} ICs)"
    )

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


def _count_csv_rows(path: Path) -> int:
    """Return the number of data rows (excluding the header) in a CSV file."""
    with path.open("r", encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def _write_survey_report(
    path: Path, rows: list[tuple[str, int, int, str]]
) -> None:
    """Write the per-block survey table (advisory overlap/bounds counts).

    ``rows`` are ``(block_name, bounds_count, overlap_count, note)``;
    a placement-failed block carries ``-1`` counts and a failure note.
    """
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = [r for r in rows if r[3] == "ok"]
    total_overlap = sum(o for _n, _b, o, _note in ok)
    total_bounds = sum(b for _n, b, _o, _note in ok)
    lines = [
        "# Carrier — Layout Survey (advisory, non-gating)",
        "",
        f"Generated: {stamp}",
        "",
        f"Emitted {len(ok)}/{len(rows)} sheets. "
        f"Advisory totals across emitted sheets: "
        f"**overlap={total_overlap}, bounds={total_bounds}**.",
        "",
        "These are the in-memory geometric validators only. The supreme "
        "judge is the render — see `boards/carrier/render/*.png` "
        "(`python -m zynq_eda.core.render --all`).",
        "",
        "| Block | bounds | overlap | note |",
        "|---|---:|---:|---|",
    ]
    for name, bounds, overlap, note in rows:
        b = "—" if bounds < 0 else str(bounds)
        o = "—" if overlap < 0 else str(overlap)
        lines.append(f"| {name} | {b} | {o} | {note} |")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
