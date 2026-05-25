"""Layout engine: derives placement coordinates from declarative blocks."""

from zynq_eda.core.layout.geometry import (
    PinGeometry,
    SymbolBoundingBox,
    SymbolGeometryCache,
    pin_connection_from_anchor,
)


__all__ = [
    "PinGeometry",
    "SymbolBoundingBox",
    "SymbolGeometryCache",
    "pin_connection_from_anchor",
]
