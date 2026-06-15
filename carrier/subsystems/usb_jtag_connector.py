"""usb_jtag_connector — carrier ADAPTER for the reusable USB-C UFP receptacle.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/usb_jtag_connector/`` (netlist + README + SPICE + local test). This
file is the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written sheet
used, so the emitted carrier/schematic/usb_jtag_connector.kicad_sch + its golden
render are unchanged.

Stream-C C1, the connector half (the carrier's "connectors get their own sheet"
idiom — the twin of usb_uart_connector for the CP2102N). A USB 2.0 device-role
(UFP) USB-C receptacle supplies the CH347T USB-JTAG/UART bridge (usb_jtag.py)
over a protected data pair + its own 5 V VBUS. Splitting the receptacle off keeps
neither sheet dense enough to defeat the placer's escape-lane router (the CH347T
+ crystal + LDO + buffer alone is already a busy sheet). The DEVICE-role Rd
strapping, the USB-2 flip-pair short, the USBLC6 SHUNT-array (no series R)
rationale and the live-verified parts all live in the library docstring +
``subsystems/usb_jtag_connector/README.md``.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VBUS   -> +5V_DBG    the receptacle 5 V VBUS, published as +5V_DBG: the
                        bridge's self-powered island source (a POWER rail so it
                        merges by name onto usb_jtag's AP2112K LDO input — the
                        bridge is alive only with the cable plugged, constraint
                        C1).
  GND         -> GND         (identity).
  CHASSIS_GND -> CHASSIS_GND  (identity) — the receptacle shell (EH) -> chassis.

  USB_DP/USB_DM -> DBG_USB_DP/DBG_USB_DM   the USB 2.0 HS data pair (90R diff)
                        AFTER the USBLC6-2SC6 ESD array, feeding the CH347T
                        bridge. The CH347 UD+/UD- take the bus directly (its DS
                        forbids a SERIES R on the data lines); the USBLC6 is a
                        SHUNT array, so it adds no series element.

The protected USB pair binds on the usb_jtag (CH347T bridge) sheet, so the
adapter declares that linker deferral via the library's ``expects`` hook (the
EXACT prior carrier deferral string — kept byte-stable so a standalone link
reports the pair as awaiting the bridge, never a silent open).
"""

from __future__ import annotations

from subsystems.usb_jtag_connector import usb_jtag_connector as _lib
from schgen.core.model import Circuit

# The protected USB pair is consumed on the usb_jtag (CH347T bridge) sheet, which
# binds DBG_USB_DP/DM by name. EXPLICIT linker deferral so a standalone link
# reports the pair as awaiting-bridge, never a silent open.
_BRIDGE = "usb_jtag (CH347T bridge)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects the protected USB pair -> the usb_jtag (CH347T bridge) sheet
META = {
    "bind": {
        "+VBUS": "+5V_DBG",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "DBG_USB_DP",
        "USB_DM": "DBG_USB_DM",
    },
    "expects": {
        "USB_DP": _BRIDGE,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
