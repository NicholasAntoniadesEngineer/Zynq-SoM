"""Canonical part registry and BOM/io-assignment writers.

Submodules:

    * ``parts``           – ``BOMPart`` dataclass + allowed-footprint table
    * ``parts_registry``  – the master ``REGISTRY`` (single source of truth
      for every cap/resistor/IC/connector on the carrier)
    * ``bom_io``          – ``emit_io_assignment_csv`` and ``emit_bom_csv``

Re-exports the most-used names so blocks can write::

    from scripts.carrier.registry import REGISTRY, get_part, BOMPart
"""

from scripts.carrier.registry.parts import (
    ALLOWED_FOOTPRINT_PREFIXES,
    BOMPart,
    PartInstance,
)
from scripts.carrier.registry.parts_registry import (
    REGISTRY,
    REGISTRY_LIST,
    all_parts,
    get_part,
)


__all__ = [
    "ALLOWED_FOOTPRINT_PREFIXES",
    "BOMPart",
    "PartInstance",
    "REGISTRY",
    "REGISTRY_LIST",
    "all_parts",
    "get_part",
]
