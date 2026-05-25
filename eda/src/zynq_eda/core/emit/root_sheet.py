"""Root-sheet emitter: Sheet (with embedded PlacedSheet symbols) → .kicad_sch.

Mirrors :mod:`zynq_eda.core.emit.schematic` but additionally renders
``(sheet ...)`` blocks via kicad-sch-api's ``add_sheet`` + ``add_sheet_pin``.
The same workaround for the ``set_hierarchy_context`` connectivity bug
applies (see :mod:`zynq_eda.core.emit.schematic` for the full rationale):
we never call ``set_hierarchy_context``.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import kicad_sch_api as ksa

from zynq_eda.core.emit.schematic import (
    EmissionStats,
    _atomic_save,
    _hide_internal_properties,
)
from zynq_eda.core.model.sheet import Sheet


@dataclass(frozen=True)
class RootEmissionStats(EmissionStats):
    """Adds sheet-symbol + sheet-pin counts to :class:`EmissionStats`."""

    sheet_symbol_count: int = 0
    sheet_pin_count: int = 0


def emit_root_sheet(
    sheet: Sheet,
    output_path: Path,
    *,
    root_uuid: str | None = None,
    project_name: str,
) -> RootEmissionStats:
    """Render the root :class:`Sheet` to a ``.kicad_sch`` (atomic write).

    Args:
        sheet: The root sheet (carries a non-empty ``sheets`` tuple).
        output_path: Destination file path.
        root_uuid: Optional UUID for the root schematic. Generated if omitted.
            Passed back via the returned stats so the project-file emitter
            can wire it into ``schematic.top_level_sheets[0].uuid``.
        project_name: Name written into each sub-sheet symbol's
            ``(project ...)`` instance entry. Must match the
            ``.kicad_pro`` filename stem (KiCad uses it to bind sub-sheet
            symbol instances back to the parent project).
    """
    root_id = root_uuid or str(uuid.uuid4())

    schematic = ksa.create_schematic(sheet.title)
    schematic.set_paper_size(sheet.paper_size)
    schematic.title_block["title"] = sheet.title
    if sheet.description:
        schematic.title_block["comment1"] = sheet.description

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

    # The defining piece for a root sheet: every PlacedSheet becomes a
    # (sheet ...) symbol with its hierarchical pins on the declared edges.
    sheet_pin_total = 0
    for placed_sheet in sheet.sheets:
        sheet_uuid = schematic.add_sheet(
            name=placed_sheet.name,
            filename=placed_sheet.filename,
            position=placed_sheet.position.as_tuple(),
            size=placed_sheet.size,
            project_name=project_name,
        )
        for sheet_pin in placed_sheet.pins:
            schematic.add_sheet_pin(
                sheet_uuid=sheet_uuid,
                name=sheet_pin.name,
                pin_type=sheet_pin.direction,
                edge=sheet_pin.edge,
                position_along_edge=sheet_pin.position_along_edge,
            )
            sheet_pin_total += 1

    _atomic_save(schematic, output_path)
    _hide_internal_properties(output_path)

    return RootEmissionStats(
        sheet_name=sheet.name,
        output_path=output_path,
        placed_symbol_count=len(sheet.symbols),
        wire_count=len(sheet.wires),
        label_count=len(sheet.labels),
        hierarchical_label_count=len(sheet.hierarchical_labels),
        junction_count=len(sheet.junctions),
        no_connect_count=len(sheet.no_connects),
        sheet_symbol_count=len(sheet.sheets),
        sheet_pin_count=sheet_pin_total,
    )
