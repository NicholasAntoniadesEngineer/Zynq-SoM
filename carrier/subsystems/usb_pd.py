"""usb_pd — carrier ADAPTER for the reusable FUSB302B USB-PD sink subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/usb_pd/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT same net names the hand-written sheet used, so the
emitted carrier/schematic/usb_pd.kicad_sch + its golden render are unchanged.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_LOGIC  -> +3V3_SC   FUSB302B VDD/INT live on the SoM system-controller
                           rail (+3V3_SC), an ALWAYS-ON rail, NEVER a DIP-gated
                           carrier rail. Bring-up dossier risk R1
                           (carrier/research/bringup_power_gating.md): PD
                           negotiation must happen BEFORE any DIP-gated carrier
                           rail exists — the board boots on default 5 V VBUS.
  +VBUS_SENSE -> +VBUS_IN  the RAW receptacle VBUS, AHEAD of the round-5
                           TPS26631 inlet eFuse (pd_input): the PD PHY must
                           observe vSafe5V/vbus at the connector itself for
                           attach detection, not the dVdT-ramped rail behind the
                           eFuse. AMX-1: U1.2 sits at its 21.0 V recommended-max
                           at the legal 20 V+5% contract (abs-max 28 V); +VBUS_IN
                           is bounded only by the SMBJ22A TVS (pd_input D1).
  GND         -> GND       (identity).

  CC1/CC2 -> STM32_USB_CC1/2   the receptacle CC lines (pd_input.J1). PD-CC-1
                           (firmware contract): the FUSB302B OWNS CC1/CC2 (Rd/Rp,
                           vRd sensing, BMC PHY, VCONN switching). The SoM/STM32
                           SC firmware MUST NOT enable its native UCPD on these
                           lines (double-termination corrupts advertised current
                           + garbles BMC framing). The SoM-side CC pins are STM32
                           PB6 (CC1)/PB4 (CC2) brought bare to J1.29/31; firmware
                           holds them input-only/Hi-Z. The SC talks PD only over
                           I2C (0x22) + INT_N.
  I2C_SDA/SCL -> STM32_I2C2_SDA/SCL   the shared STM32_I2C2 bus. The bus
                           pull-ups (4k7 to +3V3_SC) live ONCE on bringup_rails
                           with the TCA9535 — not duplicated here.
  INT_N   -> SC_INT_N      G2 (wave3_function_map.md sec 1.1): the FUSB302 INT
                           and the TCA9535 INT# wire-OR onto the SINGLE shared SC
                           interrupt SC_INT_N (STM32_GPIO4=PA15). ONE pull-up per
                           net: the bringup_rails 10k pull is the only one — none
                           here.

These ports bind on the generated J1 sheet (som_conn_gen FUNCTION_MAP), so the
adapter declares that linker deferral via the library's ``expects`` hook.
"""

from __future__ import annotations

from subsystems.usb_pd import usb_pd as _lib
from schgen.core.model import Circuit

# Abstract subsystem net -> carrier real net (the carrier binding map).
BIND = {
    "+VDD_LOGIC": "+3V3_SC",
    "+VBUS_SENSE": "+VBUS_IN",
    "GND": "GND",
    "CC1": "STM32_USB_CC1",
    "CC2": "STM32_USB_CC2",
    "I2C_SDA": "STM32_I2C2_SDA",
    "I2C_SCL": "STM32_I2C2_SCL",
    "INT_N": "SC_INT_N",
}

# The generated J1 sheet (som_conn_gen FUNCTION_MAP) carries the GPIO->I2C2/INT
# function map, so these ports bind there by name. EXPLICIT linker deferral so a
# standalone link reports them as awaiting-J1, never a silent open.
_J1_MAP = "som_j1_connector (wave 3 STM32 GPIO function map)"
EXPECTS = {
    "I2C_SDA": _J1_MAP,
    "I2C_SCL": _J1_MAP,
    "INT_N": _J1_MAP,
}

# Carrier house-style metadata the adapter restores so the carrier's derived
# artifacts (layout_constraints.csv bus grouping, power_tree.txt note) are
# byte-identical: the FUSB302 I2C lives on the carrier's STM32_I2C2 bus, and the
# draw note cites the G2 wire-OR / bringup_rails dossier wording.
I2C_BUS = "STM32_I2C2"
DRAWS_NOTE = ("FUSB302B VDD (<1 mA); SC_INT_N pulled on bringup_rails "
              "(G2 wire-OR, single 10k)")


def circuit() -> Circuit:
    return _lib.circuit(bind=BIND, expects=EXPECTS,
                        i2c_bus=I2C_BUS, draws_note=DRAWS_NOTE)
