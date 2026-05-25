"""User GPIO LEDs and tactile switches."""

from __future__ import annotations

from scripts.carrier.blocks._block_common import CARRIER_SYMBOLS, load_io_rows
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    build_io_connector_section,
    connect,
    merge_hand_sections,
)
from scripts.carrier.blocks.signal_maps import unique_carrier_signals
from scripts.carrier.model.block import Block, Wire
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.tactile_switch import TACTILE_SWITCH_REFCIRCUIT
from scripts.carrier.refcircuits.user_led import USER_LED_REFCIRCUIT


LED_ANCHOR = Point(127.0, 76.2)
SWITCH_ANCHOR = Point(127.0, 127.0)
SWITCH_LIB = "carrier:SW_TACT"


def _aux_io_inter_wires(
    *,
    io_pin_map: dict[str, Point],
    led_section: Block,
    switch_section: Block,
    geometry_cache: SymbolGeometryCache,
) -> tuple[Wire, ...]:
    gpio_signals = unique_carrier_signals(load_io_rows("USR_GPIO_PS"))
    wires: list[Wire] = []

    if gpio_signals:
        gpio_label = next(
            (label for label in led_section.local_labels if label.net_name == "GPIO"),
            None,
        )
        if gpio_label is not None:
            source_point = io_pin_map.get(gpio_signals[0])
            if source_point is not None:
                wires.extend(connect(source_point, gpio_label.position))

    if len(gpio_signals) >= 2:
        switch_point = geometry_cache.absolute_pin_by_name(
            SWITCH_LIB,
            SWITCH_ANCHOR,
            "SW",
        )
        source_point = io_pin_map.get(gpio_signals[1])
        if source_point is not None:
            wires.extend(connect(source_point, switch_point))

    if len(gpio_signals) >= 3:
        switch_point = geometry_cache.absolute_pin_by_name(
            SWITCH_LIB,
            SWITCH_ANCHOR,
            "SW",
        )
        source_point = io_pin_map.get(gpio_signals[2])
        if source_point is not None:
            wires.extend(connect(source_point, switch_point))

    return tuple(wires)


def build() -> Block:
    gpio_io, _, io_pin_map = build_io_connector_section(
        symbol_name="AUX_GPIO_IO",
        ic_reference="JAUX1",
        io_destinations=("USR_GPIO_PS", "PMOD_AUX"),
        ic_anchor=Point(35.56, 101.6),
    )
    led = build_hand_section(
        name="aux_io_led",
        title="User LED",
        ref_circuit=USER_LED_REFCIRCUIT,
        registry_token="LED_green_0603",
        ic_reference="DLED1",
        ic_anchor=LED_ANCHOR,
        io_destinations=(),
        designator_prefix="RL",
        require_all_hier_wired=False,
    )
    switch = build_hand_section(
        name="aux_io_sw",
        title="User switch",
        ref_circuit=TACTILE_SWITCH_REFCIRCUIT,
        registry_token="sw_tactile_6x6",
        ic_reference="SW1",
        ic_anchor=SWITCH_ANCHOR,
        io_destinations=(),
        designator_prefix="CS",
        require_all_hier_wired=False,
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))
    inter_wires = _aux_io_inter_wires(
        io_pin_map=io_pin_map,
        led_section=led,
        switch_section=switch,
        geometry_cache=geometry_cache,
    )

    return merge_hand_sections(
        HandSectionMerge(
            name="aux_io",
            title="User GPIO (LEDs + Switches)",
            sections=(gpio_io, led, switch),
            inter_wires=inter_wires,
        )
    )
