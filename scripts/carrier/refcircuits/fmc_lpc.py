"""Hirose FX10A FMC LPC connector decoupling."""

from __future__ import annotations

from scripts.carrier.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit
from scripts.carrier.refcircuits._paths import local_datasheet_path


FMC_LPC_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FX10A-168P-SV(91)",
    lcsc="C6624664",
    datasheet_url=(
        "https://www.hirose.com/en/product/document?"
        "clcode=CL0681-2024-7-91&productname=FX10A-168P-SV(91)&series=FX10A"
    ),
    datasheet_revision="Hirose FX10A series",
    app_circuit_figure="FMC LPC VITA 57.1 decoupling guidance",
    local_datasheet_path=local_datasheet_path("FX10A-168P-SV(91)"),
    app_circuit_page="Hirose FX10A DS + VITA 57.1 Sec 5.3",
    minimum_circuit_verified=True,
    symbol_token="FMC_LPC_168P",
    footprint="Connector_FFC-FPC:FX10A-168P-SV1",
    description="168-pin FMC LPC mezzanine connector",
    supply_rail="+3V3",
    external_parts=(
        ExternalPart(
            from_pin="VCC_3V3",
            to_net="GND",
            part_token="100n_0402_X7R",
            quantity=4,
            justification="VITA 57.1: 100nF per VCC pin group on FMC connector",
        ),
        ExternalPart(
            from_pin="VCC_3V3",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="FMC bulk decoupling at connector",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Decouple each FMC VCC pin group within 3mm of connector",
            severity="rule",
            justification="VITA 57.1 LPC carrier requirements",
        ),
    ),
)
