"""Per-IC layout templates.

Each active IC on the carrier has a hand-designed ``IcBlockTemplate`` that
tells the block factory where to put each *group* of external parts:

    * ``DECOUPLING`` caps go above the VDD pin in a vertical stack.
    * ``PULL_UP`` resistors go to the right of the relevant signal pin.
    * ``PROTECTION`` components (TVS / ESD / Schottky) go between the IC
      and the connector they protect.
    * ``SIGNAL_FILTER`` caps go between the IC pin and ground, just below
      the pin on the schematic.

The template carries OFFSETS only. The block builder is responsible for
turning each ``(IC pin, PinGroup)`` pair into a concrete ``PlacedComponent``
position using the offset from the IC body anchor.

Templates are optional - if a ``ReferenceCircuit`` has no template attached,
the block factory falls back to a built-in default layout that puts every
external part to the right of the IC body in a single column. The default
is good enough for sub-circuits with few externals (USBLC6, simple LDOs);
templates are required for ICs with dense pin maps (FUSB302, INA226).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from scripts.carrier.model.grid import Point, assert_on_grid


class PinGroup(str, Enum):
    """The functional class an ``ExternalPart`` belongs to.

    Block factories assign each ``ExternalPart`` to one of these groups
    using simple net-name and pin-name rules (e.g. ``to_net == "GND"`` and
    ``from_pin`` is a power input means ``DECOUPLING``). Templates then
    look up the placement offset for the group.
    """

    DECOUPLING = "decoupling"
    PULL_UP = "pull_up"
    PULL_DOWN = "pull_down"
    SIGNAL_FILTER = "signal_filter"
    PROTECTION = "protection"
    TERMINATION = "termination"
    BULK = "bulk"
    SERIES = "series"


@dataclass(frozen=True)
class PinGroupOffset:
    """Where parts in a pin group sit relative to the IC pin they attach to.

    Attributes:
        offset: ``(dx, dy)`` from the IC pin to the part's pin-1 anchor.
        stride: Vertical distance between successive parts in the same
            group sharing the same IC pin (used when multiple decoupling
            caps stack above the same VDD pin).
        rotation: Rotation of the part in degrees (0, 90, 180, 270).
    """

    offset: Point
    stride: Point
    rotation: float = 0.0

    def __post_init__(self) -> None:
        assert_on_grid(self.offset)
        assert_on_grid(self.stride)
        if self.rotation not in (0.0, 90.0, 180.0, 270.0):
            raise ValueError(
                "PinGroupOffset.rotation must be 0/90/180/270, got "
                f"{self.rotation}"
            )


@dataclass(frozen=True)
class IcBlockTemplate:
    """Hand-designed placement rules for one IC.

    Attributes:
        ic_anchor_offset: Offset from the sheet's anchor point (block
            builder decides) to the IC body anchor.
        pin_group_offsets: Per-``PinGroup`` placement rule.
    """

    ic_anchor_offset: Point
    pin_group_offsets: dict[PinGroup, PinGroupOffset]

    def offset_for(self, group: PinGroup) -> PinGroupOffset:
        try:
            return self.pin_group_offsets[group]
        except KeyError as missing:
            raise KeyError(
                "IcBlockTemplate has no offset for pin group "
                f"{group.value!r}; declare one in the template before the "
                "block factory tries to place a part in that group."
            ) from missing
