"""Translate a :class:`Block` into a ``.kicad_sch`` file via ``kicad-sch-api``.

This module is the only place that imports ``kicad-sch-api``; every other
module talks to the in-memory model only. ``emit_block`` performs the full
sequence:

    1. Register any ``Block.symbol_library_paths`` with the global
       symbol-library cache so ``components.add`` can resolve their lib IDs.
    2. Build a fresh ``Schematic``, set its paper size + title block, and
       (when hierarchical UUIDs are supplied) install the hierarchy context.
    3. Add every ``PlacedComponent`` via ``components.add``.
    4. Emit wires, local labels, and hierarchical labels.
    5. Save the file atomically (write-and-rename).

The caller (typically ``sheets/root.py`` or ``pipeline.py``) provides the
two-half UUID pair for hierarchy context. Sub-sheets MUST receive both UUIDs
- omitting either is a hard error because KiCad will show "R?" annotations.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import kicad_sch_api as ksa

from scripts.carrier.emit.hierarchy import set_hierarchy_context
from scripts.carrier.model.block import Block, LocalLabel, PlacedComponent, SheetText, Wire
from scripts.carrier.model.interface import HierarchicalPin


@dataclass(frozen=True)
class BlockEmissionStats:
    """Counters returned by ``emit_block`` for the build log."""

    block_name: str
    schematic_path: Path
    placed_symbol_count: int
    wire_count: int
    junction_count: int
    local_label_count: int
    hierarchical_label_count: int


def _ensure_libraries_loaded(library_paths: tuple[str, ...]) -> None:
    """Register every block-required ``.kicad_sym`` with the symbol cache.

    ``kicad-sch-api``'s ``components.add`` looks up symbols through the
    global ``SymbolLibraryCache``. We add each library file exactly once;
    repeated calls with the same path are no-ops in the cache.
    """
    cache = ksa.get_symbol_cache()
    for relative_path in library_paths:
        library_path = Path(relative_path)
        if not library_path.is_absolute():
            raise ValueError(
                "Block.symbol_library_paths must be absolute paths after the "
                "block factory resolves them. Got relative path: "
                f"{relative_path!r}"
            )
        if not library_path.exists():
            raise FileNotFoundError(
                "Block requires symbol library that does not exist: "
                f"{library_path}"
            )
        cache.add_library_path(library_path)


def _emit_components(
    schematic: ksa.Schematic,
    placed_components: tuple[PlacedComponent, ...],
) -> int:
    for placed in placed_components:
        component = schematic.components.add(
            placed.lib_id,
            reference=placed.reference,
            value=placed.value,
            position=placed.position.as_tuple(),
            footprint=placed.footprint,
            rotation=placed.rotation,
        )
        for property_name, property_value in placed.properties:
            component.set_property(property_name, property_value)
    return len(placed_components)


def _emit_wires(schematic: ksa.Schematic, wires: tuple[Wire, ...]) -> int:
    for wire in wires:
        schematic.add_wire(wire.start.as_tuple(), wire.end.as_tuple())
    return len(wires)


def _emit_local_labels(
    schematic: ksa.Schematic,
    local_labels: tuple[LocalLabel, ...],
) -> int:
    for local_label in local_labels:
        schematic.add_label(
            local_label.net_name,
            position=local_label.position.as_tuple(),
            rotation=local_label.rotation,
        )
    return len(local_labels)


def _emit_hierarchical_labels(
    schematic: ksa.Schematic,
    hierarchical_pins: tuple[HierarchicalPin, ...],
    layout_width_mm: float,
    layout_interior_margin_mm: float,
) -> int:
    """Place one hierarchical_label inside the sub-sheet per ``HierarchicalPin``.

    The label sits at the sheet's left or right edge (just inside the
    interior margin) at the pin's ``position_along_edge`` Y-coordinate.
    Block factories are responsible for wiring their internal nets up to
    these labels with explicit wires before emission.
    """
    for hierarchical_pin in hierarchical_pins:
        if hierarchical_pin.label_position is not None:
            label_x = hierarchical_pin.label_position.x
            label_y = hierarchical_pin.label_position.y
        elif hierarchical_pin.edge.value == "left":
            label_x = layout_interior_margin_mm
            label_y = hierarchical_pin.position_along_edge
        elif hierarchical_pin.edge.value == "right":
            label_x = layout_width_mm - layout_interior_margin_mm
            label_y = hierarchical_pin.position_along_edge
        else:
            raise NotImplementedError(
                "Hierarchical pins on top/bottom edges are not used by any "
                "current block; placement rules undefined."
            )
        if hierarchical_pin.edge.value == "left":
            rotation = 180.0
        elif hierarchical_pin.edge.value == "right":
            rotation = 0.0
        else:
            rotation = 0.0
        schematic.add_hierarchical_label(
            hierarchical_pin.net_name,
            position=(label_x, label_y),
            shape=hierarchical_pin.direction.value,
            rotation=rotation,
        )
    return len(hierarchical_pins)


def _emit_sheet_texts(
    schematic: ksa.Schematic,
    sheet_texts: tuple[SheetText, ...],
) -> int:
    for sheet_text in sheet_texts:
        schematic.add_text(
            sheet_text.text,
            position=sheet_text.position.as_tuple(),
            rotation=sheet_text.rotation,
        )
    return len(sheet_texts)


def _hide_hierarchy_path_properties(schematic_path: Path) -> None:
    """Post-save patch: hide hierarchy_path on every symbol instance."""
    raw_text = schematic_path.read_text(encoding="utf-8")
    patched = raw_text.replace(
        '(property "hierarchy_path"',
        '(property "hierarchy_path"',
    )
    # Insert (hide yes) into hierarchy_path property effects if absent
    import re

    def _hide_property(match: re.Match[str]) -> str:
        block = match.group(0)
        if "(hide yes)" in block:
            return block
        return block.replace(
            "(effects\n\t\t\t\t(font",
            "(effects\n\t\t\t\t(hide yes)\n\t\t\t\t(font",
            1,
        )

    patched = re.sub(
        r'\(property "hierarchy_path"[^\)]*\)[\s\S]*?\)\s*\)',
        _hide_property,
        patched,
        count=0,
    )
    if patched != raw_text:
        schematic_path.write_text(patched, encoding="utf-8")


def _atomic_save(schematic: ksa.Schematic, output_path: Path) -> None:
    """Write the schematic via a temp file in the same directory + rename.

    Eliminates the half-written-file risk if KiCad / the OS crashes during
    save, satisfying the compliance rule "Output files are written
    atomically (temp + rename)".
    """
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


def emit_block(
    block: Block,
    output_path: Path,
    parent_uuid: str,
    sheet_uuid: str,
) -> BlockEmissionStats:
    """Render a single ``Block`` to ``output_path``.

    Args:
        block: The fully-built block.
        output_path: Where to write the ``.kicad_sch``. Parent directories
            are created if missing. Written atomically.
        parent_uuid: UUID of the root sheet; required for hierarchical
            reference annotation.
        sheet_uuid: UUID of the parent-side sheet symbol pointing at this
            sub-sheet; required for hierarchical reference annotation.

    Returns:
        Per-block counters suitable for ``CarrierBuildLog.log_block``.
    """
    _ensure_libraries_loaded(block.symbol_library_paths)

    schematic = ksa.create_schematic(block.title)
    schematic.set_paper_size(block.layout.paper_size)
    schematic.title_block["title"] = block.title

    with set_hierarchy_context(schematic, parent_uuid, sheet_uuid):
        placed_count = _emit_components(schematic, block.components)
        wire_count = _emit_wires(schematic, block.wires)
        local_label_count = _emit_local_labels(schematic, block.local_labels)
        hierarchical_label_count = _emit_hierarchical_labels(
            schematic,
            block.hierarchical_pins,
            layout_width_mm=block.layout.width_mm,
            layout_interior_margin_mm=block.layout.interior_margin_mm,
        )
        _emit_sheet_texts(schematic, block.sheet_texts)

    _atomic_save(schematic, output_path)
    _hide_hierarchy_path_properties(output_path)

    return BlockEmissionStats(
        block_name=block.name,
        schematic_path=output_path,
        placed_symbol_count=placed_count,
        wire_count=wire_count,
        junction_count=len(schematic.junctions),
        local_label_count=local_label_count,
        hierarchical_label_count=hierarchical_label_count,
    )
