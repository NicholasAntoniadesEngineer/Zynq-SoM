"""FUSB302BMPX - USB Type-C Port Controller with USB-PD CC negotiation.

Datasheet: ONsemi FUSB302B, Rev 6, May 2020
URL: https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf
Package: WQFN-14 (2.5x2.5mm, 0.5mm pitch)

Used as the USB-PD controller behind the STM32 USB-C connector. The FUSB302
handles CC1/CC2 termination, role detection (Rd 5.1k internal in sink mode),
and PD message framing. Host MCU (STM32G431 on the SoM) communicates over I2C.

Pin map (per datasheet Table 1):
    1  VBUS    - VBUS sense
    2  GND     - Ground
    3  VDD     - 3.3V supply
    4  CC1     - USB-C CC1 (Rd/Rp internal)
    5  CC2     - USB-C CC2
    6  VCONN_1 - VCONN switch output (cable powering)
    7  VCONN_2 - VCONN switch output (alternate orientation)
    8  SDA     - I2C data
    9  SCL     - I2C clock
    10 INT_N   - Interrupt out (open-drain)
    11 GND
    12 GND
    13 GND
    14 GND_EP  - Exposed pad
"""

from __future__ import annotations

from scripts.carrier.core.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


FUSB302_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FUSB302BMPX",
    lcsc="C442699",
    datasheet_url="https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf",
    datasheet_revision="Rev 6, May 2020",
    app_circuit_figure="Figure 5 - Typical Application Schematic",
    symbol_token="FUSB302BMPX",
    footprint="Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm",
    description="USB Type-C / PD CC controller, I2C-controlled",
    external_parts=(
        # VDD: 1uF bulk + 100nF bypass (Sec 8.2.2)
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="DS Sec 8.2.2: 1uF VDD bulk decoupling, place within 5mm",
        ),
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 8.2.2: 100nF high-frequency VDD bypass",
        ),
        # VBUS sense via divider (Fig 5) - 100k upper, NOT used as power
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 5: VBUS local bypass",
        ),
        # I2C: 4.7k pull-ups to host VIO (+3V3_SC on this design)
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS Sec 7.2 I2C SDA pull-up to host VIO; one per bus",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS Sec 7.2 I2C SCL pull-up to host VIO; one per bus",
        ),
        # INT_N: open-drain output, pull-up to host VIO
        ExternalPart(
            from_pin="INT_N",
            to_net="+3V3_SC",
            part_token="10k_0402_1%",
            justification="DS Sec 7.2: INT_N is open-drain, requires pull-up to host VIO",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "CC1",  # Internal Rd/Rp termination per Sec 7.1
        "CC2",
        "VCONN_1",  # VCONN output, no external cap when in sink-only (VCONN sourcing disabled)
        "VCONN_2",
    }),
    layout_notes=(
        LayoutNote(
            text="Place 1uF VDD cap within 5mm of pin 3; star-ground EP to PCB GND plane",
            severity="rule",
            justification="DS Sec 10.2 Layout",
        ),
        LayoutNote(
            text="CC1/CC2 traces: 90 ohm differential impedance, matched length within 5mm",
            severity="rule",
            justification="USB-C R2.0 Sec 3.2.1",
        ),
        LayoutNote(
            text="VBUS trace from USB-C connector to FUSB302 VBUS pin: keep <= 10mm",
            severity="guideline",
            justification="Minimize VBUS sense latency",
        ),
    ),
)
