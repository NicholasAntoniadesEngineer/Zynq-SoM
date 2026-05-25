"""microSD socket."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import build_hand_section
from scripts.carrier.blocks.signal_maps import load_signal_map, sdio_to_socket
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.microsd import MICROSD_DM3AT_REFCIRCUIT


def build() -> Block:
    return build_hand_section(
        name="microsd",
        title="microSD (DM3AT)",
        ref_circuit=MICROSD_DM3AT_REFCIRCUIT,
        registry_token="conn_microSD_DM3AT",
        ic_reference="JSD1",
        ic_anchor=Point(88.9, 101.6),
        io_destinations=("J_SD",),
        designator_prefix="CS",
        signal_pin_map=load_signal_map("J_SD", mapper=sdio_to_socket),
    )
