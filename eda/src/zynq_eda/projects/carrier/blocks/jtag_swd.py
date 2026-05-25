"""Carrier debug headers: Zynq PS JTAG (2x7) + STM32 SWD (2x5).

Two debug connectors live on the carrier's edge:

  * **J1 — Zynq PS JTAG (2x7, 2.54 mm).** Standard Xilinx 14-pin JTAG
    header (TCK / TMS / TDI / TDO + 3V3 + GND), per UG470. Routes to
    the SoM J1 mate via ZYNQ_PS_JTAG_* nets. The symbol uses the
    common Xilinx 6-wire pinout (no TRST pin — Zynq PS JTAG does not
    expose TRST on this header).

  * **J2 — STM32 SWD (2x5, 1.27 mm).** ARM Cortex 10-pin SWD debug
    header for the carrier's STM32 co-processor (SWDIO / SWCLK /
    nRESET + VCC + GND). Pull-ups on SWDIO and nRESET come from the
    SWD_HEADER refcircuit.
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


def build_jtag_swd() -> Block:
    """Return the JTAG+SWD debug-header block."""
    return Block(
        name="jtag_swd",
        title="Debug Headers (Zynq PS JTAG 2x7 + STM32 SWD 2x5)",
        paper_size="A4",
        description=(
            "Zynq PS JTAG (2x7 2.54mm, Xilinx UG470 pinout) and STM32 "
            "SWD (2x5 1.27mm ARM Cortex debug). SWD has pull-ups on "
            "SWDIO and nRESET from its refcircuit; JTAG is a direct "
            "passthrough to the SoM's PS JTAG pins."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["ZX-PM2.54-2-7PY"],
                lib_id="zynq_eda:JTAG_2x7",
                edge=SheetEdge.RIGHT,
                # JTAG_2x7 symbol pins (per shared/symbols/zynq_eda.kicad_sym):
                #   1=VCC, 2=TDI, 3=GND, 4=TMS, 6=TCK, 8=TDO
                pin_to_net=(
                    ("1", "+3V3"),
                    ("2", "ZYNQ_PS_JTAG_TDI"),
                    ("3", "GND"),
                    ("4", "ZYNQ_PS_JTAG_TMS"),
                    ("6", "ZYNQ_PS_JTAG_TCK"),
                    ("8", "ZYNQ_PS_JTAG_TDO"),
                ),
            ),
            ConnectorInstance(
                reference="J2",
                refcircuit=REFCIRCUITS["HX-PZ1.27-2x5P-TP"],
                lib_id="zynq_eda:SWD_2x5",
                edge=SheetEdge.RIGHT,
                # SWD_2x5 symbol pins (per shared/symbols/zynq_eda.kicad_sym):
                #   1=VCC, 2=SWDIO, 3=GND, 4=SWCLK, 10=nRESET
                pin_to_net=(
                    ("1", "+3V3"),
                    ("2", "STM32_SWDIO"),
                    ("3", "GND"),
                    ("4", "STM32_SWCLK"),
                    ("10", "STM32_NRST"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_JTAG_TCK", direction="input",  edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_JTAG_TMS", direction="input",  edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_JTAG_TDI", direction="input",  edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_JTAG_TDO", direction="output", edge=SheetEdge.LEFT),
            SignalNet("STM32_SWDIO",      direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("STM32_SWCLK",      direction="input",  edge=SheetEdge.LEFT),
            SignalNet("STM32_NRST",       direction="input",  edge=SheetEdge.LEFT),
        ),
    )
