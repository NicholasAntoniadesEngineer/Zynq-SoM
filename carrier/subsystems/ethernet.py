"""ethernet — carrier ADAPTER for the reusable HX5008NL magnetics subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/ethernet/`` (netlist + README + SPICE + local test). This file is
the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written
sheet used, so the emitted carrier/schematic/ethernet.kicad_sch + its golden
render are byte-identical.

CARRIER BINDING RATIONALE (the carrier net names + why):

  CHASSIS_GND -> CHASSIS_GND   (identity). The chassis-ground island: the
                           Bob-Smith trunk's single 1n/2kV barrier cap bypasses
                           to it. A separate net from signal GND, star-bonded
                           elsewhere on the carrier.

  CHIP / PHY-side pairs (face the SoM PHY, RTL8211F via J1 ETH_PHY_MDIx):
    MDI0_P/N -> ETH_PHY_MDI0_P/N
    MDI1_P/N -> ETH_PHY_MDI1_P/N
    MDI2_P/N -> ETH_PHY_MDI2_P/N
    MDI3_P/N -> ETH_PHY_MDI3_P/N
                           The four 1000BASE-T differential pairs that face the
                           SoM PHY; the SoM exposes only the MDI pairs across J1
                           (no CT-bias path crosses the mezzanine — the chip-side
                           centre taps stay NC, the PHY self-biases).

  MEDIA / RJ45-side pairs (face the RJ45 jack, ETH_LINE_MDI_x):
    MX0_P/N -> ETH_LINE_MDI_0_P/N
    MX1_P/N -> ETH_LINE_MDI_1_P/N
    MX2_P/N -> ETH_LINE_MDI_2_P/N
    MX3_P/N -> ETH_LINE_MDI_3_P/N
                           The media-side pairs to the RJ45 jack. The 1:1 winding
                           is IN PHASE, so + couples to + (MDIx_P <-> LINE_x_P).
                           These bind on the SEPARATE rj45_connector subsystem
                           (wave 2), so the adapter declares that linker deferral
                           via the library's ``expects`` hook (only the P net of
                           each pair need be named — the reciprocal N inherits
                           the deferral).

The four CHIP-side centre taps + the four media-side Bob-Smith centre taps
(MCT1..MCT4) and the shared trunk (BS_COMMON) stay INTERNAL to the library sheet
— they are private SIGNAL wiring, never bound here.
"""

from __future__ import annotations

from subsystems.ethernet import ethernet as _lib
from schgen.core.model import Circuit

# The media-side MDI pairs bind on the separate rj45_connector subsystem (wave
# 2), so EXPLICIT linker deferral makes a standalone link report them as
# awaiting-RJ45, never a silent open. Only the P net of each pair need be named
# (the reciprocal N inherits the deferral via the diff-pair complement).
_RJ45 = "rj45_connector (wave 2)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects media-side pairs that bind on the rj45_connector sheet -> deferral
# (no power rail to budget, no named bus -> no buses/notes here.)
META = {
    "bind": {
        "CHASSIS_GND": "CHASSIS_GND",
        # CHIP / PHY-side pairs -> SoM PHY MDI lanes
        "MDI0_P": "ETH_PHY_MDI0_P", "MDI0_N": "ETH_PHY_MDI0_N",
        "MDI1_P": "ETH_PHY_MDI1_P", "MDI1_N": "ETH_PHY_MDI1_N",
        "MDI2_P": "ETH_PHY_MDI2_P", "MDI2_N": "ETH_PHY_MDI2_N",
        "MDI3_P": "ETH_PHY_MDI3_P", "MDI3_N": "ETH_PHY_MDI3_N",
        # MEDIA / RJ45-side pairs -> line MDI pairs
        "MX0_P": "ETH_LINE_MDI_0_P", "MX0_N": "ETH_LINE_MDI_0_N",
        "MX1_P": "ETH_LINE_MDI_1_P", "MX1_N": "ETH_LINE_MDI_1_N",
        "MX2_P": "ETH_LINE_MDI_2_P", "MX2_N": "ETH_LINE_MDI_2_N",
        "MX3_P": "ETH_LINE_MDI_3_P", "MX3_N": "ETH_LINE_MDI_3_N",
    },
    "expects": {
        "MX0_P": _RJ45, "MX1_P": _RJ45, "MX2_P": _RJ45, "MX3_P": _RJ45,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
