"""Carrier FMC LPC expansion block: VITA 57.1 LPC connector breakout.

The carrier exposes a single VITA-57.1 LPC connector (HPC's lite variant)
so the user can plug in standard FMC daughtercards (ADC, DAC, FMC-Eth,
etc.). The connector wires:

  * 34 LA pairs (LA00..LA33) — single-ended or differential GPIO from
    Zynq PL bank 13. Routed to the SoM's J2 bank.
  * 4 differential clocks (CLK0_M2C, CLK1_M2C, CLK_BIDIR0/1) — clock-
    capable PL pins.
  * Power: +12V (from carrier +VIN), +3V3, +VADJ (carrier-controlled
    bank-voltage rail; ties to +1V8 or +2V5 depending on FMC card).
  * I2C management bus (SCL/SDA), JTAG passthrough, present-detect.

This block emits the connector + its decoupling cluster + the VADJ
selection. The Zynq-side bank routing happens via the SoM J2 sheet.
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


def build_fmc_lpc() -> Block:
    return Block(
        name="fmc_lpc",
        title="FMC LPC Expansion (VITA 57.1 LPC connector)",
        paper_size="A3",
        description=(
            "VITA 57.1 LPC FMC connector breakout. 34 LA pairs + 4 CLK "
            "pairs route to Zynq PL bank 13 via the SoM J2 mate. Power "
            "delivered from the carrier rails (+12V, +3V3, VADJ); VADJ "
            "tracks the bank-voltage choice for the daughtercard."
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                refcircuit=REFCIRCUITS["FX10A-168P-SV(91)"],
                lib_id="zynq_eda:FMC_LPC",
                edge=SheetEdge.RIGHT,
                pin_to_net=_fmc_lpc_pin_to_net(),
            ),
        ),
        external_nets=tuple(_fmc_external_nets()),
    )


def _fmc_external_nets():
    """Carrier-side nets the FMC sheet exposes to the parent."""
    yield PowerInputNet("+12V",  edge=SheetEdge.LEFT)
    yield PowerInputNet("+3V3",  edge=SheetEdge.LEFT)
    yield PowerInputNet("+VADJ", edge=SheetEdge.LEFT)
    yield GroundNet("GND",       edge=SheetEdge.LEFT)
    # 34 LA pairs + 2 clock pairs that reach the parent (CLK0_M2C, CLK1_M2C).
    for index in range(34):
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_P", "bidirectional", edge=SheetEdge.LEFT)
        yield SignalNet(f"ZYNQ_FMC_LA{index:02d}_N", "bidirectional", edge=SheetEdge.LEFT)
    for label in ("CLK0_M2C_P", "CLK0_M2C_N", "CLK1_M2C_P", "CLK1_M2C_N"):
        yield SignalNet(f"ZYNQ_FMC_{label}", "input", edge=SheetEdge.LEFT)
    # Management: I2C + JTAG passthrough + present-detect.
    yield SignalNet("ZYNQ_FMC_SCL",  "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_SDA",  "bidirectional", edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TCK",  "input",         edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TDI",  "input",         edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TDO",  "output",        edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TMS",  "input",         edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_TRST_N", "input",       edge=SheetEdge.LEFT)
    yield SignalNet("ZYNQ_FMC_PRSNT_N", "input",      edge=SheetEdge.LEFT)


def _fmc_lpc_pin_to_net():
    """VITA 57.1 LPC pin assignments (subset — full map is per-pair).

    Only the externally-visible pins matter for our block contract; the
    decoupling-side power and GND pins live inside the connector's
    refcircuit external_parts (FMC_LPC_REFCIRCUIT handles them).
    """
    pairs: list[tuple[str, str]] = []
    # 34 LA pairs follow the standard FMC LPC schedule. Pin numbers below
    # match the VITA 57.1 LPC table for J1.
    for index, (p_pin, n_pin) in enumerate(_LA_PAIR_PIN_NUMBERS):
        pairs.append((p_pin, f"ZYNQ_FMC_LA{index:02d}_P"))
        pairs.append((n_pin, f"ZYNQ_FMC_LA{index:02d}_N"))
    # Clock pairs
    pairs.extend((
        ("H4", "ZYNQ_FMC_CLK0_M2C_P"),
        ("H5", "ZYNQ_FMC_CLK0_M2C_N"),
        ("G2", "ZYNQ_FMC_CLK1_M2C_P"),
        ("G3", "ZYNQ_FMC_CLK1_M2C_N"),
    ))
    # Management
    pairs.extend((
        ("C30", "ZYNQ_FMC_SCL"),
        ("C31", "ZYNQ_FMC_SDA"),
        ("D29", "ZYNQ_FMC_TCK"),
        ("D30", "ZYNQ_FMC_TDI"),
        ("D31", "ZYNQ_FMC_TDO"),
        ("D32", "ZYNQ_FMC_TMS"),
        ("D33", "ZYNQ_FMC_TRST_N"),
        ("H2", "ZYNQ_FMC_PRSNT_N"),
    ))
    # Power
    pairs.extend((
        ("C35", "+12V"), ("C37", "+12V"),
        ("C39", "+3V3"), ("D36", "+3V3"), ("D38", "+3V3"), ("D40", "+3V3"),
        ("C36", "+VADJ"), ("C38", "+VADJ"), ("C40", "+VADJ"),
        ("D35", "+VADJ"), ("D37", "+VADJ"), ("D39", "+VADJ"),
    ))
    # Grounds — VITA 57.1 mandates every other row is GND on the connector.
    for gnd_pin in (
        "C1", "C2", "C5", "C8", "C11", "C14", "C17", "C20", "C23", "C26", "C29", "C32",
        "D1", "D2", "D5", "D8", "D11", "D14", "D17", "D20", "D23", "D26", "D29",
        # G7 is LA00_N (pair partner of G6); not a GND pin per VITA 57.1.
        "G1", "G4", "G10", "G13", "G16", "G19", "G22", "G25", "G28", "G31", "G34", "G37",
        "H1", "H7", "H10", "H13", "H16", "H19", "H22", "H25", "H28", "H31", "H34", "H37", "H40",
    ):
        pairs.append((gnd_pin, "GND"))
    return tuple(pairs)


_LA_PAIR_PIN_NUMBERS: list[tuple[str, str]] = [
    ("G6",  "G7"),    # LA00
    ("D8",  "D9"),    # LA01
    ("H7",  "H8"),    # LA02
    ("G9",  "G10"),   # LA03
    ("H10", "H11"),   # LA04
    ("D11", "D12"),   # LA05
    ("C10", "C11"),   # LA06
    ("H13", "H14"),   # LA07
    ("G12", "G13"),   # LA08
    ("D14", "D15"),   # LA09
    ("C14", "C15"),   # LA10
    ("H16", "H17"),   # LA11
    ("G15", "G16"),   # LA12
    ("D17", "D18"),   # LA13
    ("C18", "C19"),   # LA14
    ("H19", "H20"),   # LA15
    ("G18", "G19"),   # LA16
    ("D20", "D21"),   # LA17
    ("C22", "C23"),   # LA18
    ("H22", "H23"),   # LA19
    ("G21", "G22"),   # LA20
    ("H25", "H26"),   # LA21
    ("G24", "G25"),   # LA22
    ("D23", "D24"),   # LA23
    ("H28", "H29"),   # LA24
    ("G27", "G28"),   # LA25
    ("D26", "D27"),   # LA26
    ("C26", "C27"),   # LA27
    ("H31", "H32"),   # LA28
    ("G30", "G31"),   # LA29
    ("H34", "H35"),   # LA30
    ("G33", "G34"),   # LA31
    ("H37", "H38"),   # LA32
    ("G36", "G37"),   # LA33
]
