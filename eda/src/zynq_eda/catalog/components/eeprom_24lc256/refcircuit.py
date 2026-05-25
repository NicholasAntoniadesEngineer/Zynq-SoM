"""24LC256T-I/SN - 256 Kbit I2C Serial EEPROM.

Datasheet: Microchip 24AA256/24LC256/24FC256, Rev May 2020
URL: https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf
Package: SOIC-8 (3.9x4.9mm)

Used in two roles on the carrier:
    1. Board ID / persistent config storage (I2C bus shared with INA226/RTC)
    2. HDMI DDC EEPROM holding EDID for the HDMI TX port (5V level, separate bus)

Pin map (per datasheet):
    1  A0    - I2C address bit 0 (strap)
    2  A1    - I2C address bit 1 (strap)
    3  A2    - I2C address bit 2 (strap)
    4  VSS   - GND
    5  SDA   - I2C data (open-drain)
    6  SCL   - I2C clock
    7  WP    - Write protect (active high)
    8  VCC   - 1.7-5.5V supply

Default I2C address: 1010_xxx_w where xxx = A2:A1:A0 -> 0x50..0x57
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
    StrapPin,
)


EEPROM_24LC256_REFCIRCUIT = ReferenceCircuit(
    part_mpn="24LC256T-I/SN",
    lcsc="C5458",
    datasheet_url="https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf",
    datasheet_revision="Rev May 2020 (DS21203P)",
    app_circuit_figure="Figure 4-1 - Typical Application Circuit",
    local_datasheet_path="components/eeprom_24lc256/datasheet.pdf",
    app_circuit_page="Figure 4-1 - Typical Application Circuit",
    minimum_circuit_verified=True,
    symbol_token="24LC256",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    description="256 Kbit I2C Serial EEPROM, SOIC-8",
    external_parts=(
        ExternalPart(
            from_pin="VCC",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 2.0 Electrical Characteristics: VCC decoupling cap",
        ),
        # I2C pull-ups (shared with other devices on the bus)
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec 4.2: I2C SDA pull-up (one per bus)",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec 4.2: I2C SCL pull-up (one per bus)",
        ),
    ),
    strap_pins=(
        StrapPin(
            pin="A0",
            tied_to="GND",
            purpose="I2C address bit 0 = 0",
            justification="DS Sec 5.1 Slave Address",
        ),
        StrapPin(
            pin="A1",
            tied_to="GND",
            purpose="I2C address bit 1 = 0",
            justification="DS Sec 5.1 Slave Address",
        ),
        StrapPin(
            pin="A2",
            tied_to="GND",
            purpose="I2C address bit 2 = 0 (default address 0x50)",
            justification="DS Sec 5.1 Slave Address",
        ),
        StrapPin(
            pin="WP",
            tied_to="GND",
            purpose="Write protect disabled (write-enabled)",
            justification="DS Sec 7.0 Write Protection",
        ),
    ),
    no_external_required=frozenset(),
    layout_notes=(
        LayoutNote(
            text="Keep VCC decoupling within 5mm of pin 8",
            severity="rule",
        ),
    ),
)
