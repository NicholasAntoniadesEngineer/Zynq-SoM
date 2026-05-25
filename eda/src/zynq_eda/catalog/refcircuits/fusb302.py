"""FUSB302BMPX - USB Type-C Port Controller with USB-PD CC negotiation.

Datasheet: ONsemi FUSB302B, Rev 6, May 2020
URL: https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf
Package: WQFN-14 (2.5x2.5mm, 0.5mm pitch)

Used as the USB-PD controller behind the STM32 USB-C connector. The FUSB302
handles CC1/CC2 termination, role detection (Rd 5.1k internal in sink mode),
and PD message framing. Host MCU (STM32G431 on the SoM) communicates over I2C.
"""

from __future__ import annotations

from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)
from zynq_eda.core.model.templates import IcBlockTemplate, PinGroup, PinGroupOffset
from zynq_eda.catalog.refcircuits._paths import local_datasheet_path


FUSB302_BLOCK_TEMPLATE = IcBlockTemplate(
    ic_anchor_offset=Point(0.0, 0.0),
    pin_group_offsets={
        PinGroup.DECOUPLING: PinGroupOffset(
            offset=Point(-15.24, -25.4),
            stride=Point(0.0, -12.7),
        ),
        PinGroup.SIGNAL_FILTER: PinGroupOffset(
            offset=Point(-15.24, 12.7),
            stride=Point(0.0, 12.7),
        ),
        PinGroup.BULK: PinGroupOffset(
            offset=Point(-15.24, 38.1),
            stride=Point(0.0, 12.7),
        ),
        PinGroup.PULL_UP: PinGroupOffset(
            offset=Point(38.1, -7.62),
            stride=Point(0.0, 12.7),
        ),
    },
)


FUSB302_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FUSB302BMPX",
    lcsc="C442699",
    datasheet_url="https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf",
    datasheet_revision="Rev 6, May 2020",
    app_circuit_figure="Figure 5 - Typical Application Schematic",
    local_datasheet_path=local_datasheet_path("FUSB302BMPX"),
    app_circuit_page="p.22, Figure 5",
    minimum_circuit_verified=True,
    symbol_token="FUSB302BMPX",
    footprint="Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm",
    description="USB Type-C / PD CC controller, I2C-controlled",
    supply_rail="+3V3",
    layout_template=FUSB302_BLOCK_TEMPLATE,
    pin_net_overrides=(
        ("CC1", "STM32_USB_CC1"),
        ("CC2", "STM32_USB_CC2"),
        ("VDD", "+3V3"),
        ("VBUS", "+VIN"),
        ("SDA", "STM32_I2C2_SDA"),
        ("SCL", "STM32_I2C2_SCL"),
        ("INT_N", "STM32_FUSB302_INT"),
    ),
    external_parts=(
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="DS 8.2.2 VDD bulk",
        ),
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS 8.2.2 VDD bypass",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 5 VBUS bypass",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="+VIN",
            part_token="1M_0402_1%",
            justification="DS Fig 5 VBUS sense divider upper leg (R1)",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100k_0402_1%",
            justification="DS Fig 5 VBUS sense divider lower leg (R2)",
        ),
        ExternalPart(
            from_pin="CC1",
            to_net="GND",
            part_token="200p_0402_C0G",
            justification="USB-PD cReceiver, DS Fig 5",
        ),
        ExternalPart(
            from_pin="CC2",
            to_net="GND",
            part_token="200p_0402_C0G",
            justification="USB-PD cReceiver, DS Fig 5",
        ),
        ExternalPart(
            from_pin="VCONN_1",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="Type-C VCONN bulk per EVB",
        ),
        ExternalPart(
            from_pin="VCONN_2",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="Type-C VCONN bulk per EVB",
        ),
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS 7.2 I2C pull-up",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3_SC",
            part_token="4k7_0402_1%",
            justification="DS 7.2 I2C pull-up",
        ),
        ExternalPart(
            from_pin="INT_N",
            to_net="+3V3_SC",
            part_token="10k_0402_1%",
            justification="DS 7.2 INT_N pull-up",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset(),
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
