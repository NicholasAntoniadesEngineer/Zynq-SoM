"""Context manager for ``kicad-sch-api``'s hierarchy-context requirement.

KiCad needs every symbol on a sub-sheet annotated with the parent project
path and sheet UUID so reference designators show as ``R12`` instead of
``R?``. ``kicad-sch-api`` exposes this via ``Schematic.set_hierarchy_context``
which must be called BEFORE any component is added.

This module wraps the call in a ``with`` block so every block emitter uses
it the same way and we get a fail-hard if anyone forgets.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import kicad_sch_api as ksa


@contextmanager
def set_hierarchy_context(
    schematic: ksa.Schematic,
    parent_uuid: str,
    sheet_uuid: str,
) -> Iterator[ksa.Schematic]:
    """Install the parent/sheet UUID pair before adding any components.

    Args:
        schematic: A freshly-created ``Schematic`` (no components added yet).
        parent_uuid: UUID of the root ``carrier_template.kicad_sch``.
        sheet_uuid: UUID of the sheet symbol on the root sheet that points
            at this sub-sheet's file.

    Yields:
        The same schematic, configured for hierarchical annotation.
    """
    if not parent_uuid:
        raise ValueError(
            "set_hierarchy_context.parent_uuid must be non-empty; KiCad needs "
            "it for hierarchical reference annotation"
        )
    if not sheet_uuid:
        raise ValueError(
            "set_hierarchy_context.sheet_uuid must be non-empty; KiCad needs "
            "it for hierarchical reference annotation"
        )
    schematic.set_hierarchy_context(parent_uuid=parent_uuid, sheet_uuid=sheet_uuid)
    yield schematic
