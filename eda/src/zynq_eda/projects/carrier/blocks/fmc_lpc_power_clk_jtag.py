"""Carrier FMC LPC expansion — bank C: power + clock + JTAG + mgmt.

Sister to ``fmc_lpc_la_low`` and ``fmc_lpc_la_high``. This bank carries
the FMC's power rails (+12V, +3V3, VADJ), differential clocks
(CLK0_M2C, CLK1_M2C), management I2C, JTAG passthrough, and present-
detect.

BANK SPLIT MECHANISM
====================
Distinct sub-symbol (``FMC_LPC_PWR_CLK_JTAG``) carved out of the parent
``FMC_LPC`` pin list. See ``som_j1_mio.py`` for the full mechanism
description.
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


def build_fmc_lpc_power_clk_jtag() -> Block:
    return Block(
        name="fmc_lpc_power_clk_jtag",
        title="FMC LPC bank C (power + clock + JTAG + mgmt)",
        paper_size="A3",
        description=(
            "Bank C of the VITA 57.1 LPC FMC connector. Carries the FMC "
            "power rails (+12V, +3V3, +VADJ), differential clocks "
            "(CLK0_M2C, CLK1_M2C), management I2C (SCL/SDA), JTAG "
            "passthrough, and PRSNT_M2C_L (present-detect)."
        ),
        connectors=(
            ConnectorInstance(
                reference="J4C",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="FMC_LPC_PWR_CLK_JTAG:FMC_LPC_PWR_CLK_JTAG",
                edge=SheetEdge.RIGHT,
                pin_to_net=_fmc_lpc_pwr_clk_jtag_pin_to_net(),
                # The FMC power/I2C/PRSNT decoupling lives on this bank's
                # dense adjacent designator pins — draw it as a labelled cap
                # bank in open space rather than clustered on the pins.
                decoupling_array=True,
            ),
        ),
        external_nets=tuple(_fmc_pwr_clk_jtag_external_nets()),
    )


def _fmc_pwr_clk_jtag_external_nets():
    yield PowerInputNet("+12V",  edge=SheetEdge.LEFT)
    yield PowerInputNet("+3V3",  edge=SheetEdge.LEFT)
    yield PowerInputNet("+VADJ", edge=SheetEdge.LEFT)
    yield GroundNet("GND",       edge=SheetEdge.LEFT)
    for label in ("CLK0_M2C_P", "CLK0_M2C_N", "CLK1_M2C_P", "CLK1_M2C_N"):
        yield SignalNet(f"ZYNQ_FMC_{label}", "input", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_SCL",  "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_SDA",  "bidirectional", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TCK",  "input",         edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TDI",  "input",         edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TDO",  "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TMS",  "input",         edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TRST_N", "input",       edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_PRSNT_N", "input",      edge=SheetEdge.LEFT)


def _fmc_lpc_pwr_clk_jtag_pin_to_net() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    # Clocks
    pairs.extend((
        ("H4", "ZYNQ_FMC_CLK0_M2C_P"),
        ("H5", "ZYNQ_FMC_CLK0_M2C_N"),
        ("G2", "ZYNQ_FMC_CLK1_M2C_P"),
        ("G3", "ZYNQ_FMC_CLK1_M2C_N"),
    ))
    # Management I2C
    pairs.extend((
        ("C30", "ZYNQ_FMC_SCL"),
        ("C31", "ZYNQ_FMC_SDA"),
    ))
    # JTAG
    pairs.extend((
        ("D29", "ZYNQ_FMC_TCK"),
        ("D30", "ZYNQ_FMC_TDI"),
        ("D31", "ZYNQ_FMC_TDO"),
        ("D32", "ZYNQ_FMC_TMS"),
        ("D33", "ZYNQ_FMC_TRST_N"),
        ("H2",  "ZYNQ_FMC_PRSNT_N"),
    ))
    # Power
    pairs.extend((
        ("C35", "+12V"), ("C37", "+12V"),
        ("C39", "+3V3"), ("D36", "+3V3"), ("D38", "+3V3"), ("D40", "+3V3"),
        ("C36", "+VADJ"), ("C38", "+VADJ"), ("C40", "+VADJ"),
        ("D35", "+VADJ"), ("D37", "+VADJ"), ("D39", "+VADJ"),
    ))
    # GND (within this bank's pin set, excluding the JTAG/I2C/power pins above).
    claimed: set[str] = {pin for pin, _ in pairs}
    for gnd_candidate in ("H40", "C32"):
        if gnd_candidate not in claimed:
            pairs.append((gnd_candidate, "GND"))
    return tuple(pairs)
