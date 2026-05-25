"""Hirose DM3AT-SF-PEJM5 - microSD push-push card socket.

Datasheet: Hirose DM3 series, latest
URL: https://www.hirose.com/en/product/document?clcode=CL0540-1284-2-51&productname=DM3AT-SF-PEJM5(51)&series=DM3
SDIO Reference: SD Card Specification Part 1 Physical Layer Specification

Push-push microSD socket with built-in card-detect switch. Interfaces
directly with the Zynq PS SDIO peripheral via SoM J1 pins (SDIO_D0..D3,
SDIO_CMD, SDIO_CLK).

Pin map (per Hirose DM3 catalog):
    1  DAT2
    2  DAT3 / CD (card detect)
    3  CMD
    4  VDD (3.3V supply)
    5  CLK
    6  VSS (GND)
    7  DAT0
    8  DAT1
    9  CD switch common
    10 CD switch normally-open
    SH SHIELD

SDIO 3.0 requires:
    - VDD pull-up by host (controlled by Zynq)
    - 10-100k pull-ups on DAT[0..3], CMD (controlled by host or external)
    - Card detect: pull-up + switch to GND when card inserted
"""

from __future__ import annotations

from scripts.carrier.refcircuits._paths import local_datasheet_path
from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


MICROSD_DM3AT_REFCIRCUIT = ReferenceCircuit(
    part_mpn="DM3AT-SF-PEJM5",
    lcsc="C114218",
    datasheet_url="https://www.hirose.com/en/product/document?clcode=CL0540-1284-2-51&productname=DM3AT-SF-PEJM5(51)&series=DM3",
    datasheet_revision="DM3 series, 2023",
    app_circuit_figure="SD Spec Part 1, Sec 4.5 - SD Bus Topology",
    local_datasheet_path=local_datasheet_path("DM3AT-SF-PEJM5"),
    app_circuit_page="SD Spec Part 1, Sec 4.5 - SD Bus Topology",
    minimum_circuit_verified=True,
    symbol_token="microSD_DM3AT",
    footprint="Connector_Card:microSD_HiroseDM3AT-SF-PEJM5_Push-Push",
    description="microSD push-push socket with card-detect switch",
    external_parts=(
        # VDD bulk decoupling
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="4u7_0402_X5R",
            justification="SD Spec Part 1 Sec 6.3: VDD bulk cap (>= 4.7uF for card insertion transients)",
        ),
        ExternalPart(
            from_pin="VDD",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="SD Spec: VDD HF bypass",
        ),
        # SDIO data pull-ups (SD Spec Sec 6.5 - 10-100k recommended)
        ExternalPart(
            from_pin="DAT0",
            to_net="VDD",
            part_token="10k_0402_1%",
            justification="SD Spec Sec 6.5: DAT0 pull-up 10-100k",
        ),
        ExternalPart(
            from_pin="DAT1",
            to_net="VDD",
            part_token="10k_0402_1%",
            justification="SD Spec Sec 6.5: DAT1 pull-up 10-100k",
        ),
        ExternalPart(
            from_pin="DAT2",
            to_net="VDD",
            part_token="10k_0402_1%",
            justification="SD Spec Sec 6.5: DAT2 pull-up 10-100k",
        ),
        ExternalPart(
            from_pin="DAT3_CD",
            to_net="VDD",
            part_token="10k_0402_1%",
            justification="SD Spec Sec 6.5: DAT3/CD pull-up",
        ),
        ExternalPart(
            from_pin="CMD",
            to_net="VDD",
            part_token="10k_0402_1%",
            justification="SD Spec Sec 6.5: CMD pull-up 10-100k",
        ),
        # Card-detect switch pull-up (pulled low when card inserted)
        ExternalPart(
            from_pin="CD_SW",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Card-detect to host GPIO via pull-up + switch to GND",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({"CLK"}),  # CLK is host-driven push-pull
    layout_notes=(
        LayoutNote(
            text="Route SDIO_CLK with matched length to SDIO_CMD and DAT[0..3] (length match within 5mm)",
            severity="rule",
            justification="SD Spec Sec 6.5 - SDIO timing margin",
        ),
        LayoutNote(
            text="Place series 22 ohm termination on each SDIO line near host SoM (already provided in SoM)",
            severity="info",
        ),
    ),
)
