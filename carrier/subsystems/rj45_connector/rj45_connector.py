"""rj45_connector — carrier ADAPTER for the reusable 8P8C RJ45 jack subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/rj45_connector/`` (netlist + README + SPICE + local test). This file
is the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written sheet
used, so the emitted carrier/schematic/rj45_connector.kicad_sch + its golden
render are byte-identical.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VLED       -> +3V3        the jack's two housing LEDs are a steady port-present
                             indicator off the always-on +3V3 rail (330R each,
                             ~4 mA). NOT a DIP-gated rail — the LEDs light at
                             power-on regardless of any module enable.
  GND         -> GND         (identity). The LED cathodes return to signal GND.
  CHASSIS_GND -> CHASSIS_GND (identity). The shield/shell (J1.13) bonds to the
                             chassis island — the same separate net the ethernet
                             sheet's C5 isolation barrier bonds to (kept separate
                             from signal GND, star-bonded elsewhere on the
                             carrier). The four M3 corner mounting holes are NOT
                             on this jack sheet: they moved to the carrier-LOCAL
                             ``mechanical`` sheet so the PCB placer corner-forces
                             them as their own cluster instead of bundling them
                             into this jack's per-subsystem ratsnest.

  Line-side MDI pairs (face the ethernet magnetics' MEDIA side, ETH_LINE_MDI_x):
    RJ45_MDI0_P/N -> ETH_LINE_MDI_0_P/N   (BI_DA, contacts 1,2)
    RJ45_MDI1_P/N -> ETH_LINE_MDI_1_P/N   (BI_DB, contacts 3,6)
    RJ45_MDI2_P/N -> ETH_LINE_MDI_2_P/N   (BI_DC, contacts 4,5)
    RJ45_MDI3_P/N -> ETH_LINE_MDI_3_P/N   (BI_DD, contacts 7,8)
                             The four 1000BASE-T differential pairs. The ethernet
                             magnetics subsystem exposes these media-side (its MXn
                             ports) and declares an ``expects`` deferral on them
                             that names THIS sheet ("rj45_connector (wave 2)"); by
                             binding both subsystems to the same ETH_LINE_MDI_x
                             nets, that deferral resolves to BOUND on both sheets.
                             So this adapter does NOT itself defer them — it is the
                             peer that binds them.

The two housing-LED anode nodes (RJ45_LED_L / RJ45_LED_R) stay INTERNAL to the
library sheet — they are private SIGNAL wiring, never bound here.
"""

from __future__ import annotations

from subsystems.rj45_connector import rj45_connector as _lib
from schgen.core.model import Circuit

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   notes   power-tree draw note (carrier house-style prose)
# (the line-side MDI pairs are BOUND here — this is the peer sheet for the
#  ethernet subsystem's media-side deferral — so no expects; no named bus.)
META = {
    "bind": {
        "+VLED": "+3V3",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        # line-side MDI pairs -> the carrier's line MDI nets (the ethernet
        # magnetics' media side binds these same nets)
        "RJ45_MDI0_P": "ETH_LINE_MDI_0_P", "RJ45_MDI0_N": "ETH_LINE_MDI_0_N",
        "RJ45_MDI1_P": "ETH_LINE_MDI_1_P", "RJ45_MDI1_N": "ETH_LINE_MDI_1_N",
        "RJ45_MDI2_P": "ETH_LINE_MDI_2_P", "RJ45_MDI2_N": "ETH_LINE_MDI_2_N",
        "RJ45_MDI3_P": "ETH_LINE_MDI_3_P", "RJ45_MDI3_N": "ETH_LINE_MDI_3_N",
    },
    "notes": {"draws": "RJ45 housing LEDs (2x 330R port-present indicator)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
