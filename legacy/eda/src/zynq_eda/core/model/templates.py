"""Legacy per-IC placement templates.

Retained for backward compatibility with the 28 ``ReferenceCircuit`` specs
that set a ``layout_template`` field. The new layout engine in
``zynq_eda.core.layout`` ignores templates and derives placement from real
symbol pin geometry; templates are kept here only so the refcircuit data
loads without modification.

The :class:`PinGroup` enum is *not* legacy — it is the canonical taxonomy
the new clusterer uses to classify external parts (decoupling/pull-up/etc.)
when laying out each IC.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from zynq_eda.core.model.grid import Point, assert_on_grid


class PinGroup(str, Enum):
    """The functional class an ``ExternalPart`` belongs to."""

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
    """Legacy placement offset for a pin group (ignored by the new engine)."""

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
    """Legacy hand-designed placement rules for one IC.

    Retained so existing refcircuit specs continue to import cleanly. The
    new layout engine ignores the template and derives placement from real
    symbol pin geometry; this class will be removed once every refcircuit
    drops its ``layout_template`` field.
    """

    ic_anchor_offset: Point
    pin_group_offsets: dict[PinGroup, PinGroupOffset]

    def offset_for(self, group: PinGroup) -> PinGroupOffset:
        try:
            return self.pin_group_offsets[group]
        except KeyError as missing:
            raise KeyError(
                "IcBlockTemplate has no offset for pin group "
                f"{group.value!r}"
            ) from missing
