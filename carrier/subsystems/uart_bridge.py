"""uart_bridge project bind — circuit + basis: subsystems/uart_bridge/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.uart_bridge import uart_bridge as _lib

_SUB = "uart_bridge"
_USB_MAP = "usb_uart_connector (wave 2)"
_J1_MAP = "som_j1_connector (wave 3 MIO function map)"

_VDD_IO = bind(
    _SUB, "+VDD_IO", "+3V3",
    "CP2102N self-powered: VREGIN, VDD, VIO and the 1k ~RST pull-up all sit on "
    "the carrier +3V3 rail.",
    "datasheet")

_USB_VBUS = bind(
    _SUB, "USB_VBUS", "USB_UART_VBUS",
    "The receptacle's OWN 5 V VBUS — the cable-attach detect the VBUS-sense pin "
    "is for. Authoring this divider off +VIN would put 13.6 V on a 5.8 V "
    "abs-max pin once PD negotiates 20 V (schgen spice gate, 2026-06-11).",
    "datasheet")

_CROSSOVER = {
    port: bind(_SUB, port, net, basis, "datasheet")
    for port, net, basis in (
        ("UART_TXD", "ZYNQ_PS_UART0_RXD",
         "NULL-MODEM CROSSOVER, and it lives HERE in the bind, not in the "
         "library: bridge TXD (pin 21) drives the Zynq RXD net."),
        ("UART_RXD", "ZYNQ_PS_UART0_TXD",
         "Crossover twin: the Zynq TXD net drives bridge RXD (pin 20)."),
        ("UART_RTS_N", "ZYNQ_PS_UART0_CTS_N",
         "Crossover twin: bridge ~RTS (pin 19) drives the Zynq ~CTS net."),
        ("UART_CTS_N", "ZYNQ_PS_UART0_RTS_N",
         "Crossover twin: the Zynq ~RTS net drives bridge ~CTS (pin 18)."),
    )
}

META = {
    "bind": {
        "+VDD_IO": _VDD_IO,
        "GND": "GND",
        "USB_VBUS": _USB_VBUS,
        "USB_DP": "USB_UART_DP",
        "USB_DM": "USB_UART_DM",
        **_CROSSOVER,
    },
    "expects": {
        "USB_VBUS": _USB_MAP,
        "USB_DP": _USB_MAP,
        **{port: _J1_MAP for port in _CROSSOVER},
    },
    "notes": {"draws": "CP2102N active ~14 mA typ + RST 1k pull-up"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
