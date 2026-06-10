"""Reconcile validator findings against the rendered page, per sheet.

``python -m zynq_eda.core.render.reconcile [--block NAME | --all]``

For each carrier block: place it, run the overlap validator (advisory),
emit the *exact* placed sheet to a temp ``.kicad_sch``, render that to PNG,
and draw the findings on top. Writes ``<name>.overlay.png`` next to the
plain ``<name>.png`` and prints a per-sheet finding count.

This is the operational form of "the render is the supreme judge": open
the overlays and confirm every drawn box sits on a real visual collision,
and that every visible crowd carries a box. Rendering the freshly-emitted
sheet (not a stale on-disk one) guarantees the pixels match the bboxes the
validator just measured.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import uuid
from pathlib import Path

from zynq_eda.core.emit import emit_sheet
from zynq_eda.core.layout import SymbolGeometryCache
from zynq_eda.core.layout.place import place_block
from zynq_eda.core.render.overlay import overlay_findings
from zynq_eda.core.render.raster import DEFAULT_DPI, render_sheet_to_png
from zynq_eda.core.validate.overlap import validate_overlap

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_RENDER_DIR = REPO_ROOT / "boards" / "carrier" / "render"


def reconcile_block(block, geometry, render_dir: Path, dpi: int) -> tuple[int, Path]:
    """Place, validate, render and overlay one block. Returns (n_findings, overlay_path)."""
    sheet = place_block(block, geometry_cache=geometry)
    findings = validate_overlap(sheet, geometry=geometry, strict=False)
    with tempfile.TemporaryDirectory(prefix="zynq_eda_reconcile_") as temp_dir:
        sch = Path(temp_dir) / f"{block.name}.kicad_sch"
        emit_sheet(
            sheet, sch, parent_uuid=str(uuid.uuid4()), sheet_uuid=str(uuid.uuid4())
        )
        raster = render_sheet_to_png(sch, render_dir / f"{block.name}.png", dpi=dpi)
    overlay = overlay_findings(
        raster, findings, render_dir / f"{block.name}.overlay.png"
    )
    return len(findings), overlay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zynq_eda.core.render.reconcile",
        description="Render carrier sheets and overlay validator findings.",
    )
    parser.add_argument("--block", action="append", metavar="NAME", help="Block name. Repeatable.")
    parser.add_argument("--all", action="store_true", help="Reconcile every block.")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--render-dir", type=Path, default=DEFAULT_RENDER_DIR)
    args = parser.parse_args(argv)

    from zynq_eda.projects import carrier as carrier_project

    geometry = SymbolGeometryCache()
    libs = tuple(p for p in carrier_project.SHARED_SYMBOL_LIBRARIES if p.exists())
    if libs:
        geometry.register_libraries(libs)

    if args.all:
        blocks = carrier_project.build_blocks(only=None)
    elif args.block and len(args.block) == 1:
        blocks = carrier_project.build_blocks(only=args.block[0])
    elif args.block:
        wanted = set(args.block)
        blocks = [b for b in carrier_project.build_blocks(only=None) if b.name in wanted]
    else:
        parser.print_help()
        print("\nPass --all or --block NAME.", file=sys.stderr)
        return 1

    total = 0
    print(f"Reconciling {len(blocks)} block(s) → {args.render_dir}")
    for block in blocks:
        try:
            count, overlay = reconcile_block(block, geometry, args.render_dir, args.dpi)
            total += count
            flag = "" if count == 0 else f"  <-- {count} finding(s)"
            print(f"  {block.name:32s} {count:4d}  {overlay.name}{flag}")
        except Exception as err:  # noqa: BLE001 — measurement tool, report and continue
            print(f"  {block.name:32s} FAILED: {type(err).__name__}: {err}")
    print(f"\nTotal findings across reconciled sheets: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
