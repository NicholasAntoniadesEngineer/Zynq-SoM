"""usb_jtag — carrier ADAPTER for the reusable CH347T USB-JTAG/UART subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/usb_jtag/`` (netlist + README + SPICE + local test). This file is
the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written
sheet used, so the emitted carrier/schematic/usb_jtag.kicad_sch + its golden
render are unchanged.

Stream-C C1. A USB-C cable plugged here gives a host PC a Zynq JTAG programmer
AND a console UART (one CH347 channel each, MODE 3) WITHOUT any external pod —
and it does so even when the carrier's main rails are OFF, because the bridge
runs entirely off its OWN debug-USB VBUS and its JTAG IO is buffered so it never
back-feeds an unpowered carrier (SELF-POWERED + ISOLATED). The contention proof,
the CH347-vs-FT2232H part choice, the MODE-3 strap and the crystal-load-cap
sizing all live in the library docstring + ``subsystems/usb_jtag/README.md``.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VBUS_USB   -> +5V_DBG    the debug-USB receptacle's OWN 5 V VBUS (the LDO U4
                            input), published by the usb_jtag_connector sheet.
                            Alive ONLY with the debug cable plugged -> the whole
                            self-powered island is too (constraint C1).
  +3V3_ISLAND -> +3V3_DBG   the self-powered island rail (U4 AP2112K output) that
                            powers the CH347, the buffer and all the pulls. NOT a
                            carrier system rail — it exists only while the debug
                            cable is present.
  GND         -> GND        (identity).

  USB_DP/DM -> DBG_USB_DP/DM   the ESD-protected USB 2.0 HS pair from the
                            usb_jtag_connector sheet (USB-C UFP receptacle +
                            USBLC6-2SC6 D+/D- ESD). The CH347 UD+/UD- take the bus
                            directly (DS forbids a series R); the USBLC6 is a
                            SHUNT array, no series element added.

  JTAG_TCK/TDI/TMS/TDO -> ZYNQ_TCK/TDI/TMS/TDO   the carrier exposes these on the
                            debug_boot 2x7 JTAG header (a passive connector + the
                            TMS/TDI 4k7 insurance pulls). The SN74LVC125 buffer +
                            the SW1-gated, default-HIGH OE# guarantee the bridge
                            never contends with a pod on that header (LAW-0).

  UART crossover -> Zynq PL-bank UART (bank 13 EMIO). The library brings the two
  UART lines out BRIDGE-RELATIVE; the carrier wires them to a free PL-bank UART
  with the standard 2-wire console mapping:
    UART_RXD -> DBG_UART_RXD   CH347 TXD1 (pin 3) -> Zynq RXD
    UART_TXD -> DBG_UART_TXD   Zynq TXD -> CH347 RXD1 (pin 4)
  Bank 13 is +VCCO_13 = +3V3 = LVCMOS33, matching the CH347 3.3 V IO (level-safe).
  The generated J2 sheet (som_conn_gen FUNCTION_MAP) carries the bank-13 EMIO
  UART map, so the two UART ports are deferred there.

The USB pair binds on the usb_jtag_connector sheet; the JTAG ports on the
debug_boot header; the UART ports on the generated J2 MIO function map. The
adapter declares those linker deferrals via the library's ``expects`` hook.
"""

from __future__ import annotations

from subsystems.usb_jtag import usb_jtag as _lib
from schgen.core.model import Circuit

# Linker deferrals (EXACT prior carrier deferral strings — kept byte-stable so a
# standalone link reports each port as awaiting its sheet, never a silent open):
#   the USB pair binds on the usb_jtag_connector sheet (USB-C UFP + USBLC6 ESD);
#   the JTAG ports on the debug_boot 2x7 header (same ZYNQ_T* nets);
#   the UART ports on the generated J2 sheet (PL bank 13 EMIO UART, LVCMOS33).
_USB_MAP = "usb_jtag_connector (USB-C UFP receptacle + USBLC6 ESD)"
_J2_MAP = "som_j2_connector (PL bank 13 EMIO UART, LVCMOS33 — FUNCTION_MAP)"
_HDR_MAP = "debug_boot (the 2x7 JTAG header carries the same ZYNQ_T* nets)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects USB pair -> usb_jtag_connector; JTAG -> debug_boot; UART -> J2 map
#   notes   power-tree draw note keeps the carrier's house-style wording
META = {
    "bind": {
        "+VBUS_USB": "+5V_DBG",
        "+3V3_ISLAND": "+3V3_DBG",
        "GND": "GND",
        "USB_DP": "DBG_USB_DP",
        "USB_DM": "DBG_USB_DM",
        "JTAG_TCK": "ZYNQ_TCK",
        "JTAG_TDI": "ZYNQ_TDI",
        "JTAG_TMS": "ZYNQ_TMS",
        "JTAG_TDO": "ZYNQ_TDO",
        "UART_RXD": "DBG_UART_RXD",      # CH347 TXD1 -> Zynq RXD
        "UART_TXD": "DBG_UART_TXD",      # Zynq TXD -> CH347 RXD1
    },
    "expects": {
        "USB_DP": _USB_MAP,
        "JTAG_TCK": _HDR_MAP,
        "JTAG_TDI": _HDR_MAP,
        "JTAG_TMS": _HDR_MAP,
        "JTAG_TDO": _HDR_MAP,
        "UART_RXD": _J2_MAP,
        "UART_TXD": _J2_MAP,
    },
    "notes": {"draws": "CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull "
                       "network"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
