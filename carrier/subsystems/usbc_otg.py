"""usbc_otg — carrier ADAPTER for the reusable USB 2.0 HS OTG port subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/usbc_otg/`` (netlist + README + SPICE + local test). This file is
the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written
sheet used, so the emitted carrier/schematic/usbc_otg.kicad_sch + its golden
render are unchanged.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VBUS_SUPPLY -> +5V_USB   the bring-up-gated module rail (SY6280 on the bringup
                            sheet): a POWER net with its own power symbol, like
                            +3V3_HDMI_TX. The port SOURCES this onto the cable
                            VBUS via the TPS2051C current-limited switch.
  +VDD_LOGIC   -> +3V3_SC   the SoM system-controller rail. G4 ABS-MAX FIX
                            (wave3_function_map.md sec 1.2): the FLT# pull-up is
                            re-railed +5V_USB -> +3V3_SC. A TCA9535 IO abs-max is
                            VCC+0.5 = 3.8 V (TI SCPS201E); a 5 V pull on P14
                            violates it. +3V3_SC keeps FLT# readable even with
                            the +5V_USB module rail gated OFF (the flag is valid
                            low when the port is unpowered).
  GND          -> GND       (identity).
  CHASSIS_GND  -> CHASSIS_GND   (identity) — the receptacle shell/shield bond.

  VBUS    -> USB_VBUS       the connector VBUS the SoM senses (TPS2051 OUT + the
                            receptacle VBUS pads; also CC Rp ref + ESD VBUS pin).
  VBUS_EN -> VBUS_OUT_EN    the SoM VBUS-source enable (contract J1.38). Binds on
                            the generated J1 sheet (som_conn_gen FUNCTION_MAP).
  FLT_N   -> USBOTG_FLT_N   the open-drain fault flag, reported to the SoM SC via
                            the TCA9535 expander port P14 (bringup_rails, G4; no
                            free STM32 GPIO). Binds on the bringup sheet.
  USB_ID  -> USB_ID         (identity) the OTG ID (contract J1.20), strapped low
                            through 1k = HOST role for this port (the FS+PD
                            Type-C is the device/dual-role port). Binds on J1.
  USB_DP/USB_DM -> USB_D+/USB_D-   the SoM USB HS PHY data pair (90 ohm diff).

VBUS_EN / USB_ID bind on the generated J1 sheet (som_conn_gen FUNCTION_MAP) and
FLT_N binds on the bringup sheet, so the adapter declares those linker deferrals
via the library's ``expects`` hook.
"""

from __future__ import annotations

from subsystems.usbc_otg import usbc_otg as _lib
from schgen.core.model import Circuit

# The generated J1 sheet (som_conn_gen FUNCTION_MAP) carries the SoM GPIO
# function map, so VBUS_OUT_EN / USB_ID bind there by name. EXPLICIT linker
# deferral so a standalone link reports them as awaiting-J1, never a silent open.
_J1_MAP = "som_j1_connector (STM32 GPIO function map)"
# FLT# is reported to the SC via the TCA9535 expander (bringup_rails P14).
_FLT_BRINGUP = "bringup (TCA9535 expander port P14)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects ports that bind off-sheet (J1 function map / bringup expander)
#   notes   power-tree draw notes cite the carrier dossier wording (G4 re-rail)
# (notes keep the carrier's derived power_tree.txt note byte-identical to the
#  hand-written sheet.)
META = {
    "bind": {
        "+VBUS_SUPPLY": "+5V_USB",
        "+VDD_LOGIC": "+3V3_SC",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "USB_D+",
        "USB_DM": "USB_D-",
        "VBUS": "USB_VBUS",
        "VBUS_EN": "VBUS_OUT_EN",
        "FLT_N": "USBOTG_FLT_N",
        "USB_ID": "USB_ID",
    },
    "expects": {
        "VBUS_EN": _J1_MAP,
        "USB_ID": _J1_MAP,
        "FLT_N": _FLT_BRINGUP,
    },
    "notes": {
        "draws_vbus": "downstream USB device budget, TPS2051C current-limited",
        "draws_flt": "USBOTG_FLT# 100k pull-up (G4 re-rail)",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
