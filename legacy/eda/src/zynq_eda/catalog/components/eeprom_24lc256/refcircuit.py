"""24LC256T-I/SN - 256-Kbit I2C CMOS Serial EEPROM.

Datasheet: Microchip 24AA256 / 24LC256 / 24FC256, DS21203P (2007)
URL: https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf
Package: SOIC-8 (3.9 x 4.9mm body, 1.27mm pitch)

A small I2C EEPROM used as a board-identity / persistent-config store on
the +3V3 system I2C bus that also carries the INA226 power monitors and
the DS3231 RTC. The EDID variant of the same silicon lives in a sibling
folder (``eeprom_24lc256_edid``) - it is configured for the HDMI DDC bus
at +5V with a hard-wired I2C address of 0x50 per the HDMI 1.4 EDID spec.

Pin map (8-pin SOIC, DS Table 2-1):

    1  A0    Chip-select address bit 0 (strap)
    2  A1    Chip-select address bit 1 (strap)
    3  A2    Chip-select address bit 2 (strap)
    4  V_SS  Ground
    5  SDA   I2C serial data (open-drain, needs bus pull-up)
    6  SCL   I2C serial clock (open-drain, needs bus pull-up)
    7  WP    Write protect (HIGH = read-only, LOW = read/write)
    8  V_CC  +2.5V .. +5.5V supply (24LC256 grade); board uses +3V3

I2C device address (DS Sec 5):
    Control code 1010 | A2 A1 A0 | R/W
    With A2 = A1 = A0 = 0 -> 7-bit addr 0x50 (write 0xA0, read 0xA1).
    Up to eight 24LC256 devices may share a bus via different A[2:0] straps.

External-component count (DS Sec 2.2 + Fig 4-1 typical application):

    * 100nF V_CC bypass to GND
    * One SDA pull-up and one SCL pull-up to V_CC per bus (typical
      10k @ 100kHz, 2k @ 400kHz) - these may be shared with other I2C
      devices on the same bus, so the carrier-level block decides whose
      refcircuit owns the pull-ups. We declare 4.7k here as the 'first
      come, first served' fallback at +3V3 / 400kHz.
    * Strap A0/A1/A2 + WP to GND or V_CC depending on role.

Strap selection on this carrier (board-ID role):
    A2 = A1 = A0 = 0  -> I2C address 0x50
    WP = GND          -> write-enabled (factory-programmable from Zynq PS)
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
    datasheet_revision="DS21203P (2007)",
    app_circuit_figure="DS Sec 2.0 Electrical Characteristics + Sec 5 Device Addressing",
    local_datasheet_path="components/eeprom_24lc256/datasheet.pdf",
    app_circuit_page="p.2 Sec 2.0 + p.5 Sec 2.2 + p.8 Sec 5.0",
    minimum_circuit_verified=True,
    symbol_token="24LC256",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    description="256 Kbit I2C EEPROM (board-ID role on +3V3 system bus)",
    supply_rail="+3V3",
    external_parts=(
        ExternalPart(
            from_pin="VCC",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 2.0 / 8.0: 100nF V_CC decoupling cap close to pin 8",
        ),
        # Bus pull-ups - one set per I2C bus. The board-level pmod / power-mon
        # block may share an existing pull-up; if no other device owns it the
        # EEPROM contributes 4.7k @ +3V3 for 400kHz operation (DS Sec 2.2).
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec 2.2: SDA bus pull-up (~2k for 400kHz, ~10k "
                          "for 100kHz; 4.7k is a safe compromise at 3.3V)",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec 2.2: SCL bus pull-up matched to SDA",
        ),
    ),
    strap_pins=(
        StrapPin(
            pin="A0",
            tied_to="GND",
            purpose="A0 = 0 (LSB of chip-select address)",
            justification="DS Sec 2.1 + Sec 5.0: address 1010_000 = 0x50",
        ),
        StrapPin(
            pin="A1",
            tied_to="GND",
            purpose="A1 = 0",
            justification="DS Sec 2.1 + Sec 5.0",
        ),
        StrapPin(
            pin="A2",
            tied_to="GND",
            purpose="A2 = 0 (board-ID role at I2C 0x50)",
            justification="DS Sec 2.1 + Sec 5.0",
        ),
        StrapPin(
            pin="WP",
            tied_to="GND",
            purpose="Write protect disabled (Zynq PS may program board ID)",
            justification="DS Sec 2.4: WP=GND -> write operations enabled",
        ),
    ),
    no_external_required=frozenset(),
    layout_notes=(
        LayoutNote(
            text="Place 100nF V_CC decoupling within 5mm of pin 8",
            severity="rule",
            justification="DS Sec 2.0 - minimise supply-noise injection on internal HV programming pump",
        ),
        LayoutNote(
            text="Keep SDA / SCL traces <= 100mm to stay within the 400pF total "
                 "bus capacitance limit of the I2C-bus specification",
            severity="guideline",
            justification="I2C-bus specification UM10204 Sec 3.1.9",
        ),
    ),
)
