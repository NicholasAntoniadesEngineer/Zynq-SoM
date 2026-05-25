"""24LC256 configured as HDMI DDC EDID EEPROM."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
    StrapPin,
)


EEPROM_24LC256_EDID_REFCIRCUIT = ReferenceCircuit(
    part_mpn="24LC256T-I/SN",
    lcsc="C5458",
    datasheet_url="https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf",
    datasheet_revision="Rev May 2020 (DS21203P)",
    app_circuit_figure="Figure 4-1 + HDMI DDC EDID wiring",
    local_datasheet_path="components/eeprom_24lc256_edid/datasheet.pdf",
    app_circuit_page="DS21203P Fig 4-1 + HDMI DDC at +5V",
    minimum_circuit_verified=True,
    symbol_token="24LC256",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    description="256 Kbit I2C EDID EEPROM on HDMI DDC bus",
    supply_rail="+5V",
    external_parts=(
        ExternalPart(
            from_pin="VCC",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 2.0: VCC decoupling cap",
        ),
        ExternalPart(
            from_pin="SDA",
            to_net="+5V",
            part_token="2k2_0402_1%",
            justification="HDMI DDC SDA pull-up to +5V (shared with connector)",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+5V",
            part_token="2k2_0402_1%",
            justification="HDMI DDC SCL pull-up to +5V (shared with connector)",
        ),
    ),
    strap_pins=(
        StrapPin(
            pin="A0",
            tied_to="GND",
            purpose="EDID I2C address bit 0 = 0",
            justification="DS Sec 5.1",
        ),
        StrapPin(
            pin="A1",
            tied_to="+5V",
            purpose="EDID I2C address bit 1 = 1 (address 0x54)",
            justification="HDMI EDID typical address 0xA0/0xA1",
        ),
        StrapPin(
            pin="A2",
            tied_to="GND",
            purpose="EDID I2C address bit 2 = 0",
            justification="DS Sec 5.1",
        ),
        StrapPin(
            pin="WP",
            tied_to="GND",
            purpose="Write protect disabled for EDID programming",
            justification="DS Sec 7.0",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Route DDC SDA/SCL to HDMI connector within 20mm",
            severity="rule",
        ),
    ),
)
