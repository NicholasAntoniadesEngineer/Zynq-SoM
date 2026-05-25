"""LVDS LCD FFC connector."""

from __future__ import annotations

from scripts.carrier.blocks._block_common import CARRIER_SYMBOLS
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_io_connector_section,
    inter_wires_from_pin_maps,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import build_lvds_ffc_signal_map
from scripts.carrier.blocks.symbol_registry import lib_id_for_token
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.lvds_lcd import LVDS_LCD_REFCIRCUIT


FFC_ANCHOR = Point(127.0, 101.6)


def build() -> Block:
    io_section, _, io_pin_map = build_io_connector_section(
        symbol_name="LVDS_LCD_IO",
        ic_reference="JLCD1",
        io_destinations=("J_LCD",),
        ic_anchor=Point(50.8, 101.6),
    )
    ffc_section = build_hand_section(
        name="lvds_lcd_ffc",
        title="LVDS LCD FFC",
        ref_circuit=LVDS_LCD_REFCIRCUIT,
        registry_token="conn_FFC_40P_0.5mm",
        ic_reference="JFFC1",
        ic_anchor=FFC_ANCHOR,
        io_destinations=(),
        designator_prefix="CL",
        require_all_hier_wired=False,
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))
    inter_wires = inter_wires_from_pin_maps(
        source_pin_map=io_pin_map,
        geometry_cache=geometry_cache,
        dest_lib_id=lib_id_for_token("conn_FFC_40P_0.5mm"),
        dest_anchor=FFC_ANCHOR,
        signal_map=build_lvds_ffc_signal_map(),
    )

    return merge_hand_sections(
        HandSectionMerge(
            name="lvds_lcd",
            title="LVDS LCD FFC",
            sections=(io_section, ffc_section),
            inter_wires=inter_wires,
        )
    )
