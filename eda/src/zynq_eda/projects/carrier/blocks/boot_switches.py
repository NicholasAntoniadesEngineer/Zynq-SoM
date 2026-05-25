"""Carrier boot-mode straps + PS reset button.

Two user-facing inputs on the carrier:

  * **SW1 — 4-position DIP boot strap.** Drives the Zynq PS BOOT_MODE[3:0]
    strap pins. Each switch has a 10 k pull-up to +3V3 (from the refcircuit);
    flipping the switch ON pulls the corresponding bit to GND. The four
    bits select the boot source (QSPI / NAND / SD / JTAG) per Zynq-7000
    TRM Sec 6.3.6 "Boot Mode Pins".

  * **SW2 — Tactile reset button.** Drives the active-low PS_SRST_N reset
    line. The refcircuit supplies the 10 k pull-up to +3V3 and a 100 nF
    debounce/ESD cap to GND. Pressing the button asserts PS_SRST_N low.
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    GroundNet,
    IcInstance,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_boot_switches() -> Block:
    """Return the boot-mode DIP + PS reset tactile-switch block."""
    return Block(
        name="boot_switches",
        title="Boot Mode Straps + PS Reset (DIP-4 + Tactile)",
        paper_size="A4",
        description=(
            "User boot-mode selection (SW1: 4-position DIP into Zynq "
            "BOOT_MODE[3:0]) and active-low PS reset push-button (SW2 → "
            "ZYNQ_PS_SRST_N). Both switches sit between their host net "
            "and GND; refcircuit pull-ups bias the host net high until "
            "the switch is closed."
        ),
        ics=(
            # 4-position DIP — boot strap selector
            IcInstance(
                reference="SW1",
                refcircuit=REFCIRCUITS["DS-04P"],
                lib_id="zynq_eda:SW_DIP_4",
                power_input_net="+3V3",
                # Rename each DIP pin to the boot-mode strap net it drives.
                # SW_DIP_4 pin names per shared/symbols/zynq_eda.kicad_sym:
                #   1=SW1, 2=SW2, 3=SW3, 4=SW4
                net_overrides=(
                    ("SW1", "ZYNQ_BOOT_MODE_0"),
                    ("SW2", "ZYNQ_BOOT_MODE_1"),
                    ("SW3", "ZYNQ_BOOT_MODE_2"),
                    ("SW4", "ZYNQ_BOOT_MODE_3"),
                ),
            ),
            # Tactile push-button — PS active-low reset
            IcInstance(
                reference="SW2",
                refcircuit=REFCIRCUITS["TS-1002S-06026C"],
                lib_id="zynq_eda:SW_TACT",
                power_input_net="+3V3",
                # SW_TACT has two pins both named "SW"; the refcircuit treats
                # them as one node. Map that node to the active-low PS reset.
                net_overrides=(
                    ("SW", "ZYNQ_PS_SRST_N"),
                ),
            ),
        ),
        external_nets=(
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_BOOT_MODE_0", direction="output", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_BOOT_MODE_1", direction="output", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_BOOT_MODE_2", direction="output", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_BOOT_MODE_3", direction="output", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_SRST_N",   direction="output", edge=SheetEdge.LEFT),
        ),
    )
