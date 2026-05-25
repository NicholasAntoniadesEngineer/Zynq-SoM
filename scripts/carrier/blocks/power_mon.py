"""INA226 power rail monitoring."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_power_distribution_section,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import i2c_to_ina226, load_signal_map
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.ina226 import INA226_REFCIRCUIT


def build() -> Block:
    monitor = build_hand_section(
        name="power_mon_ic",
        title="INA226",
        ref_circuit=INA226_REFCIRCUIT,
        registry_token="powermon_INA226",
        ic_reference="UIM1",
        ic_anchor=Point(127.0, 101.6),
        io_destinations=("I2C_BUS_PS",),
        designator_prefix="RM",
        signal_pin_map=load_signal_map("I2C_BUS_PS", mapper=i2c_to_ina226),
    )
    rails = build_power_distribution_section(
        name="power_mon_rails",
        title="Monitor supply rails",
        io_destinations=("power_rail", "ground"),
    )
    return merge_hand_sections(
        HandSectionMerge(
            name="power_mon",
            title="Power Monitoring (INA226)",
            sections=(monitor, rails),
        )
    )
