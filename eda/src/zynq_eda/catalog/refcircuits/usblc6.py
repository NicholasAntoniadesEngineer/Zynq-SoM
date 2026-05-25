"""USBLC6-4SC6 - 4-line USB 2.0 ESD protection.

Datasheet: STMicroelectronics USBLC6-2, USBLC6-4, Rev 11, Mar 2024
URL: https://www.st.com/resource/en/datasheet/usblc6-4.pdf
Package: SOT-23-6L

USBLC6-4SC6 protects 4 single-ended data lines (e.g. USB D+/D- on two
ports OR a single USB 2.0 HS pair plus two general-purpose lines).
For this design we use it on USB 2.0 D+/D- on each USB-C port.

Pin map (per datasheet Sec 1):
    1  I/O1 (D+ side 1)
    2  GND
    3  VBUS (5V supply reference for clamping)
    4  I/O2 (D- side 1)
    5  I/O3 (D+ side 2 - unused if only one USB)
    6  I/O4 (D- side 2 - unused if only one USB)

We are protecting a single USB 2.0 HS pair per IC instance, so we use:
    Pin 1 (I/O1) <- USB D+ from connector
    Pin 4 (I/O2) <- USB D- from connector
    Pins 5/6     <- NC (or used for SBU1/SBU2 protection)
"""

from __future__ import annotations

from scripts.carrier.refcircuits._paths import local_datasheet_path
from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


USBLC6_REFCIRCUIT = ReferenceCircuit(
    part_mpn="USBLC6-4SC6",
    lcsc="C111212",
    datasheet_url="https://www.st.com/resource/en/datasheet/usblc6-4.pdf",
    datasheet_revision="Rev 11, Mar 2024",
    app_circuit_figure="Figure 1 - Pin connection / Figure 13 - Application",
    local_datasheet_path=local_datasheet_path("USBLC6-4SC6"),
    app_circuit_page="Figure 1 - Pin connection / Figure 13 - Application",
    minimum_circuit_verified=True,
    symbol_token="USBLC6-4SC6",
    footprint="Package_TO_SOT_SMD:SOT-23-6",
    description="USB 2.0 ESD/TVS protection, 4 lines, SOT-23-6",
    external_parts=(
        # VBUS (pin 3) needs decoupling and is the supply rail reference
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 13: VBUS decoupling cap",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "I/O1", "I/O2", "I/O3", "I/O4",  # data lines pass through, no R/C
    }),
    layout_notes=(
        LayoutNote(
            text="Place USBLC6 within 5mm of the USB connector pins to minimize stub length",
            severity="rule",
            justification="DS Sec 4 Layout - protection must precede device",
        ),
        LayoutNote(
            text="Route USB D+/D- as 90 ohm differential pair with length match within 5mm",
            severity="rule",
            justification="USB 2.0 spec Sec 7.1.6",
        ),
    ),
)
