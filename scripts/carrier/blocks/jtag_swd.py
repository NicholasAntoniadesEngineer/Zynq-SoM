"""JTAG and STM32 breakout debug headers."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_io_connector_section,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import jtag_to_header, load_signal_map
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point, snap_to_grid
from scripts.carrier.refcircuits.jtag_header import JTAG_HEADER_REFCIRCUIT


def build() -> Block:
    jtag = build_hand_section(
        name="jtag",
        title="JTAG",
        ref_circuit=JTAG_HEADER_REFCIRCUIT,
        registry_token="conn_JTAG_2x7_THT",
        ic_reference="JJTAG1",
        ic_anchor=Point(76.2, 76.2),
        io_destinations=("J_JTAG",),
        designator_prefix="RJ",
        signal_pin_map=load_signal_map("J_JTAG", mapper=jtag_to_header),
    )
    stm32_io, _, _ = build_io_connector_section(
        symbol_name="STM32_BREAKOUT_IO",
        ic_reference="JSTM1",
        io_destinations=("STM32_breakout",),
        ic_anchor=Point(152.4, 101.6),
    )
    return merge_hand_sections(
        HandSectionMerge(
            name="jtag_swd",
            title="JTAG + STM32 Breakout",
            sections=(jtag, stm32_io),
        )
    )
