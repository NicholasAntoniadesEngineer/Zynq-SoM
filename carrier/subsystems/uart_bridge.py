"""uart_bridge — carrier ADAPTER for the reusable CP2102N USB-UART subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/uart_bridge/`` (netlist + README + SPICE + local test). This file
is the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written
sheet used, so the emitted carrier/schematic/uart_bridge.kicad_sch + its golden
render are unchanged.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_IO -> +3V3        CP2102N self-powered: VREGIN + VDD + VIO + the 1k ~RST
                         pull-up all sit on the carrier +3V3 rail.
  GND     -> GND         (identity).

  USB_VBUS -> USB_UART_VBUS   the wave-2 USB-UART receptacle's OWN 5 V VBUS (the
                         cable-attach detect the VBUS-sense pin is for) — NOT a
                         board input rail. FIX 2026-06-11 (schgen spice gate):
                         authoring this divider off +VIN would put 13.6 V on a
                         5.8 V abs-max pin after PD negotiates 20 V.
  USB_DP/DM -> USB_UART_DP/DM   the receptacle USB 2.0 HS pair (90R diff); the
                         USB receptacle subsystem lands in wave 2.

  UART crossover (TXD->RXD / RTS->CTS) lives HERE, in the bind map — the library
  brings the four UART signals out BRIDGE-RELATIVE, and the carrier wires them
  to the Zynq PS UART0 with the standard null-modem crossover:
  UART_TXD   -> ZYNQ_PS_UART0_RXD     bridge TXD (pin 21) -> Zynq RXD
  UART_RXD   -> ZYNQ_PS_UART0_TXD     Zynq TXD -> bridge RXD (pin 20)
  UART_RTS_N -> ZYNQ_PS_UART0_CTS_N   bridge ~RTS (pin 19) -> Zynq ~CTS
  UART_CTS_N -> ZYNQ_PS_UART0_RTS_N   Zynq ~RTS -> bridge ~CTS (pin 18)
                         The SoM contract exposes raw ZYNQ_PS_MIO* names; the
                         generated J1 sheet (wave 3) carries the MIO->UART0
                         function map, so the four UART ports are deferred there.

The USB ports bind on the generated wave-2 USB-UART connector sheet; the UART
ports on the wave-3 J1 MIO function map. The adapter declares those linker
deferrals via the library's ``expects`` hook.
"""

from __future__ import annotations

from subsystems.uart_bridge import uart_bridge as _lib
from schgen.core.model import Circuit

# Linker deferrals: the USB ports bind on the wave-2 USB-UART receptacle sheet;
# the four UART ports bind on the generated J1 sheet's MIO->UART0 function map.
# EXPLICIT deferrals so a standalone link reports them as awaiting their sheet,
# never a silent open.
_USB_MAP = "usb_uart_connector (wave 2)"
_J1_MAP = "som_j1_connector (wave 3 MIO function map)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net (incl the UART crossover)
#   expects USB ports -> wave-2 receptacle sheet; UART ports -> wave-3 J1 map
#   notes   power-tree draw note keeps the carrier's house-style wording
META = {
    "bind": {
        "+VDD_IO": "+3V3",
        "GND": "GND",
        "USB_VBUS": "USB_UART_VBUS",
        "USB_DP": "USB_UART_DP",
        "USB_DM": "USB_UART_DM",
        "UART_TXD": "ZYNQ_PS_UART0_RXD",      # bridge TXD -> Zynq RXD
        "UART_RXD": "ZYNQ_PS_UART0_TXD",      # Zynq TXD -> bridge RXD
        "UART_RTS_N": "ZYNQ_PS_UART0_CTS_N",  # bridge ~RTS -> Zynq ~CTS
        "UART_CTS_N": "ZYNQ_PS_UART0_RTS_N",  # Zynq ~RTS -> bridge ~CTS
    },
    "expects": {
        "USB_VBUS": _USB_MAP,
        "USB_DP": _USB_MAP,
        "UART_TXD": _J1_MAP,
        "UART_RXD": _J1_MAP,
        "UART_RTS_N": _J1_MAP,
        "UART_CTS_N": _J1_MAP,
    },
    "notes": {"draws": "CP2102N active ~14 mA typ + RST 1k pull-up"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
