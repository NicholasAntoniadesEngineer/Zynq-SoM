"""Carrier board generator package.

This package generates a complete, validated hierarchical KiCad schematic
for the Zynq SoM carrier evaluation board. The design intent is captured
as Python data (ReferenceCircuit specs from each IC's datasheet) and
emitted as KiCad 9.0 .kicad_sch files with full validation.

Top-level entry point: scripts/create_carrier_template_schematic.py
"""

__version__ = "0.2.0"
