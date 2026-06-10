"""Sheet-to-parent connectivity contract.

Every ``Block`` exposes a tuple of :class:`HierarchicalPin` instances that
defines its wiring contract with the root sheet. The root builder uses these
pins to size sheet symbols, route inter-block nets, and validate pin-name
uniqueness.

The ``shape``/``pin_type`` taxonomy follows KiCad's exact set of allowed
values for hierarchical labels and sheet pins.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from zynq_eda.core.model.grid import Point


class PinDirection(str, Enum):
    """Allowed hierarchical-pin shapes (matches KiCad 9 ``pin`` ``shape`` set)."""

    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"


class SheetEdge(str, Enum):
    """Which edge of a sheet symbol a hierarchical pin lives on."""

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True)
class HierarchicalPin:
    """One entry in a block's externally visible wiring contract."""

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
