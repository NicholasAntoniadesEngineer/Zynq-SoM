"""FMC LPC mezzanine connector."""

from __future__ import annotations

from scripts.carrier.blocks._block_common import CARRIER_SYMBOLS, load_io_rows
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_io_connector_section,
    connect,
    inter_wires_from_pin_maps,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import identity_signal_map
from scripts.carrier.blocks.symbol_registry import lib_id_for_token
from scripts.carrier.model.block import Block, Wire
from scripts.carrier.model.grid import Point, snap_to_grid
from scripts.carrier.refcircuits.fmc_lpc import FMC_LPC_REFCIRCUIT


FMC_ANCHOR = Point(101.6, 40.64)


def _fmc_io_to_connector_inter_wires(
    *,
    io_pin_map: dict[str, Point],
    geometry_cache: SymbolGeometryCache,
    fmc_anchor: Point,
) -> tuple[Wire, ...]:
    """Wire IO symbol pins to FMC connector symbol pins where names align."""
    io_rows = load_io_rows(
        "J_FMC.CLK0",
        "J_FMC.LA00-LA11",
        "J_FMC.LA12-LA23",
    )
    signal_map = identity_signal_map(io_rows)
    fmc_lib_id = lib_id_for_token("conn_FMC_FX10A_168P")
    wired = inter_wires_from_pin_maps(
        source_pin_map=io_pin_map,
        geometry_cache=geometry_cache,
        dest_lib_id=fmc_lib_id,
        dest_anchor=fmc_anchor,
        signal_map=signal_map,
    )
    if wired:
        return wired

    connector_x = snap_to_grid(fmc_anchor.x - 12.7)
    fallback_wires: list[Wire] = []
    for source_point in io_pin_map.values():
        fallback_wires.extend(
            connect(
                source_point,
                Point(connector_x, source_point.y),
            )
        )
    return tuple(fallback_wires)


def build() -> Block:
    decoupling = build_hand_section(
        name="fmc_lpc_dec",
        title="FMC decoupling",
        ref_circuit=FMC_LPC_REFCIRCUIT,
        registry_token="conn_FMC_FX10A_168P",
        ic_reference="JFMC0",
        ic_anchor=FMC_ANCHOR,
        io_destinations=(),
        designator_prefix="CF",
        require_all_hier_wired=False,
    )
    io_section, _, io_pin_map = build_io_connector_section(
        symbol_name="FMC_LPC_IO",
        ic_reference="JFMC1",
        io_destinations=(
            "J_FMC.CLK0",
            "J_FMC.LA00-LA11",
            "J_FMC.LA12-LA23",
        ),
        ic_anchor=Point(50.8, 101.6),
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))
    inter_wires = _fmc_io_to_connector_inter_wires(
        io_pin_map=io_pin_map,
        geometry_cache=geometry_cache,
        fmc_anchor=FMC_ANCHOR,
    )

    return merge_hand_sections(
        HandSectionMerge(
            name="fmc_lpc",
            title="FMC LPC Connector",
            sections=(decoupling, io_section),
            inter_wires=inter_wires,
        )
    )
