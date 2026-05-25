"""XADC / MRCC SMA clock inputs."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_io_connector_section,
    merge_hand_sections,
)
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.sma_clock import SMA_CLOCK_REFCIRCUIT


def build() -> Block:
    io_section, _, _ = build_io_connector_section(
        symbol_name="XADC_MRCC_IO",
        ic_reference="JSMAIO1",
        io_destinations=("J_XADC_SMA", "J_MRCC_SMA"),
        ic_anchor=Point(35.56, 101.6),
    )
    xadc = build_hand_section(
        name="xadc_sma",
        title="XADC SMA",
        ref_circuit=SMA_CLOCK_REFCIRCUIT,
        registry_token="conn_SMA_RA_TH",
        ic_reference="JSMA1",
        ic_anchor=Point(127.0, 76.2),
        io_destinations=(),
        designator_prefix="CX",
        require_all_hier_wired=False,
    )
    mrcc = build_hand_section(
        name="mrcc_sma",
        title="MRCC SMA",
        ref_circuit=SMA_CLOCK_REFCIRCUIT,
        registry_token="conn_SMA_RA_TH",
        ic_reference="JSMA2",
        ic_anchor=Point(127.0, 127.0),
        io_destinations=(),
        designator_prefix="CX",
        require_all_hier_wired=False,
    )
    return merge_hand_sections(
        HandSectionMerge(
            name="xadc_clk",
            title="XADC / MRCC SMA Clock Inputs",
            sections=(io_section, xadc, mrcc),
        )
    )
