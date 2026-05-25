"""HDMI receiver with TPD12S016."""

from __future__ import annotations

from scripts.carrier.blocks._hdmi_wiring import (
    build_tpd_b_side_hier_pins,
    hdmi_io_to_tpd_inter_wires,
    hdmi_tpd_inter_wires,
)
from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_io_symbol_section,
    merge_hand_sections,
)
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.hdmi_connector import HDMI_A_REFCIRCUIT
from scripts.carrier.refcircuits.tpd12s016 import TPD12S016_RX_REFCIRCUIT


TPD_ANCHOR = Point(127.0, 88.9)
HDMI_ANCHOR = Point(190.5, 88.9)


def build() -> Block:
    som_io, _, io_pin_map = build_io_symbol_section(
        symbol_name="HDMIRX_IO",
        ic_reference="JHDMIRX1",
        io_destinations=("J_HDMIRX",),
        ic_anchor=Point(35.56, 88.9),
    )
    tpd = build_hand_section(
        name="hdmi_rx_tpd",
        title="TPD12S016 RX",
        ref_circuit=TPD12S016_RX_REFCIRCUIT,
        registry_token="hdmi_companion_TPD12S016",
        ic_reference="UTPD2",
        ic_anchor=TPD_ANCHOR,
        io_destinations=(),
        designator_prefix="CR",
        require_all_hier_wired=False,
    )
    hdmi = build_hand_section(
        name="hdmi_rx_conn",
        title="HDMI connector",
        ref_circuit=HDMI_A_REFCIRCUIT,
        registry_token="conn_HDMI_A",
        ic_reference="JHDMI2",
        ic_anchor=HDMI_ANCHOR,
        io_destinations=(),
        designator_prefix="CH",
        require_all_hier_wired=False,
    )
    inter_wires = (
        *hdmi_io_to_tpd_inter_wires(
            io_pin_map=io_pin_map,
            tpd_anchor=TPD_ANCHOR,
            io_destinations=("J_HDMIRX",),
        ),
        *hdmi_tpd_inter_wires(
            tpd_anchor=TPD_ANCHOR,
            hdmi_anchor=HDMI_ANCHOR,
        ),
    )
    merged = merge_hand_sections(
        HandSectionMerge(
            name="hdmi_rx",
            title="HDMI RX (TPD12S016 + HDMI)",
            sections=(som_io, tpd, hdmi),
            inter_wires=inter_wires,
        )
    )
    hierarchical_pins, hier_wires = build_tpd_b_side_hier_pins(
        tpd_anchor=TPD_ANCHOR,
        io_destinations=("J_HDMIRX",),
        paper_width_mm=merged.layout.width_mm,
    )
    return Block(
        name=merged.name,
        title=merged.title,
        layout=merged.layout,
        components=merged.components,
        wires=merged.wires + hier_wires,
        local_labels=merged.local_labels,
        hierarchical_pins=hierarchical_pins,
        symbol_library_paths=merged.symbol_library_paths,
    )
