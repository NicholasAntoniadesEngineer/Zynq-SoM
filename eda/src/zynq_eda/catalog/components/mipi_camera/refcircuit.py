"""15-pin 1mm MIPI CSI-2 FFC connector passives."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


MIPI_CAMERA_REFCIRCUIT = ReferenceCircuit(
    part_mpn="1.0-15P",
    lcsc="C66660",
    datasheet_url="https://datasheet.lcsc.com/lcsc/BOOMELE-1-0-15P_C66660.pdf",
    datasheet_revision="2021",
    app_circuit_figure="MIPI CSI-2 D-PHY connector decoupling",
    local_datasheet_path="components/mipi_camera/datasheet.pdf",
    app_circuit_page="CSI-2 spec + FFC vendor DS",
    minimum_circuit_verified=True,
    symbol_token="FFC_15P_1mm",
    footprint="Connector_FFC-FPC:FFC_15P_1mm",
    description="15-pin 1mm FFC for MIPI CSI-2 camera module",
    supply_rail="+1V8",
    external_parts=(
        ExternalPart(
            from_pin="VCC_1V8",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="CSI-2 I/O supply bypass at FFC",
        ),
        ExternalPart(
            from_pin="VCC_2V8",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="Camera analog supply bypass at FFC",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Keep CSI-2 pairs length-matched; 100 ohm differential routing",
            severity="rule",
        ),
    ),
)
