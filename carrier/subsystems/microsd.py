"""microsd — carrier ADAPTER for the reusable TXS02612 microSD-slot subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/microsd/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT same net names the hand-written sheet used, so the
emitted carrier/schematic/microsd.kicad_sch + its golden render are unchanged.

CARRIER CONTEXT: the SoM's SDIO_* nets run straight to the Zynq at 1.8 V and
standard SD cards initialize at 3.3 V, so a TXS02612 sits between them — port A
= 1.8 V SoM side (the contract SDIO_* nets, typed sd_bus 1.8 V), port B0 =
3.3 V card side to the TF-01A push-push slot, port B1 unused. SEL strapped low
selects B0. The card side is fixed at the bring-up-gated +3V3_SD rail (SY6280
cell 5 on the bringup sheet) — DEFAULT/HIGH-SPEED SD only, no UHS-I S18 switch
(SD-1). Card-line anti-float pulls are 100k (SD-2).

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_HOST -> +1V8       TXS02612 VCCA host-side reference: the SoM SDIO_*
                          domain runs at 1.8 V, so the A-side reference is the
                          carrier +1V8 rail.
  +VDD_CARD -> +3V3_SD    TXS02612 VCCB(0/1) card-side rail = the bring-up-gated
                          +3V3_SD module rail (SY6280 cell 5, bringup sheet — a
                          POWER net with its own symbol, like +5V_USB). Feeds
                          slot VDD + both VCCB + every card pull + bulk + the
                          TPD6E001 ESD-array VCC (SD-1).
  GND       -> GND        (identity).

  SD_CLK/CMD/D0..D3 -> SDIO_CLK/CMD/D0..D3   the SoM SDIO contract nets (port A,
                          1.8 V), verbatim. The card-side twins stay library-
                          private internal SIGNAL nets (SD_CARD_*).
  CD_N      -> SD_CARD_DETECT   card-detect reported to the SoM. Binds on the
                          generated J1 sheet (som_conn_gen FUNCTION_MAP), so the
                          adapter declares that linker deferral via ``expects``.

These notes reproduce the carrier's house-style power-tree draw prose so the
derived power_tree.txt stays byte-identical to the hand-written sheet.
"""

from __future__ import annotations

from subsystems.microsd import microsd as _lib
from schgen.core.model import Circuit

# The generated J1 sheet (som_conn_gen FUNCTION_MAP) carries the card-detect
# GPIO, so CD_N binds there by name. EXPLICIT linker deferral so a standalone
# link reports it as awaiting-J1, never a silent open.
_J1_MAP = "som_j1_connector (STM32 GPIO function map)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects card-detect binds on the generated J1 sheet -> explicit linker deferral
#   notes   power-tree draw notes cite the carrier's house-style wording
# (notes keep the carrier's derived artifact — power_tree.txt — byte-identical to
#  the hand-written sheet.)
META = {
    "bind": {
        "+VDD_HOST": "+1V8",
        "+VDD_CARD": "+3V3_SD",
        "GND": "GND",
        "SD_CLK": "SDIO_CLK",
        "SD_CMD": "SDIO_CMD",
        "SD_D0": "SDIO_D0",
        "SD_D1": "SDIO_D1",
        "SD_D2": "SDIO_D2",
        "SD_D3": "SDIO_D3",
        "CD_N": "SD_CARD_DETECT",
    },
    "expects": {
        "CD_N": _J1_MAP,
    },
    "notes": {
        "draws_card": "SD card write burst ~200 mA + pull-ups + "
                      "TXS02612 VCCB",
        "draws_host": "TXS02612 VCCA (SoM-side level)",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
