"""Sheet → .kicad_sch via kicad-sch-api.

Atomic write: emit to a temp file in the destination directory then rename
into place. Eliminates half-written files on crash.

KNOWN ISSUE — ``kicad-sch-api`` 0.5.5/0.5.6 ``add_wire`` connectivity bug
========================================================================

Wires emitted by ``schematic.add_wire(start, end)`` do **not** form
electrical connections between passive pins, even when both endpoints
land at the exact KiCad-canonical pin positions.

Minimal reproducer::

    sch = ksa.create_schematic('repro')
    sch.set_hierarchy_context(...)
    r1 = sch.components.add('Device:R', reference='R1', value='1k',
                            position=(100.0, 100.0), rotation=90)
    r2 = sch.components.add('Device:R', reference='R2', value='1k',
                            position=(120.0, 100.0), rotation=90)
    # KiCad pin positions for rot 90: R1.2 at (103.81, 100),
    # R2.1 at (116.19, 100). Power-symbol probe confirms.
    sch.add_wire((103.81, 100.0), (116.19, 100.0))
    sch.components.add('power:+5V', reference='#PWR1', position=(96.19, 100.0))
    sch.components.add('power:GND', reference='#PWR2', position=(123.81, 100.0))
    sch.save_as('repro.kicad_sch')
    # kicad-cli sch export netlist:
    #   Expected: one merged net containing R1.2 + R2.1
    #   Actual:   no net contains the middle wire — R1.2 and R2.1 missing

Power symbols *do* register at the same coordinates (placing
``power:+5V`` at ``(103.81, 100)`` correctly nets it to R1.2). So the
pin positions are not the issue — only ``add_wire`` is broken.

Consequence: every passive-to-IC-pin wire we emit is visually drawn but
electrically inert. ERC reports it as ``wire_dangling`` and the affected
IC pins as floating. The schematic still looks correct on screen.

Workarounds (none implemented yet — pending Stage 5 layout-engine work):
 * Bypass ``kicad-sch-api`` for wire emission and write our own
   ``(wire ...)`` s-expression blocks.
 * Lift the connection through a named local label at one wire endpoint
   (KiCad treats same-name local labels as connected).
 * Switch the entire emit stage to a different library or a hand-built
   s-expression writer.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import kicad_sch_api as ksa

from zynq_eda.core.model.sheet import Sheet


@dataclass(frozen=True)
class EmissionStats:
    """Counters returned by :func:`emit_sheet` for the build log."""

    sheet_name: str
    output_path: Path
    placed_symbol_count: int
    wire_count: int
    label_count: int
    hierarchical_label_count: int
    junction_count: int
    no_connect_count: int = 0


_PREVIEW_PARENT_UUID = str(uuid.uuid4())  # set once per pipeline run
_PREVIEW_SHEET_UUID = str(uuid.uuid4())


def emit_sheet(
    sheet: Sheet,
    output_path: Path,
    *,
    parent_uuid: str | None = None,
    sheet_uuid: str | None = None,
) -> EmissionStats:
    """Render a :class:`Sheet` to a ``.kicad_sch`` file (atomic write).

    Args:
        sheet: The placed sheet to emit.
        output_path: Where to write the file. Parent dirs are created.
        parent_uuid, sheet_uuid: UUIDs for the hierarchical reference
            annotation. When omitted, fresh UUIDs are generated (suitable
            for standalone-sheet tests). For real hierarchical projects,
            the root sheet emitter passes the parent + sheet UUIDs it
            allocated when adding the sheet symbol.
    """
    parent = parent_uuid or _PREVIEW_PARENT_UUID
    sheet_id = sheet_uuid or _PREVIEW_SHEET_UUID

    schematic = ksa.create_schematic(sheet.title)
    schematic.set_paper_size(sheet.paper_size)
    schematic.title_block["title"] = sheet.title
    if sheet.description:
        schematic.title_block["comment1"] = sheet.description
    schematic.set_hierarchy_context(parent_uuid=parent, sheet_uuid=sheet_id)

    for placed in sheet.symbols:
        component = schematic.components.add(
            placed.lib_id,
            reference=placed.reference,
            value=placed.value,
            position=placed.position.as_tuple(),
            footprint=placed.footprint,
            rotation=placed.rotation,
        )
        for property_name, property_value in placed.properties:
            try:
                component.set_property(property_name, property_value)
            except Exception:
                # Some property names are reserved by kicad-sch-api; skip
                # gracefully rather than fail the whole emission.
                continue

    for wire in sheet.wires:
        schematic.add_wire(wire.start.as_tuple(), wire.end.as_tuple())

    for label in sheet.labels:
        schematic.add_label(
            label.net_name,
            position=label.position.as_tuple(),
            rotation=label.rotation,
        )

    for hlabel in sheet.hierarchical_labels:
        schematic.add_hierarchical_label(
            hlabel.net_name,
            position=hlabel.position.as_tuple(),
            shape=hlabel.direction,
            rotation=hlabel.rotation,
        )

    for junction in sheet.junctions:
        schematic.add_junction(junction.position.as_tuple())

    for no_connect in sheet.no_connects:
        schematic.no_connects.add(position=no_connect.position.as_tuple())

    _atomic_save(schematic, output_path)
    _hide_internal_properties(output_path)

    return EmissionStats(
        sheet_name=sheet.name,
        output_path=output_path,
        placed_symbol_count=len(sheet.symbols),
        wire_count=len(sheet.wires),
        label_count=len(sheet.labels),
        hierarchical_label_count=len(sheet.hierarchical_labels),
        junction_count=len(sheet.junctions),
        no_connect_count=len(sheet.no_connects),
    )


_INTERNAL_PROPERTIES_TO_HIDE: tuple[str, ...] = (
    "hierarchy_path",  # kicad-sch-api annotation; KiCad renders it as text
                       # next to every symbol unless explicitly hidden.
)


def _hide_internal_properties(schematic_path: Path) -> None:
    """Inject ``(hide yes)`` into the effects block of every internal property.

    kicad-sch-api 0.5.6 emits a ``hierarchy_path`` property on every placed
    symbol but does not mark it hidden, so KiCad renders the UUID path next
    to every component on the sheet — the schematic becomes unreadable.

    This pass scans the file line-by-line, finds the ``(effects`` block that
    immediately follows any matching property, and inserts ``(hide yes)``
    inside that block (no-op if already hidden).
    """
    lines = schematic_path.read_text(encoding="utf-8").splitlines()

    in_target_property = False
    awaiting_effects = False
    modified = False
    new_lines: list[str] = []
    target_names = {f'"{name}"' for name in _INTERNAL_PROPERTIES_TO_HIDE}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("(property "):
            tokens = stripped.split()
            if len(tokens) >= 2 and tokens[1] in target_names:
                in_target_property = True
                awaiting_effects = True
                new_lines.append(line)
                continue
            in_target_property = False
            awaiting_effects = False

        if awaiting_effects and stripped == "(effects":
            new_lines.append(line)
            # Compute indent of the effects content (one level deeper than (effects).
            effects_indent_len = len(line) - len(line.lstrip())
            child_indent = "\t" * ((effects_indent_len // 1) + 1)
            # Use tab indent to match KiCad's style; len of line.lstrip's whitespace
            # gives us the existing indent character set.
            existing_indent = line[:effects_indent_len]
            child_indent = existing_indent + "\t"
            new_lines.append(f"{child_indent}(hide yes)")
            awaiting_effects = False
            in_target_property = False
            modified = True
            continue

        # If the property closes without an (effects block, reset state.
        if in_target_property and stripped == ")":
            in_target_property = False
            awaiting_effects = False

        new_lines.append(line)

    if modified:
        schematic_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _atomic_save(schematic: ksa.Schematic, output_path: Path) -> None:
    """Write the schematic via a temp file in the same directory + rename."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(
        prefix=output_path.stem + ".",
        suffix=".kicad_sch.tmp",
        dir=str(output_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_path_str)
    try:
        schematic.save_as(temp_path)
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
