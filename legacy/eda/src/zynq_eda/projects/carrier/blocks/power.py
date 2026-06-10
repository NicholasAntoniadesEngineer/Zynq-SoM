"""Carrier Power block: USB-C +5V → 3.3 / 2.5 / 1.8 V LDO rails.

This is the carrier's main power-conversion section:

    +VIN (5V from USB-C)
        ├─→ TLV75733PDBV → +3V3   (3.3V @ 1A, main carrier rail)
        ├─→ TLV75725PDBV → +2V5   (2.5V @ 1A, for SSTL/DCI references)
        └─→ TLV75718PDBV → +1V8   (1.8V @ 1A, for FPGA banks needing 1.8V)

Each LDO is wired per the TI TLV757P datasheet "Typical Application"
(Sec 8.2.2, Fig 18):

    1 µF X7R 0402  on IN  → GND   (input cap, place close to pin 1)
    1 µF X7R 0402  on OUT → GND   (output cap, ESR-stable)
    100 nF X7R 0402 on OUT → GND  (HF bypass for transient response)
    100 kΩ 1% 0402 on EN  → IN    (always-on pull-up; replace with GPIO
                                    when sequenced)
    10 nF X7R 0402 on NR/SS → GND (optional noise-reduction / soft-start)

The block exposes hierarchical labels on its edges so the parent sheet
can wire +VIN in and route the regulated rails out to the rest of the
carrier (FPGA banks, peripherals, indicator LEDs).
"""

from __future__ import annotations

from zynq_eda.catalog.components import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    GroundNet,
    IcInstance,
    PowerInputNet,
    PowerOutputNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_power() -> Block:
    """Return the carrier Power block (3 LDOs)."""
    return Block(
        name="power",
        title="Power Architecture (USB-C +5V → +3V3 / +2V5 / +1V8)",
        paper_size="A3",
        description=(
            "Three TLV757P-family LDOs convert +VIN (5V from USB-C) into the "
            "three regulated rails the carrier needs: +3V3 (main), +2V5 "
            "(SSTL refs), +1V8 (FPGA 1.8V banks). Each LDO carries its full "
            "TI datasheet 'Typical Application' decoupling (1µF in, 1µF + "
            "100nF out, 100k EN pull-up, 10nF NR/SS) per Fig 18, p.18."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["TLV75733PDBVR"],
                lib_id="Regulator_Linear:TLV75733PDBV",
                power_input_net="+VIN",
                power_output_net="+3V3",
                # EN always-on pull-up targets the LDO INPUT rail; the
                # generic refcircuit names it "IN", remapped per-instance.
                external_part_net_remap=(("IN", "+VIN"),),
            ),
            IcInstance(
                reference="U2",
                refcircuit=REFCIRCUITS["TLV75725PDBVR"],
                lib_id="Regulator_Linear:TLV75725PDBV",
                power_input_net="+VIN",
                power_output_net="+2V5",
                external_part_net_remap=(("IN", "+VIN"),),
            ),
            IcInstance(
                reference="U3",
                refcircuit=REFCIRCUITS["TLV75718PDBVR"],
                lib_id="Regulator_Linear:TLV75718PDBV",
                power_input_net="+VIN",
                power_output_net="+1V8",
                external_part_net_remap=(("IN", "+VIN"),),
            ),
        ),
        external_nets=(
            PowerInputNet("+VIN", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            PowerOutputNet("+3V3", edge=SheetEdge.RIGHT),
            PowerOutputNet("+2V5", edge=SheetEdge.RIGHT),
            PowerOutputNet("+1V8", edge=SheetEdge.RIGHT),
        ),
    )
