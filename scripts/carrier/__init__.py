"""Hierarchical carrier-board schematic generator.

This package emits a complete, validated KiCad 9.0 hierarchical schematic
for the Zynq SoM carrier evaluation board. The design intent is captured as
Python data (``ReferenceCircuit`` specs derived from each IC's datasheet)
and the schematic is built one functional block per sub-sheet, then stitched
together by ``sheets/root.py``. ``kicad-sch-api`` writes the ``.kicad_sch``
files and ``kicad-skip`` powers the spatial validators.

Entry point:

    python -m scripts.carrier

See ``scripts/carrier/pipeline.py`` for the full orchestration flow.
"""

__version__ = "1.0.0"
