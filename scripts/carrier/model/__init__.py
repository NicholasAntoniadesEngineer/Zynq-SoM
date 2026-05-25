"""Domain model for hierarchical carrier blocks.

Exports the data structures every block factory and emit adapter consumes:

    * ``Block``                – one functional sheet's content
    * ``BlockLayout``          – paper size + interior margins
    * ``HierarchicalPin``      – the parent-side wiring contract of a block
    * ``IcBlockTemplate``      – per-pin-group placement offsets for an IC
    * ``ReferenceCircuit`` etc – datasheet-derived per-IC support network

This package is pure data + small geometry helpers; it has no dependency on
``kicad-sch-api`` or ``kicad-skip``. The ``emit/`` package translates these
models into ``.kicad_sch`` files.
"""

from scripts.carrier.model.block import (
    Block,
    BlockLayout,
    PlacedComponent,
    Wire,
    LocalLabel,
)
from scripts.carrier.model.grid import (
    GRID_TOLERANCE_MM,
    KICAD_GRID_MM,
    Point,
    assert_on_grid,
    snap_to_grid,
)
from scripts.carrier.model.interface import HierarchicalPin, PinDirection, SheetEdge
from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
    StrapPin,
)
from scripts.carrier.model.templates import (
    IcBlockTemplate,
    PinGroup,
    PinGroupOffset,
)


__all__ = [
    "Block",
    "BlockLayout",
    "ExternalPart",
    "GRID_TOLERANCE_MM",
    "HierarchicalPin",
    "IcBlockTemplate",
    "KICAD_GRID_MM",
    "LayoutNote",
    "LocalLabel",
    "PinDirection",
    "PinGroup",
    "PinGroupOffset",
    "PlacedComponent",
    "Point",
    "ReferenceCircuit",
    "SheetEdge",
    "StrapPin",
    "Wire",
    "assert_on_grid",
    "snap_to_grid",
]
