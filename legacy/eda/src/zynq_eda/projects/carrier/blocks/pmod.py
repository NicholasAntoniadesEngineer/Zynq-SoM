"""Carrier PMOD block: two Digilent-standard 12-pin PMOD connectors.

Each PMOD connector provides 8 GPIO + power (3V3 + GND), per the
Digilent PMOD Interface Specification v1.3.0 (single-ended Type 1A).
The carrier exposes two PMOD slots so users can stack two daughterboards.
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    GroundNet,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_pmod() -> Block:
    return Block(
        name="pmod",
        title="PMOD Headers (2× Digilent 12-pin Type 1A)",
        paper_size="A3",
        description=(
            "Two PMOD headers per Digilent PMOD Interface Spec v1.3.0 "
            "(Type 1A, single-ended GPIO). Each provides 8 GPIO + 3V3 + "
            "GND. Pins route to Zynq PL bank 35 via the SoM J3 mate."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["PM254R-12-08-H85"],
                lib_id="Connector_Generic:Conn_02x06_Odd_Even",
                edge=SheetEdge.RIGHT,
                pin_to_net=_pmod_pin_to_net(slot=0),
            ),
            ConnectorInstance(
                reference="J2",
                refcircuit=REFCIRCUITS["PM254R-12-08-H85"],
                lib_id="Connector_Generic:Conn_02x06_Odd_Even",
                edge=SheetEdge.RIGHT,
                pin_to_net=_pmod_pin_to_net(slot=1),
            ),
        ),
        external_nets=tuple(_pmod_external_nets()),
    )


def _pmod_pin_to_net(*, slot: int) -> tuple[tuple[str, str], ...]:
    """Digilent PMOD Type 1A pinout (per row: 1-6 top, 7-12 bottom).

    Top row: pins 1-4 = data, 5 = GND, 6 = +3V3.
    Bottom row: pins 7-10 = data (extra GPIOs), 11 = GND, 12 = +3V3.
    """
    return (
        ("1",  f"PMOD{slot}_IO0"),
        ("2",  f"PMOD{slot}_IO1"),
        ("3",  f"PMOD{slot}_IO2"),
        ("4",  f"PMOD{slot}_IO3"),
        ("5",  "GND"),
        ("6",  "+3V3"),
        ("7",  f"PMOD{slot}_IO4"),
        ("8",  f"PMOD{slot}_IO5"),
        ("9",  f"PMOD{slot}_IO6"),
        ("10", f"PMOD{slot}_IO7"),
        ("11", "GND"),
        ("12", "+3V3"),
    )


def _pmod_external_nets():
    # The PMOD connector body has pins emerging on BOTH sides. The
    # ``Conn_02x06_Odd_Even`` symbol places ODD pin numbers (1, 3, 5,
    # 7, 9, 11) on the LEFT column (X = pin_tip_left = 334) with
    # local label rotation 180 (text OUT-PAGE LEFT) and EVEN pin
    # numbers (2, 4, 6, 8, 10, 12) on the RIGHT column (X = 346.71)
    # with rotation 0 (text OUT-PAGE RIGHT). Each net's declared
    # ``edge`` MUST match the physical column its pin sits on,
    # otherwise the hier-label has to be routed ACROSS the connector
    # body (LEFT-declared net on a RIGHT-column pin), which is
    # geometrically unrouteable past the body bbox.
    #
    # PMOD Type 1A pin map (per ``_pmod_pin_to_net``):
    #   pin 1=IO0(LEFT), 2=IO1(RIGHT), 3=IO2(LEFT), 4=IO3(RIGHT),
    #   5=GND(LEFT), 6=+3V3(RIGHT),
    #   7=IO4(LEFT), 8=IO5(RIGHT), 9=IO6(LEFT), 10=IO7(RIGHT),
    #   11=GND(LEFT), 12=+3V3(RIGHT)
    yield PowerInputNet("+3V3", edge=SheetEdge.RIGHT)  # pin 6/12 on RIGHT column
    yield GroundNet("GND", edge=SheetEdge.LEFT)         # pin 5/11 on LEFT column
    for slot in range(2):
        for io in range(8):
            # Even IO indices = LEFT column pins, odd IO indices = RIGHT.
            edge = SheetEdge.LEFT if io % 2 == 0 else SheetEdge.RIGHT
            yield SignalNet(
                f"PMOD{slot}_IO{io}", "bidirectional", edge=edge,
            )
