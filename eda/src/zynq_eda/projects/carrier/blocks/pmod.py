"""Carrier PMOD block: two Digilent-standard 12-pin PMOD connectors.

Each PMOD connector provides 8 GPIO + power (3V3 + GND), per the
Digilent PMOD Interface Specification v1.3.0 (single-ended Type 1A).
The carrier exposes two PMOD slots so users can stack two daughterboards.
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
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
        paper_size="A4",
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
    yield PowerInputNet("+3V3", edge=SheetEdge.LEFT)
    yield GroundNet("GND", edge=SheetEdge.LEFT)
    for slot in range(2):
        for io in range(8):
            yield SignalNet(
                f"PMOD{slot}_IO{io}", "bidirectional", edge=SheetEdge.LEFT,
            )
