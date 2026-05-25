"""40-pin 0.5mm LVDS LCD FFC connector with 100R differential termination."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


LVDS_LCD_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FPC-05F-40PH20",
    lcsc="C2856812",
    datasheet_url="https://datasheet.lcsc.com/lcsc/XUNPU-FPC-05F-40PH20_C2856812.pdf",
    datasheet_revision="2022",
    app_circuit_figure="LVDS panel termination (100 ohm differential)",
    local_datasheet_path="components/lvds_lcd/datasheet.pdf",
    app_circuit_page="LVDS IEEE 1596.3 + panel vendor ref",
    minimum_circuit_verified=True,
    symbol_token="FFC_40P_0.5mm",
    footprint="Connector_FFC-FPC:FPC-05F-40PH20",
    description="40-pin 0.5mm FFC for LVDS LCD panel",
    external_parts=(
        ExternalPart(
            from_pin="LVDS_CLK+",
            to_net="LVDS_CLK-",
            part_token="100R_0402_1%",
            justification="100 ohm LVDS clock pair termination at connector",
        ),
        ExternalPart(
            from_pin="LVDS_DATA0+",
            to_net="LVDS_DATA0-",
            part_token="100R_0402_1%",
            justification="100 ohm LVDS data0 pair termination",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Route LVDS pairs as 100 ohm differential, matched length",
            severity="rule",
        ),
    ),
)
