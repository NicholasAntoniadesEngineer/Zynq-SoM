"""CP2102N-A02-GQFN24R - USB to UART bridge.

Datasheet: Silicon Labs CP2102N, Rev 1.5, 2021
URL: https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf
Package: QFN-24 (4x4mm, 0.5mm pitch)

Provides a USB-to-UART bridge for the host PC to talk to the Zynq PS UART
console. Powered from USB VBUS or external 3.3V; integrated 3.3V regulator
and internal crystal-less oscillator (no external crystal needed).

Pin map (per datasheet Table 4.1):
    1  DCD_N
    2  RI_N
    3  GND
    4  D+              <- USB data
    5  D-              <- USB data
    6  VDD             <- 3.3V supply
    7  REGIN           <- regulator input (tie to VDD for self-power)
    8  VBUS            <- USB VBUS (5V detect)
    9  RST_N           <- reset (pull-up to VDD)
    10 NC
    11 CHREN
    12 SUSPEND
    13 SUSPEND_N
    14 NC
    15 GPIO3
    16 GPIO2
    17 GPIO1
    18 GPIO0
    19 RXD             <- UART receive (from external TX)
    20 TXD             <- UART transmit (to external RX)
    21 RTS_N
    22 CTS_N
    23 DSR_N
    24 DTR_N
    EP GND (exposed pad)
"""

from __future__ import annotations

from scripts.carrier.refcircuits._paths import local_datasheet_path
from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


CP2102N_REFCIRCUIT = ReferenceCircuit(
    part_mpn="CP2102N-A02-GQFN24R",
    lcsc="C969151",
    datasheet_url="https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf",
    datasheet_revision="Rev 1.5, 2021",
    app_circuit_figure="Figure 4-1 - Typical USB to UART Bridge",
    local_datasheet_path=local_datasheet_path("CP2102N-A02-GQFN24R"),
    app_circuit_page="Figure 4-1 - Typical USB to UART Bridge",
    minimum_circuit_verified=True,
    symbol_token="CP2102N",
    footprint="Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    description="USB to UART bridge, USB 2.0 FS, internal regulator and oscillator",
    external_parts=(
        # VBUS sense - 100nF + connected to USB-C VBUS via series resistor optional
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 4.4: VBUS decoupling cap",
        ),
        # VDD bulk + bypass (self-powered from VBUS via internal regulator)
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="4u7_0402_X5R",
            justification="DS Fig 4-1: 4.7uF VDD bulk cap (recommended for USB compliance)",
        ),
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 4-1: 100nF VDD high-frequency bypass",
        ),
        # REGIN bypass (regulator input from VBUS internally)
        ExternalPart(
            from_pin="REGIN",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="DS Sec 4.3: REGIN bypass cap when using internal regulator",
        ),
        # RST_N pull-up (DS recommends external R + C for reliable startup)
        ExternalPart(
            from_pin="RST_N",
            to_net="VDD",
            part_token="10k_0402_1%",
            justification="DS Sec 4.5: RST_N requires pull-up to VDD",
        ),
        ExternalPart(
            from_pin="RST_N",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 4.5: 100nF RST_N filter to GND for noise immunity",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "D+", "D-",  # No external pull-ups (CP2102N has internal pull-up)
        "TXD", "RXD",  # Logic-level outputs, no termination needed
    }),
    layout_notes=(
        LayoutNote(
            text="Place D+/D- matched length to USB-C connector, 90 ohm differential impedance",
            severity="rule",
            justification="USB 2.0 Sec 7.1.6",
        ),
        LayoutNote(
            text="Connect exposed pad (EP) to GND plane with multiple vias for thermal dissipation",
            severity="rule",
            justification="DS Sec 11.1 Layout",
        ),
    ),
)
