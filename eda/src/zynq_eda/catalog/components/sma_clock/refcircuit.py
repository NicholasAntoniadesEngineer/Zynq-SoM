"""SMA clock input with AC coupling and 50R termination."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


SMA_CLOCK_REFCIRCUIT = ReferenceCircuit(
    part_mpn="KH-SMA-P-8496",
    lcsc="C910123",
    datasheet_url="https://datasheet.lcsc.com/lcsc/kinghelm-KH-SMA-P-8496_C910123.pdf",
    datasheet_revision="2021",
    app_circuit_figure="XADC external clock input (UG480)",
    local_datasheet_path="components/sma_clock/datasheet.pdf",
    app_circuit_page="UG480 XADC: AC-couple external clock with 50R termination",
    minimum_circuit_verified=True,
    symbol_token="SMA_RA_TH",
    footprint="Connector_Coaxial:SMA_Amphenol_132289-14_Vertical",
    description="SMA right-angle clock input for XADC/MRCC",
    external_parts=(
        ExternalPart(
            from_pin="CENTER",
            to_net="XADC_CLK",
            part_token="22p_0402_C0G",
            justification="UG480: AC coupling cap on external clock input",
        ),
        ExternalPart(
            from_pin="XADC_CLK",
            to_net="GND",
            part_token="49R9_0402_1%",
            justification="50 ohm termination to GND at XADC clock input",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Route SMA to XADC as 50 ohm controlled impedance",
            severity="rule",
        ),
    ),
)
