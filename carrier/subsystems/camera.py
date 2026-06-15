"""camera — carrier ADAPTER for the reusable RPi-FFC MIPI CSI-2 camera subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/camera/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT net names the hand-written sheet used, so the
emitted carrier/schematic/camera.kicad_sch + its golden render are unchanged.

Authored per carrier/research/camera_csi.md (lane map section 1, netlist sketch
section 4): SFW15R-1STE1LF 1.0 mm 15P bottom-contact FFC (LCSC C3168538 —
LIVE-verified 2026-06-11: stock 4,000, Extended; contact orientation verified
against Amphenol drawing 10172241 and the generated footprint). FFC pin n = RPi
camera FFC pin n.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_CAM -> +3V3_CAM   the bring-up-gated module rail (SY6280 cell #4 on
                         bringup_modules, 523 mA limit vs 300 mA budget), same
                         contract as +3V3_PMOD / +3V3_SD / +3V3_USER_LED. The
                         camera-control I2C pull-ups (4k7, C23162) tie to this
                         GATED rail so a powered-down camera is not back-fed
                         through its bus pull-ups. 100n + 10u (C14663 + C15850,
                         the wave-1 pair) at the connector.
  GND      -> GND        (identity) — FFC grounds 1/4/7/10 + mounting tabs 16/17.

  CSI lanes -> the carrier's CAM_* diff pairs, destined for J3 bank 35 (LVDS_25,
  +VCCO_35 = 2.5 V from a local LDO — dossier risk 1; bank 35 is then 2.5 V-only
  and nothing 3.3 V may be allocated there, so the control lines go to bank 33):
    CSI_D0_P/N  -> CAM_D0_P/N    (FFC 3/2 -> IO_L10_P/N_35,        J3.5/7)
    CSI_D1_P/N  -> CAM_D1_P/N    (FFC 6/5 -> IO_L15_DQS_P/N_35,    J3.17/15)
    CSI_CLK_P/N -> CAM_CLK_P/N   (FFC 9/8 -> IO_L13_MRCC_P/N_35,   J3.9/11)
  100R differential terminations (R1-R3, C22775) live FPGA-side per XAPP894 —
  LAYOUT NOTE: place R1-R3 at the SoM-connector end of the traces, not at the
  FFC. CAM-1 (electrical audit): the 100R stays POPULATED (HS D-PHY needs it; the
  HR-bank RX cannot gate DIFF_TERM). LP observability is the XAPP894 LP
  resistor-divider DNP stuffing option on a reserved bank-35 pair (L18_35,
  J3.27/25 — L16_35 J3.31/29 is now the watchdog; repick the 2nd pair vs
  FUNCTION_MAP before stuffing), NOT spent on this FFC sheet (see the library
  README). Video-only capture works without them.

  CAM_SCL/CAM_SDA -> CAM_SCL/CAM_SDA   (FFC 13/14) the dedicated camera I2C bus
                         CAM_I2C — a Zynq-fabric bus (AXI IIC / PS I2C via EMIO),
                         NOT the STM32_I2C2 bus (different controller domain).
                         Bank 33 (+VCCO_33 = +3V3, 3.3 V logic).
  CAM_EN  -> CAM_EN      (FFC 11) module shutdown, bank 33.
  CAM_LED -> CAM_LED     (FFC 12) v1-only indicator, kept routed, bank 33.

These ports bind on the generated J3 sheet (som_conn_gen FUNCTION_MAP), so the
adapter declares that linker deferral via the library's ``expects`` hook: the CSI
lanes on bank 35 (2.5 V LVDS), the control lines on bank 33 (3.3 V).
"""

from __future__ import annotations

from subsystems.camera import camera as _lib
from schgen.core.model import Circuit

# The generated J3 sheet (som_conn_gen FUNCTION_MAP) carries the bank-35 LVDS_25
# CSI lanes and the bank-33 3.3 V control lines, so these ports bind there by
# name. EXPLICIT linker deferral so a standalone link reports them as awaiting-J3,
# never a silent open. (Same deferral strings the hand-written sheet used.)
_J3_35 = "som_j3_connector (PL bank 35, LVDS_25, +VCCO_35=2.5V)"
_J3_33 = "som_j3_connector (PL bank 33, +VCCO_33=3.3V)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects ports that bind on the generated J3 sheet -> explicit linker deferral
#           (CSI lanes -> bank 35; control I2C + EN/LED -> bank 33)
#   buses   the dedicated camera I2C is the carrier CAM_I2C bus
#   notes   power-tree draw note cites the carrier dossier wording (camera_csi.md)
# (buses/notes keep the carrier's derived artifacts — layout_constraints.csv bus
#  grouping, power_tree.txt note — byte-identical to the hand-written sheet.)
META = {
    "bind": {
        "+VDD_CAM": "+3V3_CAM",
        "GND": "GND",
        "CSI_D0_P": "CAM_D0_P",
        "CSI_D0_N": "CAM_D0_N",
        "CSI_D1_P": "CAM_D1_P",
        "CSI_D1_N": "CAM_D1_N",
        "CSI_CLK_P": "CAM_CLK_P",
        "CSI_CLK_N": "CAM_CLK_N",
        "CAM_SCL": "CAM_SCL",
        "CAM_SDA": "CAM_SDA",
        "CAM_EN": "CAM_EN",
        "CAM_LED": "CAM_LED",
    },
    "expects": {
        "CSI_D0_P": _J3_35,
        "CSI_D0_N": _J3_35,
        "CSI_D1_P": _J3_35,
        "CSI_D1_N": _J3_35,
        "CSI_CLK_P": _J3_35,
        "CSI_CLK_N": _J3_35,
        "CAM_SCL": _J3_33,
        "CAM_SDA": _J3_33,
        "CAM_EN": _J3_33,
        "CAM_LED": _J3_33,
    },
    "buses": {"i2c": "CAM_I2C"},
    "notes": {"draws": "RPi camera module budget (camera_csi.md: V2 typ ~250 mA)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
