"""Power input protection and VCCO LDO regulators."""

from __future__ import annotations

from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_power_distribution_section,
    merge_hand_sections,
)
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.power_input import POWER_INPUT_REFCIRCUIT
from scripts.carrier.refcircuits.tlv757 import TLV75733_REFCIRCUIT


_VCCO_BANKS: tuple[tuple[str, str, Point], ...] = (
    ("+VCCO_13", "ULDO13", Point(127.0, 50.8)),
    ("+VCCO_33", "ULDO33", Point(127.0, 88.9)),
    ("+VCCO_34", "ULDO34", Point(127.0, 127.0)),
    ("+VCCO_35", "ULDO35", Point(127.0, 165.1)),
)


def build() -> Block:
    input_section = build_hand_section(
        name="power_input",
        title="Input protection",
        ref_circuit=POWER_INPUT_REFCIRCUIT,
        registry_token="schottky_SS14",
        ic_reference="DPWR1",
        ic_anchor=Point(50.8, 101.6),
        io_destinations=("power_input",),
        designator_prefix="CP",
        signal_pin_map={"+VIN": "CATHODE"},
    )
    rails_section = build_power_distribution_section(
        name="power_rails",
        title="SoM power rails",
        io_destinations=("power_rail", "ground"),
    )
    ldo_sections = [
        build_hand_section(
            name=f"power_ldo_{vcco_signal.strip('+')}",
            title=f"LDO {vcco_signal}",
            ref_circuit=TLV75733_REFCIRCUIT,
            registry_token="LDO_TLV75733_3V3",
            ic_reference=ldo_reference,
            ic_anchor=anchor,
            io_destinations=("carrier_LDO",),
            designator_prefix="CL",
            carrier_signals_filter=frozenset({vcco_signal}),
            signal_pin_map={vcco_signal: "OUT"},
        )
        for vcco_signal, ldo_reference, anchor in _VCCO_BANKS
    ]
    return merge_hand_sections(
        HandSectionMerge(
            name="power",
            title="Power Input + VCCO LDOs",
            sections=(input_section, rails_section, *ldo_sections),
        )
    )
