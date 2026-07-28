"""usb_uart_connector — carrier ADAPTER for the reusable USB-C UFP receptacle.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/usb_uart_connector/`` (netlist + README + SPICE + local test). This
file is the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written sheet
used, so the emitted carrier/schematic/usb_uart_connector.kicad_sch + its golden
render are unchanged.

Wave-2 external console port. A USB 2.0 device-role (UFP) USB-C receptacle that
supplies the CP2102N USB-UART bridge (uart_bridge.py) over a protected data pair.
Type-C chosen for consistency with usbc_otg.py and to reuse the already-stocked
TYPE-C-31-M-12 receptacle in parts/.

CARRIER BINDING RATIONALE (the carrier net names + why):

  GND         -> GND       (identity).
  CHASSIS_GND -> CHASSIS_GND   (identity) — the receptacle shell/shield bond.

  These three PORTs bind the bridge's three deferred wave-2 ports (read VERBATIM
  from uart_bridge.py), giving the bridge its peer so its
  ``expect="usb_uart_connector (wave 2)"`` deferrals resolve to BOUND on both
  sheets:
  VBUS   -> USB_UART_VBUS   the receptacle 5 V VBUS (the bridge senses it through
                            its own 22k1/47k5 divider — datasheet self-powered
                            cable-attach). NOT a board input rail.
  USB_DP -> USB_UART_DP     the USB 2.0 HS data pair (90R diff), behind the ESD
  USB_DM -> USB_UART_DM     array; the bridge's USB data pins join these.

DEVICE-role (UFP) Type-C — the CC pins carry 5.1k Rd PULLDOWNS to GND (NOT the
host port's 56k Rp): this is what tells a source to apply VBUS. The CC nets are
subsystem-internal; only GND/CHASSIS_GND + the three USB peer ports are external.
"""

from __future__ import annotations

from subsystems.usb_uart_connector import usb_uart_connector as _lib
from schgen.core.model import Circuit

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind  abstract subsystem net -> carrier real net. The VBUS/USB_DP/USB_DM
#         PORTs are the EXACT carrier net names the uart_bridge peer binds for
#         its USB side (uart_bridge.py expects them on "usb_uart_connector (wave
#         2)"), so the two sheets join those nets at link time.
# No expects/notes: the connector PRODUCES these nets (the bridge defers TO it),
# the original sheet carried no port deferral, and this sheet adds no power-tree
# draw (a UFP/device port sinks, it does not source VBUS) — matching the hand-
# written sheet byte-for-byte.
META = {
    "bind": {
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "VBUS": "USB_UART_VBUS",
        "USB_DP": "USB_UART_DP",
        "USB_DM": "USB_UART_DM",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
