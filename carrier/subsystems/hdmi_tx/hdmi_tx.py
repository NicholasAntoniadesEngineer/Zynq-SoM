"""hdmi_tx — carrier ADAPTER for the reusable TPD12S016 HDMI-source subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/hdmi_tx/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT same net names the hand-written sheet used, so the
emitted carrier/schematic/hdmi_tx.kicad_sch + its golden render are unchanged.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_IO   -> +3V3_HDMI_TX   V_CCA (controller side). The bring-up dossier's
                              GATED module rail (bringup_power_gating): the
                              SY6280 load switch gates +3V3_HDMI_TX on the
                              bringup sheet; this sheet just decouples it (DS
                              Fig 15) and owns its 10u bulk (each module owns
                              its bulk, matching the camera/microsd peers).
  +5V       -> +5V_HDMI_TX    V_CC5V, the load-switch INPUT (cable side). Also a
                              GATED module rail; the TPD's integrated 55 mA
                              current-limited switch drives the cable's +5V from
                              it (DS 7.3.10).
  GND       -> GND            (identity).
  CHASSIS_GND -> CHASSIS_GND  (identity). The four HDMI shell legs bond to the
                              chassis island, star-bonded to GND elsewhere.

  TMDS_D2/1/0/CLK_P/N -> ZYNQ_HDMI_TX_TMDS_2/1/0/CLK_P/N   the 8 differential
                              TMDS lines from the Zynq PL. These flow THROUGH the
                              TPD clamp pads to the receptacle (one net per lane).
  CEC      -> ZYNQ_HDMI_TX_CEC   A-side (V_CCA) CEC line to the Zynq PL.
  DDC_SCL  -> ZYNQ_HDMI_TX_SCL   } the HDMI DDC (I2C) bus to the Zynq PL. Pull-ups
  DDC_SDA  -> ZYNQ_HDMI_TX_SDA   } are INTEGRATED in the TPD12S016 (DS 7.3.9/
                              7.3.15) — none on-board (the library waives them).
  HPD      -> ZYNQ_HDMI_TX_HPD   A-side hot-plug-detect to the Zynq PL.

All eight TMDS lines and the four control lines bind on the generated J2 sheet
(som_conn_gen wave-3 PL FUNCTION_MAP), so the adapter declares that linker
deferral via the library's ``expects`` hook (the P line of each TMDS pair carries
the pair's deferral; the reciprocal N type is registered automatically).
"""

from __future__ import annotations

from subsystems.hdmi_tx import hdmi_tx as _lib
from schgen.core.model import Circuit

# The generated J2 sheet (som_conn_gen FUNCTION_MAP) carries the Zynq PL
# function map, so these ports bind there by name. EXPLICIT linker deferral so a
# standalone link reports them as awaiting-J2, never a silent open.
_J2_MAP = "som_j2_connector (wave 3 PL function map)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects ports that bind on the generated J2 sheet -> explicit linker deferral
# (buses/notes are left at the library defaults, which already equal the
#  carrier's house-style HDMI_TX_DDC bus name + power-tree draw notes, so the
#  carrier's derived artifacts stay byte-identical without an override.)
META = {
    "bind": {
        "+VDD_IO": "+3V3_HDMI_TX",
        "+5V": "+5V_HDMI_TX",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "TMDS_D2_P": "ZYNQ_HDMI_TX_TMDS_2_P",
        "TMDS_D2_N": "ZYNQ_HDMI_TX_TMDS_2_N",
        "TMDS_D1_P": "ZYNQ_HDMI_TX_TMDS_1_P",
        "TMDS_D1_N": "ZYNQ_HDMI_TX_TMDS_1_N",
        "TMDS_D0_P": "ZYNQ_HDMI_TX_TMDS_0_P",
        "TMDS_D0_N": "ZYNQ_HDMI_TX_TMDS_0_N",
        "TMDS_CLK_P": "ZYNQ_HDMI_TX_TMDS_CLK_P",
        "TMDS_CLK_N": "ZYNQ_HDMI_TX_TMDS_CLK_N",
        "CEC": "ZYNQ_HDMI_TX_CEC",
        "DDC_SCL": "ZYNQ_HDMI_TX_SCL",
        "DDC_SDA": "ZYNQ_HDMI_TX_SDA",
        "HPD": "ZYNQ_HDMI_TX_HPD",
    },
    "expects": {
        # the P line of each TMDS pair (the reciprocal N gets the same deferral)
        "TMDS_D2_P": _J2_MAP,
        "TMDS_D1_P": _J2_MAP,
        "TMDS_D0_P": _J2_MAP,
        "TMDS_CLK_P": _J2_MAP,
        "CEC": _J2_MAP,
        "DDC_SCL": _J2_MAP,
        "DDC_SDA": _J2_MAP,
        "HPD": _J2_MAP,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
