"""MIPI camera FFC connector."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import build_io_connector_section
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point


def build() -> Block:
    section, _, _ = build_io_connector_section(
        symbol_name="MIPI_CAMERA_IO",
        ic_reference="JCAM1",
        io_destinations=("J_CAM",),
        ic_anchor=Point(50.8, 101.6),
    )
    return Block(
        name="mipi_camera",
        title="MIPI Camera FFC",
        layout=section.layout,
        components=section.components,
        wires=section.wires,
        local_labels=section.local_labels,
        hierarchical_pins=section.hierarchical_pins,
        symbol_library_paths=section.symbol_library_paths,
    )
