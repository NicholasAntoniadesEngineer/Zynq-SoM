"""Layout engine: derives placement coordinates from declarative blocks."""

from zynq_eda.core.layout.bbox import (
    BBox,
    BBoxKind,
    placeholder_symbol_bbox,
    symbol_bbox,
    text_bbox,
    wire_bbox,
)
from zynq_eda.core.layout.geometry import (
    PinGeometry,
    SymbolBoundingBox,
    SymbolGeometryCache,
    pin_connection_from_anchor,
)
from zynq_eda.core.layout.occupancy import Occupancy


__all__ = [
    "BBox",
    "BBoxKind",
    "Occupancy",
    "PinGeometry",
    "SymbolBoundingBox",
    "SymbolGeometryCache",
    "pin_connection_from_anchor",
    "placeholder_symbol_bbox",
    "symbol_bbox",
    "text_bbox",
    "wire_bbox",
]
