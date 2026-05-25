"""Sheet-to-parent connectivity contract.

Every ``Block`` exposes a tuple of ``HierarchicalPin`` instances that defines
its wiring contract with the root sheet. The ``sheets/root.py`` builder uses
these pins to:

    1. Size the parent-side sheet symbol.
    2. Connect inter-block nets by matching pin name across blocks.
    3. Validate that no block references an unknown pin or has duplicate
       pin names.

The ``shape``/``pin_type`` taxonomy follows KiCad's exact set of allowed
values for hierarchical labels and sheet pins. Using anything else makes
``kicad-cli sch erc`` complain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from scripts.carrier.model.grid import Point


class PinDirection(str, Enum):
    """Allowed hierarchical-pin shapes (matches KiCad 9 ``pin`` ``shape`` set).

    The string values are exactly what ``kicad-sch-api.add_sheet_pin`` and
    ``add_hierarchical_label`` expect for the ``pin_type`` / ``shape`` field.
    """

    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"


class SheetEdge(str, Enum):
    """Which edge of a sheet symbol a hierarchical pin lives on.

    Sheet pins are placed on the left or right edge in KiCad-canonical use;
    top/bottom are supported by KiCad but uncommon. Block builders always
    pick ``LEFT`` or ``RIGHT`` so the sub-sheet looks like a clean black box
    on the root page.
    """

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True)
class HierarchicalPin:
    """One entry in a block's externally visible wiring contract.

    Attributes:
        net_name: The net name the parent sheet sees. Must match exactly the
            hierarchical-label text emitted inside the sub-sheet (KiCad
            requirement; mismatch is a silent disconnection).
        direction: One of the KiCad-canonical pin shapes (``PinDirection``).
        edge: Which edge of the parent-side sheet symbol this pin lands on.
        position_along_edge: Distance in mm from the sheet symbol's top-left
            corner along the named edge (used for the parent-side sheet pin).
        label_position: Optional absolute position for the sub-sheet
            hierarchical label. When set, overrides the margin-derived X/Y
            from ``position_along_edge`` so labels can align with IC pins.
    """

    net_name: str
    direction: PinDirection
    edge: SheetEdge
    position_along_edge: float
    label_position: Point | None = None

    def __post_init__(self) -> None:
        if not self.net_name:
            raise ValueError("HierarchicalPin.net_name must be non-empty")
        if not isinstance(self.direction, PinDirection):
            raise TypeError(
                "HierarchicalPin.direction must be a PinDirection, got "
                f"{type(self.direction).__name__}"
            )
        if not isinstance(self.edge, SheetEdge):
            raise TypeError(
                "HierarchicalPin.edge must be a SheetEdge, got "
                f"{type(self.edge).__name__}"
            )
        if self.position_along_edge < 0:
            raise ValueError(
                "HierarchicalPin.position_along_edge must be >= 0, got "
                f"{self.position_along_edge}"
            )
