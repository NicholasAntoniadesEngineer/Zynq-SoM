"""USB-PD subsystem: FUSB302 + USBLC6 + USB-C with wired reference circuit."""

from __future__ import annotations

from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._wiring import manhattan_wires
from scripts.carrier.model.block import Block, BlockLayout, LocalLabel, PlacedComponent, Wire
from scripts.carrier.model.grid import KICAD_GRID_MM, Point, snap_to_grid
from scripts.carrier.model.interface import HierarchicalPin, PinDirection, SheetEdge
from scripts.carrier.registry import get_part
from scripts.carrier.refcircuits.fusb302 import FUSB302_REFCIRCUIT
from scripts.carrier.refcircuits.usblc6 import USBLC6_REFCIRCUIT

from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[2]
CARRIER_SYMBOLS = (SCRIPTS_DIR / "carrier" / "symbols" / "carrier.kicad_sym").resolve()

PAPER_A4_WIDTH_MM: float = snap_to_grid(297.0)
PAPER_A4_HEIGHT_MM: float = snap_to_grid(210.0)
INTERIOR_MARGIN_MM: float = snap_to_grid(10.16)
HIER_EDGE_X_MM: float = snap_to_grid(PAPER_A4_WIDTH_MM - INTERIOR_MARGIN_MM)

FUSB302_LIB = "carrier:FUSB302BMPX"
USBLC6_LIB = "carrier:USBLC6-4SC6"
USBC_LIB = "carrier:USBC_16P"

FUSB302_ANCHOR = Point(165.1, 101.6)
USBC_ANCHOR = Point(35.56, 101.6)
USBLC6_ANCHOR = Point(88.9, 38.1)

HIER_INTERFACE_NETS: tuple[tuple[str, PinDirection], ...] = (
    ("STM32_USB_D_P", PinDirection.BIDIRECTIONAL),
    ("STM32_USB_D_N", PinDirection.BIDIRECTIONAL),
    ("STM32_USB_CC1", PinDirection.BIDIRECTIONAL),
    ("STM32_USB_CC2", PinDirection.BIDIRECTIONAL),
    ("STM32_I2C2_SDA", PinDirection.BIDIRECTIONAL),
    ("STM32_I2C2_SCL", PinDirection.BIDIRECTIONAL),
    ("STM32_FUSB302_INT", PinDirection.INPUT),
)


def _part(lib_id: str, reference: str, value: str, position: Point, footprint: str) -> PlacedComponent:
    return PlacedComponent(
        lib_id=lib_id,
        reference=reference,
        value=value,
        position=position,
        footprint=footprint,
        rotation=0.0,
    )


def _cap(reference: str, token: str, position: Point) -> PlacedComponent:
    part = get_part(token)
    return _part("Device:C", reference, part.value, position, part.footprint)


def _resistor(reference: str, token: str, position: Point) -> PlacedComponent:
    part = get_part(token)
    return _part("Device:R", reference, value=part.value, position=position, footprint=part.footprint)


def build() -> Block:
    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    fusb302_part = get_part("usbc_pd_FUSB302BMPX")
    usblc6_part = get_part("esd_USBLC6_4SC6")

    components: list[PlacedComponent] = [
        _part(
            FUSB302_LIB,
            "UPD1",
            fusb302_part.value,
            FUSB302_ANCHOR,
            FUSB302_REFCIRCUIT.footprint,
        ),
        _part(
            USBLC6_LIB,
            "UESD1",
            usblc6_part.value,
            USBLC6_ANCHOR,
            USBLC6_REFCIRCUIT.footprint,
        ),
        _part(
            USBC_LIB,
            "JUSBC1",
            "USBC_16P",
            USBC_ANCHOR,
            "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        ),
        _part("power:GND", "#PWR01", "GND", Point(25.4, 177.8), ""),
        _part("power:GND", "#PWR02", "GND", Point(165.1, 177.8), ""),
        _part("power:+3V3", "#PWR03", "+3V3", Point(215.9, 50.8), ""),
        _cap("CPD1", "1u_0402_X7R", Point(149.86, 76.2)),
        _cap("CPD2", "100n_0402_X7R", Point(149.86, 88.9)),
        _cap("CPD3", "100n_0402_X7R", Point(127.0, 76.2)),
        _cap("CPD4", "200p_0402_C0G", Point(149.86, 114.3)),
        _cap("CPD5", "200p_0402_C0G", Point(149.86, 127.0)),
        _cap("CPD6", "10u_0603_X7R", Point(149.86, 139.7)),
        _cap("CPD7", "10u_0603_X7R", Point(149.86, 152.4)),
        _cap("CPD8", "100n_0402_X7R", Point(76.2, 25.4)),
        _resistor("RPD1", "4k7_0402_1%", Point(203.2, 93.98)),
        _resistor("RPD2", "4k7_0402_1%", Point(203.2, 106.68)),
        _resistor("RPD3", "10k_0402_1%", Point(203.2, 119.38)),
    ]

    fusb_pins = geometry_cache.absolute_pin_positions(FUSB302_LIB, FUSB302_ANCHOR)
    usbc_cc1 = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "CC1")
    usbc_cc2 = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "CC2")
    usbc_vbus = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "VBUS")
    usbc_d_plus = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "D+")
    usbc_d_minus = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "D-")

    esd_io1 = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "I/O1")
    esd_io2 = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "I/O2")
    esd_vbus = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "VBUS")
    esd_gnd = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "GND")

    wires: list[Wire] = []
    local_labels: list[LocalLabel] = []

    def connect(point_a: Point, point_b: Point) -> None:
        wires.extend(manhattan_wires(point_a, point_b))

    ground_rail = Point(25.4, 177.8)
    vdd_rail = Point(215.9, 50.8)
    sc_rail = Point(228.6, 63.5)

    local_labels.append(LocalLabel("+3V3_SC", sc_rail))

    # FUSB302 decoupling
    connect(fusb_pins["3"], vdd_rail)
    connect(fusb_pins["3"], Point(149.86, 76.2))
    connect(Point(149.86, 76.2), Point(149.86, 88.9))
    connect(Point(149.86, 88.9), ground_rail)
    connect(Point(149.86, 76.2), ground_rail)

    # VBUS bypass
    connect(fusb_pins["1"], usbc_vbus)
    connect(fusb_pins["1"], Point(127.0, 76.2))
    connect(Point(127.0, 76.2), ground_rail)

    # CC lines with 200p caps to GND
    connect(fusb_pins["4"], usbc_cc1)
    connect(fusb_pins["4"], Point(149.86, 114.3))
    connect(Point(149.86, 114.3), ground_rail)
    connect(fusb_pins["5"], usbc_cc2)
    connect(fusb_pins["5"], Point(149.86, 127.0))
    connect(Point(149.86, 127.0), ground_rail)

    # VCONN bulk caps
    connect(fusb_pins["6"], Point(149.86, 139.7))
    connect(Point(149.86, 139.7), ground_rail)
    connect(fusb_pins["7"], Point(149.86, 152.4))
    connect(Point(149.86, 152.4), ground_rail)

    # I2C pull-ups to +3V3_SC
    connect(fusb_pins["8"], Point(203.2, 93.98))
    connect(Point(203.2, 93.98), sc_rail)
    connect(fusb_pins["9"], Point(203.2, 106.68))
    connect(Point(203.2, 106.68), sc_rail)
    connect(fusb_pins["10"], Point(203.2, 119.38))
    connect(Point(203.2, 119.38), sc_rail)

    # GND pins
    for gnd_pin in ("2", "11", "12", "13", "14"):
        connect(fusb_pins[gnd_pin], ground_rail)

    # USB ESD: D+ / D- through USBLC6
    connect(usbc_d_plus, esd_io1)
    connect(usbc_d_minus, esd_io2)
    connect(esd_vbus, usbc_vbus)
    connect(esd_gnd, ground_rail)
    connect(Point(76.2, 25.4), esd_vbus)
    connect(Point(76.2, 25.4), ground_rail)

    min_hier_y = INTERIOR_MARGIN_MM + 12.7
    hierarchical_pins: list[HierarchicalPin] = []

    interface_taps: dict[str, Point] = {
        "STM32_USB_CC1": fusb_pins["4"],
        "STM32_USB_CC2": fusb_pins["5"],
        "STM32_I2C2_SDA": fusb_pins["8"],
        "STM32_I2C2_SCL": fusb_pins["9"],
        "STM32_FUSB302_INT": fusb_pins["10"],
        "STM32_USB_D_P": esd_io1,
        "STM32_USB_D_N": esd_io2,
    }

    planned_hier_ys: list[float] = []
    occupied_y: set[float] = set()
    for net_name, direction in HIER_INTERFACE_NETS:
        tap = interface_taps[net_name]
        hier_y = snap_to_grid(max(INTERIOR_MARGIN_MM + 12.7, tap.y))
        while hier_y in occupied_y:
            hier_y = snap_to_grid(hier_y + KICAD_GRID_MM)
        occupied_y.add(hier_y)
        planned_hier_ys.append(hier_y)

    min_label_y = min(planned_hier_ys)

    for index, (net_name, direction) in enumerate(HIER_INTERFACE_NETS):
        tap = interface_taps[net_name]
        hier_y = planned_hier_ys[index]
        hier_point = Point(HIER_EDGE_X_MM, hier_y)
        connect(tap, hier_point)
        hierarchical_pins.append(
            HierarchicalPin(
                net_name=net_name,
                direction=direction,
                edge=SheetEdge.RIGHT,
                position_along_edge=snap_to_grid(hier_y - min_label_y + INTERIOR_MARGIN_MM),
                label_position=hier_point,
            )
        )

    return Block(
        name="usb_pd",
        title="USB-PD (FUSB302 + USBLC6 + USB-C)",
        layout=BlockLayout(
            paper_size="A4",
            width_mm=PAPER_A4_WIDTH_MM,
            height_mm=PAPER_A4_HEIGHT_MM,
            interior_margin_mm=INTERIOR_MARGIN_MM,
        ),
        components=tuple(components),
        wires=tuple(wires),
        local_labels=tuple(local_labels),
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=(str(CARRIER_SYMBOLS),),
    )
