from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    UART_BRIDGE_RESET_PULL,
    UART_BRIDGE_SENSE_BOTTOM,
    UART_BRIDGE_SENSE_TOP,
    UART_BRIDGE_SUPPLY_BYPASS,
    UART_BRIDGE_VREGIN_BULK,
)

LCSC_BYPASS = "C14663"
LCSC_BULK = "C15850"
LCSC_RESET_PULL = "C21190"
LCSC_SENSE_TOP = "C25961"
LCSC_SENSE_BOTTOM = "C23061"

RAILS = ("+VDD_IO", "GND")
PORTS = ("USB_VBUS", "USB_DP", "USB_DM",
         "UART_TXD", "UART_RXD", "UART_RTS_N", "UART_CTS_N")
INTERFACE = RAILS + PORTS

# TP creation order IS the placer's TP1/TP2 order: it must survive a project's
# TXD<->RXD crossover bind, so the sequence is declared, never incidental.
TESTPOINT_ORDER = ("UART_RXD", "UART_TXD")

DRAWS_NOTE = "CP2102N active ~14 mA typ + RST 1k pull-up"
DRAWS_A = 0.015
RESET_WAIVER = "open-drain RST: 1k pull-up only, internal POR; no RC cap"


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("uart_bridge", "UART bridge: CP2102N USB-UART")
    c.use_part("CP2102N-A02-GQFN24R", ref="U1", value="CP2102N-A02")

    c.net("+VDD_IO", "U1.5", "U1.6", "U1.7")
    c.net("GND", "U1.2", "U1.25")
    for cap, lcsc in zip(c.decouple("U1.7", UART_BRIDGE_SUPPLY_BYPASS,
                                    UART_BRIDGE_VREGIN_BULK),
                         (LCSC_BYPASS, LCSC_BULK), strict=True):
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.6", UART_BRIDGE_SUPPLY_BYPASS):
        cap.fields["LCSC"] = LCSC_BYPASS
    for cap in c.decouple("U1.5", UART_BRIDGE_SUPPLY_BYPASS):
        cap.fields["LCSC"] = LCSC_BYPASS

    c.net("CP2102N_RST_N", "U1.9")
    c.pullup("U1.9", UART_BRIDGE_RESET_PULL,
             "+VDD_IO").fields["LCSC"] = LCSC_RESET_PULL

    # USB_VBUS is the receptacle's OWN 5 V: a board VIN is 20 V post-PD and
    # this divider would then put 13.6 V on a 5.8 V abs-max pin.
    c.port("USB_VBUS", **meta.expect_kw("USB_VBUS"))
    c.net("CP2102N_VBUS_SNS", "U1.8")
    c.series("USB_VBUS", "CP2102N_VBUS_SNS", UART_BRIDGE_SENSE_TOP) \
        .fields["LCSC"] = LCSC_SENSE_TOP
    c.series("CP2102N_VBUS_SNS", "GND", UART_BRIDGE_SENSE_BOTTOM) \
        .fields["LCSC"] = LCSC_SENSE_BOTTOM

    c.port("USB_DP", "U1.3")
    c.port("USB_DM", "U1.4")
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM",
                expect=meta.expects.get("USB_DP"))

    c.port("UART_TXD", "U1.21", **meta.expect_kw("UART_TXD"))
    c.port("UART_RXD", "U1.20", **meta.expect_kw("UART_RXD"))
    c.port("UART_RTS_N", "U1.19", **meta.expect_kw("UART_RTS_N"))
    c.port("UART_CTS_N", "U1.18", **meta.expect_kw("UART_CTS_N"))

    c.nc("U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15",
         "U1.16", "U1.17", "U1.22", "U1.23", "U1.24")

    for net in TESTPOINT_ORDER:
        c.testpoint(net)

    c.draws("+VDD_IO", DRAWS_A, draws_note)
    c.waive_reset("CP2102N_RST_N", RESET_WAIVER)

    return meta.finish(c)
