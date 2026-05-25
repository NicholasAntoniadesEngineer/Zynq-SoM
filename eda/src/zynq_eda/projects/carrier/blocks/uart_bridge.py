"""Carrier UART bridge block: CP2102N USB-to-UART debug console for the Zynq PS.

A dedicated micro-USB-B receptacle wired to a Silicon Labs CP2102N-A02-GQFN24
USB-to-UART bridge, exposing the Zynq PS UART0 console to a host PC.

  * J1 = micro-USB-B receptacle (Connector:USB_B_Micro from the KiCad stock
    library — the zynq_eda library does not currently provide its own
    micro-USB-B symbol). VBUS from the cable is the block's +VIN supply
    (CP2102N is self-powered via its internal 3.3 V regulator: REGIN tied
    to VBUS, VDD as the regulated rail).
  * U1 = CP2102N-A02-GQFN24R, configured per DS Fig 4-1: REGIN/VDD bulk
    + bypass caps, RST_N pull-up + filter cap. D+/D- run straight to the
    USB receptacle (no series resistors required; integrated termination).
  * UART0 RXD/TXD/RTS_N/CTS_N expose the bridge to the Zynq PS UART0
    peripheral, with hardware flow control.

The CP2102N supplies its own internal oscillator so no crystal is needed;
the only external parts are decoupling and the reset network.
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    ConnectorInstance,
    ExternalNet,
    GroundNet,
    IcInstance,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_uart_bridge() -> Block:
    """Return the UART bridge block (CP2102N + micro-USB)."""
    return Block(
        name="uart_bridge",
        title="USB-UART Bridge (CP2102N → Zynq PS UART0)",
        paper_size="A4",
        description=(
            "Silicon Labs CP2102N-A02-GQFN24R USB-to-UART bridge for the "
            "Zynq PS UART0 debug console. Self-powered from a dedicated "
            "micro-USB-B receptacle via its internal 3.3 V regulator "
            "(REGIN = VBUS). D+/D- run direct from the receptacle to the "
            "CP2102N; UART RXD/TXD with hardware flow control (RTS_N/CTS_N) "
            "to the Zynq PS."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["CP2102N-A02-GQFN24R"],
                lib_id="Interface_USB:CP2102N-Axx-xQFN24",
                # CP2102N is self-powered from the cable VBUS; tie its
                # regulator input (REGIN) and VBUS-sense pin to +VIN.
                power_input_net="+VIN",
            ),
        ),
        connectors=(
            ConnectorInstance(
                reference="J1",
                # The zynq_eda library doesn't yet have a micro-USB connector
                # refcircuit; reuse USBC_SINK as a stand-in for the BOM /
                # external-parts hookup (VBUS decoupling + shield discharge are
                # equally applicable for any USB-2.0 receptacle). The pin map
                # below is what actually defines the per-pin connectivity.
                refcircuit=REFCIRCUITS["USBC_SINK"],
                lib_id="Connector:USB_B_Micro",
                edge=SheetEdge.RIGHT,
                pin_to_net=(
                    ("1", "+VIN"),               # VBUS  (cable power → CP2102N REGIN)
                    ("2", "USB_UART_DM"),        # D-
                    ("3", "USB_UART_DP"),        # D+
                    ("4", "USB_UART_ID"),        # ID (unused, optional pull-down)
                    ("5", "GND"),                # GND
                    ("SH", "CHASSIS_GND"),       # Shield → chassis (1M + 100nF)
                ),
            ),
        ),
        external_nets=(
            # +VIN here is the micro-USB cable VBUS, the block's only power
            # source. GND is signal ground (chassis is decoupled via 1M+100nF).
            PowerInputNet("+VIN", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            # UART0 lines to the Zynq PS. Direction is from the BLOCK's POV:
            #   - RXD: block receives (input) chars that came from the Zynq TX
            #         pin... actually the Zynq's RXD is the Zynq's input. The
            #         spec assigns RXD = input and TXD = output, matching the
            #         net naming convention (a net called *_RXD always lands
            #         on the Zynq's RXD pin, so this block, sitting opposite
            #         the Zynq, drives RXD outward via its TXD pin). We
            #         follow the spec's net-direction labels verbatim.
            SignalNet("ZYNQ_PS_UART0_RXD",   direction="input",  edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_UART0_TXD",   direction="output", edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_UART0_RTS_N", direction="input",  edge=SheetEdge.LEFT),
            SignalNet("ZYNQ_PS_UART0_CTS_N", direction="output", edge=SheetEdge.LEFT),
            # Chassis ground (decoupled from signal GND through 1M + 100nF).
            ExternalNet(
                name="CHASSIS_GND",
                direction="passive",
                edge=SheetEdge.LEFT,
                power_kind="ground",
            ),
        ),
    )
