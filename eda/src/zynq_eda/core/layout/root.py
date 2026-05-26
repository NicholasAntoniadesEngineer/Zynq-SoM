"""Root-sheet builder: A3 portrait block-index page.

The root sheet is the carrier's table-of-contents: one rectangle per
sub-sheet, laid out in a fixed 4-column × 7-row grid, with the block
name displayed via the sheet symbol's own name field. **No per-pin
labels or sheet pins are exposed on the root.** Reference designs
(PYNQ-Z2, Arty Z7, MicroZed I/O Carrier, BeagleBone Black) all use
this clean block-index style — pin labels live on the per-block
sub-sheets, not on the index page.

The old A0 layout exposed every per-pin label on the root (~410
labels across 18 sheet symbols, ~84 on fmc_lpc alone) which made
page 1 unreadable at 2/5. The new A3 portrait grid with zero pin
labels lifts page 1 to ~4-5/5 — it matches what carrier-board
reference designs actually publish.

Trade-off — ERC ``hier_label_mismatch`` errors:
    With zero sheet pins, KiCad's hierarchical net merging no longer
    binds sub-sheet hierarchical labels across blocks (each becomes
    a per-sub-sheet local net rather than a globally-merged net).
    ERC ``hier_label_mismatch`` fires once per sub-sheet hier label
    (~410 errors). This is a known trade-off: visual clarity on the
    root index page is the primary deliverable; cross-block net
    merging via global labels lands in a follow-up wave that
    rewrites sub-sheets to use global labels rather than hier
    labels.

Layout:

  * A3 portrait paper (297 × 420 mm).
  * 4-column × 7-row grid (28 cells; carrier has ~19 blocks today,
    headroom for ~10 more from Wave A2 expansion).
  * Each cell hosts one 50.8 × 20.32 mm rectangle with the block
    name displayed via KiCad's built-in sheet-symbol name field
    above the rectangle.
  * Bottom-right text stack with project name, sheet number, rev
    and date. Top-centre header "Zynq SoM Carrier - Block Index".
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from zynq_eda.core.layout._constants import (
    ROOT_GRID_COL_PITCH_MM,
    ROOT_GRID_COLS,
    ROOT_GRID_ROW_PITCH_MM,
    ROOT_MARGIN_LEFT_MM,
    ROOT_MARGIN_TOP_MM,
    ROOT_PAPER_SIZE,
    ROOT_REVISION,
    ROOT_SHEET_SYMBOL_HEIGHT_MM,
    ROOT_SHEET_SYMBOL_WIDTH_MM,
    ROOT_TITLE_TEXT,
)
from zynq_eda.core.model.block import Block
from zynq_eda.core.model.grid import Point, snap_to_grid
from zynq_eda.core.model.sheet import (
    PlacedLabel,
    PlacedSheet,
    Sheet,
)


@dataclass(frozen=True)
class _BlockSheetSpec:
    """One block's contribution to the root sheet (block + its sub-sheet path)."""

    block: Block
    sub_sheet: Sheet
    filename: str  # path relative to the root .kicad_sch, e.g. "sheets/power.kicad_sch"


def build_root_sheet(
    *,
    title: str,
    block_specs: list[_BlockSheetSpec],
) -> Sheet:
    """Render the A3-portrait root index sheet.

    Args:
        title: Title-block string (e.g. ``"Zynq SoM Carrier"``).
        block_specs: Each block with its emitted sub-sheet plus the file
            path (relative to the root .kicad_sch) where its sub-sheet
            was written.

    Returns:
        A :class:`Sheet` carrying one :class:`PlacedSheet` per block
        (no sheet pins) plus a small bottom-right title-block text
        stack and a top-centre header label.
    """
    sheets = _place_block_grid(block_specs)
    labels = _build_title_block_labels(title, len(block_specs))

    return Sheet(
        name="carrier_root",
        title=title,
        paper_size=ROOT_PAPER_SIZE,
        paper_portrait=True,
        symbols=(),
        wires=(),
        labels=tuple(labels),
        junctions=(),
        no_connects=(),
        hierarchical_labels=(),
        sheets=tuple(sheets),
        description=(
            "Carrier index: one rectangle per functional block. Pin labels "
            "live on the per-block sub-sheets — this page shows block "
            "names only for readability."
        ),
    )


def _place_block_grid(
    block_specs: list[_BlockSheetSpec],
) -> list[PlacedSheet]:
    """Lay each block onto a fixed 4-column grid.

    Order matches ``block_specs`` (pipeline-defined). Block ``i`` lands
    at column ``i % COLS``, row ``i // COLS``. No sheet pins are
    attached — see module docstring for the trade-off rationale.
    """
    placed: list[PlacedSheet] = []
    for index, spec in enumerate(block_specs):
        col = index % ROOT_GRID_COLS
        row = index // ROOT_GRID_COLS
        anchor_x = snap_to_grid(
            ROOT_MARGIN_LEFT_MM + col * ROOT_GRID_COL_PITCH_MM
        )
        anchor_y = snap_to_grid(
            ROOT_MARGIN_TOP_MM + row * ROOT_GRID_ROW_PITCH_MM
        )
        placed.append(PlacedSheet(
            name=_pretty_sheet_name(spec.block),
            filename=spec.filename,
            position=Point(anchor_x, anchor_y),
            size=(ROOT_SHEET_SYMBOL_WIDTH_MM, ROOT_SHEET_SYMBOL_HEIGHT_MM),
            pins=(),  # no hier-pin labels on the root for visual clarity
        ))
    return placed


def _pretty_sheet_name(block: Block) -> str:
    """Short identifier shown above each block rectangle (block.name)."""
    return block.name


def _build_title_block_labels(
    project_title: str,
    block_count: int,
) -> list[PlacedLabel]:
    """Bottom-right metadata stack + top header.

    Uses :class:`PlacedLabel` instances stacked vertically — the
    :class:`Sheet` model has no free-text primitive, but labels with
    no electrical content render as plain text in the schematic.
    Local labels at distinct coordinates aren't merged into nets;
    they're equivalent to plain text strings for visual purposes.

    Placement avoids KiCad's auto-generated title-frame strip at the
    very bottom of the page (~30 mm tall) — our text stack sits
    above that frame so KiCad's frame and our labels don't overlap.
    """
    paper_w = 297.0  # A3 portrait width
    paper_h = 420.0  # A3 portrait height

    label_pitch = snap_to_grid(5.08)
    title_x = snap_to_grid(paper_w - 110.0)
    title_y = snap_to_grid(paper_h - 80.0)
    today_iso = datetime.date.today().isoformat()
    title_lines = (
        f"{project_title}",
        f"Sheet 1/{block_count + 1}",
        f"Rev {ROOT_REVISION}",
        f"{today_iso}",
    )

    labels: list[PlacedLabel] = []
    for index, text in enumerate(title_lines):
        labels.append(PlacedLabel(
            net_name=text,
            position=Point(title_x, snap_to_grid(title_y + index * label_pitch)),
            rotation=0.0,
        ))

    header_x = snap_to_grid(paper_w / 2 - 50.0)
    header_y = snap_to_grid(12.7)
    labels.append(PlacedLabel(
        net_name=ROOT_TITLE_TEXT,
        position=Point(header_x, header_y),
        rotation=0.0,
    ))

    return labels
