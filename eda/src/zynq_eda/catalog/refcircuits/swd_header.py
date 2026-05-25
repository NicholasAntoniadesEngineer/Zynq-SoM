"""2x5 1.27mm ARM SWD debug header."""

from __future__ import annotations

from scripts.carrier.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit
from scripts.carrier.refcircuits._paths import local_datasheet_path


SWD_HEADER_REFCIRCUIT = ReferenceCircuit(
    part_mpn="HX-PZ1.27-2x5P-TP",
    lcsc="C41376037",
    datasheet_url="https://datasheet.lcsc.com/lcsc/hanxia-HX-PZ1-27-2x5P-TP_C41376037.pdf",
    datasheet_revision="2022",
    app_circuit_figure="ARM Debug Interface v5.2",
    local_datasheet_path=local_datasheet_path("HX-PZ1.27-2x5P-TP"),
    app_circuit_page="ARM SWD: 10k pull-up on SWDIO, 10k on nRESET",
    minimum_circuit_verified=True,
    symbol_token="SWD_2x5",
    footprint="Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
    description="2x5 1.27mm SWD + UART debug header",
    supply_rail="+3V3",
    external_parts=(
        ExternalPart(
            from_pin="SWDIO",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="ARM SWD: SWDIO pull-up to VCC",
        ),
        ExternalPart(
            from_pin="nRESET",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="ARM SWD: nRESET pull-up to VCC",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Place 10k pull-ups within 10mm of SWD header",
            severity="rule",
        ),
    ),
)
