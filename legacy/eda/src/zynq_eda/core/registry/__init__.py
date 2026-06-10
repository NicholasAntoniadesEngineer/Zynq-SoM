"""Stage 8 output emitters: BOM CSV, IO assignment CSV, reference-circuit doc.

Each emitter is a standalone module with a single public ``emit_*`` function.
They read from in-memory ``Block`` / ``Sheet`` objects produced by the
earlier pipeline stages and write to a stable file path via atomic
tempfile-and-rename.
"""

from zynq_eda.core.registry.bom import emit_bom
from zynq_eda.core.registry.io_assignment import emit_io_assignment
from zynq_eda.core.registry.reference_circuits import emit_reference_circuits_md


__all__ = [
    "emit_bom",
    "emit_io_assignment",
    "emit_reference_circuits_md",
]
