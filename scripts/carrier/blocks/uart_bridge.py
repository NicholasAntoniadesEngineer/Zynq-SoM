"""CP2102N USB-UART bridge with USBLC6 protection."""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    connect,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import load_signal_map, uart_to_cp2102n
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.cp2102n import CP2102N_REFCIRCUIT
from scripts.carrier.refcircuits.usblc6 import USBLC6_REFCIRCUIT


SCRIPTS_DIR = Path(__file__).resolve().parents[2]
CARRIER_SYMBOLS = (SCRIPTS_DIR / "carrier" / "symbols" / "carrier.kicad_sym").resolve()

CP2102N_LIB = "Interface_USB:CP2102N-Axx-xQFN24"
USBLC6_LIB = "carrier:USBLC6-4SC6"
BRIDGE_ANCHOR = Point(165.1, 101.6)
USBLC6_ANCHOR = Point(88.9, 50.8)


def build() -> Block:
    bridge = build_hand_section(
        name="uart_bridge_ic",
        title="CP2102N",
        ref_circuit=CP2102N_REFCIRCUIT,
        registry_token="usbuart_CP2102N",
        ic_reference="UUA1",
        ic_anchor=BRIDGE_ANCHOR,
        io_destinations=("U_USBUART",),
        designator_prefix="CU",
        signal_pin_map=load_signal_map("U_USBUART", mapper=uart_to_cp2102n),
    )
    esd = build_hand_section(
        name="uart_esd",
        title="USBLC6",
        ref_circuit=USBLC6_REFCIRCUIT,
        registry_token="esd_USBLC6_4SC6",
        ic_lib_id=USBLC6_LIB,
        ic_reference="UESD3",
        ic_anchor=USBLC6_ANCHOR,
        io_destinations=(),
        designator_prefix="CE",
        require_all_hier_wired=False,
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    d_plus = geometry_cache.absolute_pin_by_name(
        CP2102N_LIB, BRIDGE_ANCHOR, "D+"
    )
    d_minus = geometry_cache.absolute_pin_by_name(
        CP2102N_LIB, BRIDGE_ANCHOR, "D-"
    )
    esd_io1 = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "I/O1")
    esd_io2 = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "I/O2")

    inter_wires = connect(d_plus, esd_io1) + connect(d_minus, esd_io2)

    return merge_hand_sections(
        HandSectionMerge(
            name="uart_bridge",
            title="USB-UART Bridge (CP2102N + USBLC6)",
            sections=(bridge, esd),
            inter_wires=tuple(inter_wires),
        )
    )
