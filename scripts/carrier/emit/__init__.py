"""``kicad-sch-api`` adapter layer.

Single entry-points to translate the in-memory ``Block`` model into a
KiCad 9 ``.kicad_sch`` file, and to emit the root hierarchical sheet that
stitches multiple sub-sheets together. No other module in the package
should depend on ``kicad-sch-api`` directly.
"""

from scripts.carrier.emit.kicad_sch import (
    BlockEmissionStats,
    emit_block,
)
from scripts.carrier.emit.hierarchy import set_hierarchy_context


__all__ = [
    "BlockEmissionStats",
    "emit_block",
    "set_hierarchy_context",
]
