"""``python -m zynq_eda.core.render`` — render carrier sheets to PNG.

The fast inner loop for judging layout against the rendered page::

    python -m zynq_eda.core.render --sheet power      # one sheet
    python -m zynq_eda.core.render --all              # every sheet on disk
    python -m zynq_eda.core.render --input foo.kicad_sch --output foo.png

Output defaults to ``boards/carrier/render/<name>.png``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from zynq_eda.core.render.raster import DEFAULT_DPI, render_sheet_to_png

# .../Zynq-SoM/eda/src/zynq_eda/core/render/__main__.py → parents[5] = repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_SHEETS_DIR = REPO_ROOT / "boards" / "carrier" / "sheets"
DEFAULT_RENDER_DIR = REPO_ROOT / "boards" / "carrier" / "render"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m zynq_eda.core.render",
        description="Render carrier schematic sheets to PNG (the supreme judge).",
    )
    parser.add_argument(
        "--sheet",
        action="append",
        metavar="NAME",
        help="Sheet name without extension (e.g. power). Repeatable.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Render every .kicad_sch in the sheets directory.",
    )
    parser.add_argument("--input", type=Path, help="Render an arbitrary .kicad_sch file.")
    parser.add_argument("--output", type=Path, help="Output PNG path (with --input).")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"Render DPI (default {DEFAULT_DPI}).")
    parser.add_argument("--sheets-dir", type=Path, default=DEFAULT_SHEETS_DIR)
    parser.add_argument("--render-dir", type=Path, default=DEFAULT_RENDER_DIR)
    return parser


def _render_one(sch_path: Path, png_path: Path, dpi: int) -> int:
    raster = render_sheet_to_png(sch_path, png_path, dpi=dpi)
    print(
        f"  {sch_path.name} → {png_path}  "
        f"({raster.width_px}×{raster.height_px}px, "
        f"{raster.page_w_mm:.0f}×{raster.page_h_mm:.0f}mm)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.input is not None:
        out = args.output or (args.render_dir / (args.input.stem + ".png"))
        return _render_one(args.input, out, args.dpi)

    if args.all:
        sheets = sorted(args.sheets_dir.glob("*.kicad_sch"))
        if not sheets:
            print(f"No .kicad_sch files in {args.sheets_dir}", file=sys.stderr)
            return 1
        print(f"Rendering {len(sheets)} sheet(s) → {args.render_dir}")
        for sch in sheets:
            _render_one(sch, args.render_dir / (sch.stem + ".png"), args.dpi)
        return 0

    if args.sheet:
        for name in args.sheet:
            sch = args.sheets_dir / f"{name}.kicad_sch"
            if not sch.exists():
                print(f"Sheet not found: {sch}", file=sys.stderr)
                return 1
            _render_one(sch, args.render_dir / f"{name}.png", args.dpi)
        return 0

    _build_parser().print_help()
    print("\nNothing to render; pass --sheet, --all, or --input.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
