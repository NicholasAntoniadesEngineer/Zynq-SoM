"""Gigabit Ethernet magnetics and RJ45."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    merge_hand_sections,
)
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._block_common import CARRIER_SYMBOLS
from scripts.carrier.blocks.signal_maps import (
    eth_led_to_rj45,
    eth_mag_to_rj45_inter_wires,
    eth_phy_to_magnetics,
    load_signal_map,
)
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.hx5008nlt import HX5008NLT_REFCIRCUIT
from scripts.carrier.refcircuits.rj45 import RJ45_REFCIRCUIT


MAG_ANCHOR = Point(88.9, 101.6)
RJ45_ANCHOR = Point(190.5, 101.6)
MAG_LIB = "carrier:HX5008NLT"
RJ45_LIB = "carrier:RJHSE5380"


def build() -> Block:
    phy_map = load_signal_map("T_ETH", mapper=eth_phy_to_magnetics)
    mag = build_hand_section(
        name="ethernet_mag",
        title="Ethernet magnetics",
        ref_circuit=HX5008NLT_REFCIRCUIT,
        registry_token="magnetics_HX5008NLT",
        ic_reference="TMAG1",
        ic_anchor=MAG_ANCHOR,
        io_destinations=("T_ETH",),
        designator_prefix="CM",
        signal_pin_map=phy_map,
    )
    rj45 = build_hand_section(
        name="ethernet_rj45",
        title="RJ45 LEDs",
        ref_circuit=RJ45_REFCIRCUIT,
        registry_token="conn_RJ45_bare_shielded",
        ic_reference="JRJ451",
        ic_anchor=RJ45_ANCHOR,
        io_destinations=("J_RJ45",),
        designator_prefix="CR",
        signal_pin_map=load_signal_map("J_RJ45", mapper=eth_led_to_rj45),
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))
    inter_wires = eth_mag_to_rj45_inter_wires(
        geometry_cache=geometry_cache,
        mag_lib_id=MAG_LIB,
        mag_anchor=MAG_ANCHOR,
        rj45_lib_id=RJ45_LIB,
        rj45_anchor=RJ45_ANCHOR,
    )

    return merge_hand_sections(
        HandSectionMerge(
            name="ethernet",
            title="Ethernet (HX5008 + RJ45)",
            sections=(mag, rj45),
            inter_wires=inter_wires,
        )
    )
