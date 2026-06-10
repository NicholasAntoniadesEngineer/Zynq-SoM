"""Reference-circuits markdown emitter.

Emits one section per IC instance, summarising its :class:`ReferenceCircuit`:
datasheet reference, supply rail, external parts, pin overrides, and
layout notes. The output is the human-readable design-intent record an
EE skims before tape-out to confirm every IC's manufacturer reference
design was actually applied.

Each section is keyed on the IC's reference designator + part MPN so the
same part used in two blocks gets two sections (each may carry block-
specific pin overrides).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from zynq_eda.core.model.block import Block, IcInstance
from zynq_eda.core.model.refcircuit import ReferenceCircuit


def emit_reference_circuits_md(
    *,
    blocks: list[Block],
    output_path: Path,
) -> None:
    """One markdown section per IC, summarising its refcircuit.

    Args:
        blocks: The carrier's blocks.
        output_path: Where to write the markdown file. Atomic write via tempfile.
    """
    if output_path.suffix != ".md":
        raise ValueError(f"output_path must end in .md, got {output_path}")

    sections: list[str] = []
    sections.append(_header())

    # Table of contents
    toc_lines = ["## Contents", ""]
    for block in blocks:
        for ic in block.ics:
            toc_lines.append(f"- [{ic.reference} — {ic.refcircuit.part_mpn}]"
                             f"(#{_anchor(ic.reference, ic.refcircuit.part_mpn)})")
    toc_lines.append("")
    sections.append("\n".join(toc_lines))

    # Per-IC sections
    for block in blocks:
        for ic in block.ics:
            sections.append(_render_ic_section(block=block, ic=ic))

    markdown = "\n".join(sections).rstrip() + "\n"
    _atomic_write_text(output_path=output_path, content=markdown)


# ---------------------------------------------------------------------------
# Section rendering
# ---------------------------------------------------------------------------


def _header() -> str:
    return (
        "# Carrier Reference Circuits\n"
        "\n"
        "Auto-generated design-intent record. For every IC on the carrier, "
        "this document shows the manufacturer reference circuit applied: "
        "every external part required by the datasheet, pin overrides, and "
        "layout notes. The EE reviews this document before PCB tape-out to "
        "confirm the carrier design follows each IC's reference design.\n"
    )


def _render_ic_section(*, block: Block, ic: IcInstance) -> str:
    rc: ReferenceCircuit = ic.refcircuit
    lines: list[str] = []
    lines.append(f"## {ic.reference} — {rc.part_mpn}")
    lines.append("")
    lines.append(f"**Block:** {block.name}  ")
    lines.append(
        f"**Datasheet:** [{rc.part_mpn}]({rc.datasheet_url})"
        f"{_format_figure_page(rc)}  "
    )
    lines.append(f"**Footprint:** {rc.footprint}  ")
    if rc.supply_rail:
        lines.append(f"**Supply rail:** {rc.supply_rail}  ")
    lines.append(
        f"**Min-circuit verified:** "
        f"{'yes' if rc.minimum_circuit_verified else 'no'}  "
    )
    if rc.description:
        lines.append("")
        lines.append(rc.description)
    lines.append("")

    lines.append("### External parts")
    lines.append("")
    if rc.external_parts:
        lines.append("| From pin | To net | Part token | Qty | Why |")
        lines.append("|---|---|---|---|---|")
        for ext in rc.external_parts:
            lines.append(
                f"| {_md_cell(ext.from_pin)} | {_md_cell(ext.to_net)} | "
                f"{_md_cell(ext.part_token)} | {ext.quantity} | "
                f"{_md_cell(ext.justification)} |"
            )
    else:
        lines.append("_None._")
    lines.append("")

    # Combined per-IC overrides: refcircuit + IcInstance
    overrides: list[tuple[str, str]] = list(rc.pin_net_overrides) + list(ic.net_overrides)
    lines.append("### Pin overrides")
    lines.append("")
    if overrides:
        lines.append("| Pin | Net |")
        lines.append("|---|---|")
        for pin, net in overrides:
            lines.append(f"| {_md_cell(pin)} | {_md_cell(net)} |")
    else:
        lines.append("_None._")
    lines.append("")

    if rc.strap_pins:
        lines.append("### Strap pins")
        lines.append("")
        lines.append("| Pin | Tied to | Purpose | Why |")
        lines.append("|---|---|---|---|")
        for strap in rc.strap_pins:
            lines.append(
                f"| {_md_cell(strap.pin)} | {_md_cell(strap.tied_to)} | "
                f"{_md_cell(strap.purpose)} | {_md_cell(strap.justification)} |"
            )
        lines.append("")

    if rc.no_external_required:
        no_ext = sorted(rc.no_external_required)
        lines.append("### No external required")
        lines.append("")
        lines.append(f"_Pins explicitly left bare:_ {', '.join(no_ext)}")
        lines.append("")

    lines.append("### Layout notes")
    lines.append("")
    if rc.layout_notes:
        for note in rc.layout_notes:
            severity_tag = (
                f" ({note.severity})" if note.severity and note.severity != "info" else ""
            )
            extra = f" — _{note.justification}_" if note.justification else ""
            lines.append(f"- {note.text}{severity_tag}{extra}")
    else:
        lines.append("_None recorded._")
    lines.append("")
    return "\n".join(lines)


def _format_figure_page(rc: ReferenceCircuit) -> str:
    parts: list[str] = []
    if rc.app_circuit_figure:
        parts.append(rc.app_circuit_figure)
    if rc.app_circuit_page:
        parts.append(rc.app_circuit_page)
    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"


def _md_cell(text: str) -> str:
    """Escape a cell so newlines / pipes don't break the markdown table."""
    if not text:
        return ""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _anchor(reference: str, mpn: str) -> str:
    """GitHub-flavoured anchor: lowercase, spaces→hyphens, drop unsafe chars."""
    raw = f"{reference}-{mpn}".lower()
    out: list[str] = []
    for ch in raw:
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        elif ch in {" ", "—", "/"}:
            out.append("-")
        # everything else dropped (matches GitHub's slugger closely enough)
    return "".join(out)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_text(*, output_path: Path, content: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(
        prefix=output_path.stem + ".",
        suffix=output_path.suffix + ".tmp",
        dir=str(output_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_path_str)
    try:
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
