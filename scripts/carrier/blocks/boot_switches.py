"""Boot mode DIP switch and reset tact switch."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import (
    boot_mode_to_dip,
    load_signal_map,
    reset_to_switch,
)
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.dip_switch import DIP_SWITCH_REFCIRCUIT
from scripts.carrier.refcircuits.tactile_switch import TACTILE_SWITCH_REFCIRCUIT


def build() -> Block:
    dip = build_hand_section(
        name="boot_dip",
        title="Boot mode DIP",
        ref_circuit=DIP_SWITCH_REFCIRCUIT,
        registry_token="sw_dip_4pos_1.27mm",
        ic_reference="SWBOOT1",
        ic_anchor=Point(101.6, 101.6),
        io_destinations=("SW_BOOT",),
        designator_prefix="CB",
        signal_pin_map=load_signal_map("SW_BOOT", mapper=boot_mode_to_dip),
    )
    reset = build_hand_section(
        name="boot_reset",
        title="STM32 reset",
        ref_circuit=TACTILE_SWITCH_REFCIRCUIT,
        registry_token="sw_tactile_6x6",
        ic_reference="SWRST1",
        ic_anchor=Point(190.5, 101.6),
        io_destinations=("SW_RST_STM32",),
        designator_prefix="CR",
        signal_pin_map=load_signal_map("SW_RST_STM32", mapper=reset_to_switch),
    )
    return merge_hand_sections(
        HandSectionMerge(
            name="boot_switches",
            title="Boot Mode + Reset Switches",
            sections=(dip, reset),
        )
    )
