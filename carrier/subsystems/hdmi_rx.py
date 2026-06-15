"""hdmi_rx — carrier ADAPTER for the reusable HDMI-A sink subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/hdmi_rx/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT net names the hand-written sheet used, so the
emitted carrier/schematic/hdmi_rx.kicad_sch + its golden render are unchanged.

PENDING_MIGRATION: the library keeps J1's ``lib_id="schgen:HDMI_A_RX"`` override
VERBATIM — a tracked, allowlisted hand-built symbol (symbol_law) whose deep-
engine migration is handled separately. Binding does not touch lib_id.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_LOGIC  -> +3V3_HDMI_RX   the GATED module rail. Only the CEC 27k pull-up
                           sits here (~0.12 mA when CEC is driven low). The EEPROM
                           + EDID WC# write-protect are cable-5V-fed (COMP-1), so
                           nothing else draws from this rail.
  GND         -> GND       (identity). TMDS shields + DDC/CEC ground + EEPROM
                           ground + both ESD arrays' GND pads.
  CHASSIS_GND -> CHASSIS_GND   (identity). The four HDMI shell legs; star-bonded
                           to GND elsewhere (like the ethernet magjack shield).

  TMDS_RX_D2/D1/D0/CLK_P/N -> HDMI_RX_D2/D1/D0/CLK_P/N   the four RX TMDS pairs,
                           DC-coupled connector -> Zynq HR bank (bank 33, wave 3
                           FPGA bank function map). Each lane stays one net
                           {J1.pin, U2/U3.IOn} through the low-cap ESD shunt
                           (HDMIRX-1). The 2x49.9R/pair sink termination to AVCC
                           lives at the FPGA-bank (J2) end, NOT this sheet
                           (SI-HDMIRX-TERM): an HR bank does not self-terminate
                           TMDS_33, so external sink termination is placed at the
                           receiver bank balls.
  HDMI_5V_DET -> HDMI_RX_5V_DET   the cable-5V presence detect (10k/15k divider,
                           3.15 V max at 5.25 V — LVCMOS33-safe) to a 3V3 FPGA
                           bank input.
  CEC         -> HDMI_RX_CEC   3V3-domain CEC to the FPGA, with the spec 27k
                           pull-up to the gated module rail +3V3_HDMI_RX.

  The DDC I2C (HDMI_RX_SDA/SCL), HPD assert (HDMI_RX_HPD) and the cable-5V quasi-
  rail (HDMI_RX_5V) stay PRIVATE SIGNAL wiring inside the library — they run
  entirely connector<->EEPROM<->ESD on this sheet (DDC is source-mastered over
  the cable; HPD is 5-V-domain and not routed to a 3V3 bank), so they are NOT in
  the bind contract and keep their library names (identical to the carrier).

These ports bind on the generated J2/J3 sheets (som_conn_gen FUNCTION_MAP), so
the adapter declares that linker deferral via the library's ``expects`` hook.
"""

from __future__ import annotations

from subsystems.hdmi_rx import hdmi_rx as _lib
from schgen.core.model import Circuit

# The generated J2/J3 sheets (wave 3 FPGA bank function map) carry the TMDS/5V-
# det/CEC bank assignments, so these ports bind there by name. EXPLICIT linker
# deferral so a standalone link reports them as awaiting-J2/J3, never a silent open.
_J23_MAP = "som_j2_j3_connector (wave 3 FPGA bank function map)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects ports that bind on the generated J2/J3 sheets -> explicit linker deferral
#           (for a TMDS pair, the P line carries the pair's deferral)
#   notes   power-tree draw note cites the carrier's house-style wording
META = {
    "bind": {
        "+VDD_LOGIC": "+3V3_HDMI_RX",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "TMDS_RX_D2_P": "HDMI_RX_D2_P", "TMDS_RX_D2_N": "HDMI_RX_D2_N",
        "TMDS_RX_D1_P": "HDMI_RX_D1_P", "TMDS_RX_D1_N": "HDMI_RX_D1_N",
        "TMDS_RX_D0_P": "HDMI_RX_D0_P", "TMDS_RX_D0_N": "HDMI_RX_D0_N",
        "TMDS_RX_CLK_P": "HDMI_RX_CLK_P", "TMDS_RX_CLK_N": "HDMI_RX_CLK_N",
        "HDMI_5V_DET": "HDMI_RX_5V_DET",
        "CEC": "HDMI_RX_CEC",
    },
    "expects": {
        "TMDS_RX_D2_P": _J23_MAP,
        "TMDS_RX_D1_P": _J23_MAP,
        "TMDS_RX_D0_P": _J23_MAP,
        "TMDS_RX_CLK_P": _J23_MAP,
        "HDMI_5V_DET": _J23_MAP,
        "CEC": _J23_MAP,
    },
    "notes": {"draws": "CEC 27k pull-up (EEPROM + EDID WC# are cable-5V-fed)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
