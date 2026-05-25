"""Dual PMOD expansion headers."""

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
from scripts.carrier.blocks.signal_maps import build_pmod_header_signal_maps
from scripts.carrier.blocks.symbol_registry import lib_id_for_token
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.pmod import PMOD_REFCIRCUIT


JPM1_ANCHOR = Point(127.0, 76.2)
JPM2_ANCHOR = Point(127.0, 127.0)


def build() -> Block:
    io_section, _, io_pin_map = build_io_connector_section(
        symbol_name="PMOD_IO",
        ic_reference="JPMIO1",
        io_destinations=("J_PMOD1", "J_PMOD3", "J_PMOD4", "PMOD_AUX"),
        ic_anchor=Point(35.56, 101.6),
    )
    pmod1 = build_hand_section(
        name="pmod1",
        title="PMOD header 1",
        ref_circuit=PMOD_REFCIRCUIT,
        registry_token="conn_PMOD_2x6_RA",
        ic_reference="JPM1",
        ic_anchor=JPM1_ANCHOR,
        io_destinations=(),
        designator_prefix="CP",
        require_all_hier_wired=False,
    )
    pmod2 = build_hand_section(
        name="pmod2",
        title="PMOD header 2",
        ref_circuit=PMOD_REFCIRCUIT,
        registry_token="conn_PMOD_2x6_RA",
        ic_reference="JPM2",
        ic_anchor=JPM2_ANCHOR,
        io_destinations=(),
        designator_prefix="CP",
        require_all_hier_wired=False,
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))
    pmod_lib_id = lib_id_for_token("conn_PMOD_2x6_RA")
    jpm1_map, jpm2_map = build_pmod_header_signal_maps()
    inter_wires = (
        *inter_wires_from_pin_maps(
            source_pin_map=io_pin_map,
            geometry_cache=geometry_cache,
            dest_lib_id=pmod_lib_id,
            dest_anchor=JPM1_ANCHOR,
            signal_map=jpm1_map,
        ),
        *inter_wires_from_pin_maps(
            source_pin_map=io_pin_map,
            geometry_cache=geometry_cache,
            dest_lib_id=pmod_lib_id,
            dest_anchor=JPM2_ANCHOR,
            signal_map=jpm2_map,
        ),
    )

    return merge_hand_sections(
        HandSectionMerge(
            name="pmod",
            title="PMOD Expansion (x2)",
            sections=(io_section, pmod1, pmod2),
            inter_wires=inter_wires,
        )
    )
