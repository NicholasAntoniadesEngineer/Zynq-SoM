"""SoM connector blocks: one sub-sheet per J1 / J2 / J3."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from scripts.carrier.blocks._block_common import (
    INTERIOR_MARGIN_MM,
    PAPER_A2_WIDTH_MM,
    a2_layout,
    hier_channel_x,
    hier_edge_x,
    hier_pin_layout,
    load_io_rows,
    pin_direction_for_interface,
)
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._wiring import route_channel, route_horizontal
from scripts.carrier.model.block import Block, PlacedComponent, Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from scripts.carrier.model.interface import HierarchicalPin, SheetEdge


SCRIPTS_DIR = Path(__file__).resolve().parents[2]
CARRIER_TEMPLATE_DIR = SCRIPTS_DIR / "carrier_template"
SOM_SYMBOL_LIBRARY = CARRIER_TEMPLATE_DIR / "symbol_Zynq_SoM.kicad_sym"

CONNECTOR_LIB_IDS: dict[str, str] = {
    "J1": "symbol_Zynq_SoM:Zynq_SoM_J1",
    "J2": "symbol_Zynq_SoM:Zynq_SoM_J2",
    "J3": "symbol_Zynq_SoM:Zynq_SoM_J3",
}

CONNECTOR_X_MM = snap_to_grid(INTERIOR_MARGIN_MM + 15.24)


def _rows_for_connector(connector_name: str) -> tuple[object, ...]:
    all_rows = load_io_rows(
        "power_input",
        "carrier_LDO",
        "power_rail",
        "ground",
        "I2C_BUS_PS",
        "J_FMC.CLK0",
        "J_FMC.LA00-LA11",
        "J_FMC.LA12-LA23",
        "J_CAM",
        "J_JTAG",
        "J_LCD",
        "J_HDMIRX",
        "J_MRCC_SMA",
        "J_PMOD1",
        "J_PMOD3",
        "J_PMOD4",
        "J_RJ45",
        "J_SD",
        "J_USBC1",
        "J_USBC2_OTG",
        "J_XADC_SMA",
        "PMOD_AUX",
        "STM32_breakout",
        "SW_BOOT",
        "SW_RST_STM32",
        "T_ETH",
        "USR_GPIO_PS",
        "U_HDMITX",
        "U_LS1",
        "U_USBUART",
    )
    return tuple(row for row in all_rows if row.som_connector == connector_name)


def _assign_label_y_for_nets(
    net_pin_points: dict[str, list[Point]],
    net_min_pin: dict[str, int],
) -> dict[str, float]:
    """Assign hier label Y per net; stagger nets that share connector row Y."""
    nets_by_row_y: dict[float, list[str]] = defaultdict(list)
    for carrier_signal, pin_points in net_pin_points.items():
        row_y = snap_to_grid(
            pin_points[0].y
            if len(pin_points) == 1
            else sum(point.y for point in pin_points) / len(pin_points)
        )
        nets_by_row_y[row_y].append(carrier_signal)

    label_y_by_net: dict[str, float] = {}
    occupied_y: set[float] = set()
    for row_y in sorted(nets_by_row_y.keys()):
        row_nets = sorted(
            nets_by_row_y[row_y],
            key=lambda carrier_signal: net_min_pin[carrier_signal],
        )
        cursor_y = row_y
        for carrier_signal in row_nets:
            label_y = snap_to_grid(cursor_y)
            while label_y in occupied_y:
                label_y = snap_to_grid(label_y + KICAD_GRID_MM)
            occupied_y.add(label_y)
            label_y_by_net[carrier_signal] = label_y
            cursor_y = label_y + KICAD_GRID_MM

    return label_y_by_net


def build_for_connector(connector_name: str) -> Block:
    io_rows = _rows_for_connector(connector_name)
    if not io_rows:
        raise ValueError(f"No io_assignment rows for SoM connector {connector_name}")

    geometry_cache = SymbolGeometryCache()
    som_library_path = SOM_SYMBOL_LIBRARY.resolve()
    geometry_cache.register_libraries((som_library_path,))

    connector_anchor = Point(CONNECTOR_X_MM, snap_to_grid(INTERIOR_MARGIN_MM + 50.8))
    lib_id = CONNECTOR_LIB_IDS[connector_name]
    pin_positions = geometry_cache.absolute_pin_positions(lib_id, connector_anchor)

    min_pin_y = min(pin_point.y for pin_point in pin_positions.values())
    required_min_y = snap_to_grid(INTERIOR_MARGIN_MM + 12.7)
    if min_pin_y < required_min_y:
        connector_anchor = Point(
            connector_anchor.x,
            snap_to_grid(connector_anchor.y + (required_min_y - min_pin_y)),
        )
        pin_positions = geometry_cache.absolute_pin_positions(lib_id, connector_anchor)

    components: list[PlacedComponent] = [
        PlacedComponent(
            lib_id=lib_id,
            reference=connector_name,
            value=f"Zynq_SoM_{connector_name}",
            position=connector_anchor,
            footprint="",
        )
    ]
    wires: list[Wire] = []
    hierarchical_pins: list[HierarchicalPin] = []

    net_pin_points: dict[str, list[Point]] = defaultdict(list)
    net_interface: dict[str, str] = {}
    net_min_pin: dict[str, int] = {}

    for io_row in io_rows:
        pin_position = pin_positions.get(io_row.som_pin)
        if pin_position is None:
            raise KeyError(
                f"{connector_name} missing pin {io_row.som_pin!r} in symbol library"
            )
        snapped_pin = Point(
            snap_to_grid(pin_position.x),
            snap_to_grid(pin_position.y),
        )
        net_pin_points[io_row.carrier_signal].append(snapped_pin)
        net_interface[io_row.carrier_signal] = io_row.interface
        pin_number = int(io_row.som_pin)
        net_min_pin.setdefault(io_row.carrier_signal, pin_number)
        net_min_pin[io_row.carrier_signal] = min(
            net_min_pin[io_row.carrier_signal],
            pin_number,
        )

    hier_x = hier_edge_x(PAPER_A2_WIDTH_MM)
    route_bus_x = hier_channel_x(PAPER_A2_WIDTH_MM)
    label_y_by_net = _assign_label_y_for_nets(net_pin_points, net_min_pin)

    sorted_nets = sorted(
        net_pin_points.keys(),
        key=lambda carrier_signal: label_y_by_net[carrier_signal],
    )
    min_label_y = min(label_y_by_net.values())

    for carrier_signal in sorted_nets:
        label_y = label_y_by_net[carrier_signal]
        pin_points = net_pin_points[carrier_signal]
        hierarchical_pin, tap_point, hier_point = hier_pin_layout(
            net_name=carrier_signal,
            direction=pin_direction_for_interface(net_interface[carrier_signal]),
            label_y=label_y,
            min_label_y=min_label_y,
            paper_width_mm=PAPER_A2_WIDTH_MM,
            edge=SheetEdge.RIGHT,
        )
        hierarchical_pins.append(hierarchical_pin)

        if len(pin_points) == 1:
            pin = pin_points[0]
            if abs(pin.y - label_y) < 0.01:
                wires.extend(route_horizontal(pin, hier_x))
            else:
                wires.extend(route_channel(pin, route_bus_x, tap_point))
                wires.extend(route_horizontal(tap_point, hier_x))
        else:
            for pin_position in pin_points:
                if abs(pin_position.y - label_y) < 0.01:
                    wires.extend(route_horizontal(pin_position, route_bus_x))
                else:
                    wires.extend(
                        route_channel(
                            pin_position,
                            route_bus_x,
                            Point(route_bus_x, label_y),
                        )
                    )
            wires.extend(route_horizontal(tap_point, hier_x))

    return Block(
        name=f"som_{connector_name.lower()}",
        title=f"Zynq SoM Connector {connector_name}",
        layout=a2_layout(),
        components=tuple(components),
        wires=tuple(wires),
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=(str(som_library_path),),
    )


def build_j1() -> Block:
    return build_for_connector("J1")


def build_j2() -> Block:
    return build_for_connector("J2")


def build_j3() -> Block:
    return build_for_connector("J3")
