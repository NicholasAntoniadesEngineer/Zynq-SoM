"""HDMI TPD12S016 wiring: IO block, EDID, and HDMI connector."""

from __future__ import annotations

import re

from scripts.carrier.blocks._block_common import (
    CARRIER_SYMBOLS,
    load_io_rows,
    pin_direction_for_interface,
)
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._hand_block import add_hier_pin_from_tap
from scripts.carrier.blocks._wiring import route_with_jog
from scripts.carrier.blocks.signal_maps import unique_carrier_signals
from scripts.carrier.model.block import Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from scripts.carrier.model.interface import HierarchicalPin


TPD12_LIB = "carrier:TPD12S016PWR"
HDMI_LIB = "Connector:HDMI_A"
EEPROM_LIB = "Memory_EEPROM:24LC256"

_TPD_TO_HDMI: tuple[tuple[str, str], ...] = (
    ("SDA_A", "SDA"),
    ("SCL_A", "SCL"),
    ("HPD_A", "HPD"),
    ("CEC_A", "CEC"),
    ("D0+", "D0+"),
    ("D0-", "D0-"),
    ("D1+", "D1+"),
    ("D1-", "D1-"),
    ("D2+", "D2+"),
    ("D2-", "D2-"),
    ("CLK+", "CK+"),
    ("CLK-", "CK-"),
)

_TPD_TMDS_PIN_ORDER: tuple[str, ...] = (
    "D0+",
    "D0-",
    "D1+",
    "D1-",
    "D2+",
    "D2-",
    "CLK+",
    "CLK-",
)


def _complete_diff_lanes(carrier_signals: tuple[str, ...]) -> tuple[int, ...]:
    lane_polarities: dict[int, set[str]] = {}
    for carrier_signal in carrier_signals:
        match = re.search(r"IO_L(\d+)_([PN])", carrier_signal)
        if match is None:
            continue
        lane_index = int(match.group(1))
        lane_polarities.setdefault(lane_index, set()).add(match.group(2))
    return tuple(
        sorted(
            lane_index
            for lane_index, polarities in lane_polarities.items()
            if {"P", "N"}.issubset(polarities)
        )
    )


def _lane_carrier_signal(
    carrier_signals: tuple[str, ...],
    lane_index: int,
    polarity: str,
) -> str | None:
    lane_token = f"_L{lane_index}_{polarity}_"
    for carrier_signal in carrier_signals:
        if lane_token in carrier_signal:
            return carrier_signal
    return None


def _tpd_b_pin_by_carrier(
    carrier_signals: tuple[str, ...],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    selected_lanes = _complete_diff_lanes(carrier_signals)[:4]
    tmd_s_pin_index = 0
    for lane_index in selected_lanes:
        for polarity in ("P", "N"):
            carrier_signal = _lane_carrier_signal(carrier_signals, lane_index, polarity)
            if carrier_signal is None:
                continue
            mapping[carrier_signal] = _TPD_TMDS_PIN_ORDER[tmd_s_pin_index]
            tmd_s_pin_index += 1
    return mapping


def build_tpd_b_side_hier_pins(
    *,
    tpd_anchor: Point,
    io_destinations: tuple[str, ...],
    paper_width_mm: float,
    geometry_cache: SymbolGeometryCache | None = None,
) -> tuple[tuple[HierarchicalPin, ...], tuple[Wire, ...]]:
    """Hierarchical pins at TPD12 B-side with visible jogs before sheet edge."""
    if geometry_cache is None:
        geometry_cache = SymbolGeometryCache()
        geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    io_rows = load_io_rows(*io_destinations)
    carrier_signals = unique_carrier_signals(io_rows)
    tpd_pin_by_carrier = _tpd_b_pin_by_carrier(carrier_signals)

    planned: list[tuple[object, Point, float]] = []
    seen_nets: set[str] = set()
    for row in io_rows:
        if row.carrier_signal in seen_nets:
            continue
        tpd_pin_name = tpd_pin_by_carrier.get(row.carrier_signal)
        if tpd_pin_name is None:
            continue
        seen_nets.add(row.carrier_signal)
        tap_point = geometry_cache.absolute_pin_by_name(
            TPD12_LIB,
            tpd_anchor,
            tpd_pin_name,
        )
        label_y = snap_to_grid(tap_point.y + KICAD_GRID_MM)
        planned.append((row, tap_point, label_y))

    planned.sort(key=lambda item: item[2])
    if not planned:
        return (), ()

    min_label_y = min(label_y for *_rest, label_y in planned)
    hierarchical_pins: list[HierarchicalPin] = []
    wires: list[Wire] = []
    for row, tap_point, label_y in planned:
        hier_pin, segment_wires = add_hier_pin_from_tap(
            net_name=row.carrier_signal,
            tap=tap_point,
            direction=pin_direction_for_interface(row.interface),
            paper_width_mm=paper_width_mm,
            label_y=label_y,
            min_label_y=min_label_y,
        )
        hierarchical_pins.append(hier_pin)
        wires.extend(segment_wires)

    return tuple(hierarchical_pins), tuple(wires)


def hdmi_io_to_tpd_inter_wires(
    *,
    io_pin_map: dict[str, Point],
    tpd_anchor: Point,
    io_destinations: tuple[str, ...],
) -> tuple[Wire, ...]:
    """Wire SoM IO symbol TMDS lanes to TPD12 with midpoint jogs."""
    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    carrier_signals = unique_carrier_signals(load_io_rows(*io_destinations))
    tpd_pin_by_carrier = _tpd_b_pin_by_carrier(carrier_signals)

    wires: list[Wire] = []
    for carrier_signal, tpd_pin in tpd_pin_by_carrier.items():
        source_point = io_pin_map.get(carrier_signal)
        if source_point is None:
            continue
        dest_point = geometry_cache.absolute_pin_by_name(
            TPD12_LIB,
            tpd_anchor,
            tpd_pin,
        )
        jog_x = snap_to_grid((source_point.x + dest_point.x) / 2.0)
        wires.extend(route_with_jog(source_point, dest_point, jog_x))
    return tuple(wires)


def edid_to_tpd_i2c_inter_wires(
    *,
    edid_anchor: Point,
    tpd_anchor: Point,
) -> tuple[Wire, ...]:
    """Bridge EDID EEPROM DDC to TPD12 MCU-side I2C."""
    from scripts.carrier.blocks._hand_block import connect

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    wires: list[Wire] = []
    for edid_pin, tpd_pin in (("SDA", "SDA_B"), ("SCL", "SCL_B")):
        wires.extend(
            connect(
                geometry_cache.absolute_pin_by_name(
                    EEPROM_LIB,
                    edid_anchor,
                    edid_pin,
                ),
                geometry_cache.absolute_pin_by_name(
                    TPD12_LIB,
                    tpd_anchor,
                    tpd_pin,
                ),
            )
        )
    return tuple(wires)


def hdmi_tpd_inter_wires(
    *,
    tpd_anchor: Point,
    hdmi_anchor: Point,
) -> tuple[Wire, ...]:
    from scripts.carrier.blocks._hand_block import connect

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    wires: list[Wire] = []
    for tpd_pin, hdmi_pin in _TPD_TO_HDMI:
        wires.extend(
            connect(
                geometry_cache.absolute_pin_by_name(TPD12_LIB, tpd_anchor, tpd_pin),
                geometry_cache.absolute_pin_by_name(HDMI_LIB, hdmi_anchor, hdmi_pin),
            )
        )
    return tuple(wires)
