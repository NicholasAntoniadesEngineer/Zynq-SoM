"""Command-line interface for the Zynq-EDA schematic generator.

Usage::

    python -m zynq_eda --board carrier --output boards/carrier
    python -m zynq_eda --board carrier --audit-only
    python -m zynq_eda --board carrier --only power
    python -m zynq_eda --board carrier --skip-erc

Subsequent stages of the rewrite will wire the carrier pipeline into the
``--board carrier`` branch. Today the CLI parses arguments, validates the
chosen board against the known set, and reports back. The actual pipeline
lives in ``zynq_eda.core.pipeline`` (still under construction).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from zynq_eda import __version__


KNOWN_BOARDS: tuple[str, ...] = ("carrier",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zynq_eda",
        description=(
            "Generate production-grade KiCad schematics for the Zynq-SoM "
            "carrier (and future Zynq-family boards). The single source of "
            "truth is Python; the output is pristine .kicad_sch files."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"zynq_eda {__version__}",
    )
    parser.add_argument(
        "--board",
        choices=KNOWN_BOARDS,
        help="Which board to generate. Required for any non-version action.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Output directory for the board's .kicad_sch and project files. "
            "Defaults to boards/<board>/ relative to the repo root."
        ),
    )
    parser.add_argument(
        "--only",
        metavar="BLOCK",
        help="Generate just one block (iteration shortcut).",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Run Stage 0 component-completeness audit and exit.",
    )
    parser.add_argument(
        "--skip-erc",
        action="store_true",
        help="Skip running kicad-cli sch erc on the generated output.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "Allow generation to proceed even when the Stage 0 audit "
            "reports missing components (useful for in-progress runs)."
        ),
    )
    parser.add_argument(
        "--survey",
        action="store_true",
        help=(
            "Measurement mode: place, validate (advisory), and emit EVERY "
            "block sheet without halting on findings, then write "
            "survey_report.md. Skips root/ERC/outputs. Intended to be "
            "paired with `python -m zynq_eda.core.render --all`."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.board is None:
        parser.print_help()
        print("\nNo --board specified; nothing to do.", file=sys.stderr)
        return 0

    if args.board == "carrier":
        try:
            from zynq_eda.core import pipeline
        except ImportError as import_error:
            print(
                f"zynq_eda.core.pipeline not yet implemented: {import_error}",
                file=sys.stderr,
            )
            return 2
        return pipeline.run_carrier(
            output_dir=args.output,
            only_block=args.only,
            audit_only=args.audit_only,
            skip_erc=args.skip_erc,
            allow_incomplete=args.allow_incomplete,
            survey=args.survey,
        )

    print(f"Unknown board: {args.board!r}", file=sys.stderr)
    return 2
