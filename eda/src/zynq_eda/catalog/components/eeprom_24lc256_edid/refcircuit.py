"""24LC256T-I/SN configured as HDMI DDC EDID EEPROM.

Datasheet: Microchip 24AA256 / 24LC256 / 24FC256, DS21203P (2007)
URL: https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf
Package: SOIC-8 (3.9 x 4.9mm body, 1.27mm pitch)

Same silicon as the board-ID EEPROM (``components/eeprom_24lc256``) but
strapped for the HDMI DDC bus on the HDMI-TX port. Per HDMI 1.4 Sec 8.1.4
and the VESA E-DDC (Enhanced Display Data Channel) standard, the EDID
data ROM MUST respond to I2C device address 0xA0/0xA1 (7-bit 0x50),
which means A2 = A1 = A0 = 0 (24LC256 control code 1010 | 000 | R/W).

Power and bus levels:
    The HDMI 1.4 DDC bus is referenced to the cable +5V rail (HDMI 1.4
    Sec 8.1.1 specifies the DDC SCL/SDA logic levels at 5V CMOS). On
    this carrier the DDC lines are isolated from the system I2C bus by
    the TPD12S016 level shifter: cable-side SCL_B / SDA_B are 5V-
    referenced and pulled up internally by 1.75kohm to TPD12S016
    5V_OUT (TPD12S016 DS Sec 7.1). The EDID EEPROM therefore sits on
    the cable side of the TPD12S016, powered from the same +5V rail.

External-component count (DS Sec 2.0 + HDMI 1.4 Sec 8.1):

    * 100nF V_CC bypass to GND
    * No external SDA / SCL pull-ups: the TPD12S016 provides 1.75kohm
      internal pull-ups on SDA_B / SCL_B to 5V_OUT (DS Sec 7.1 + 7.3.15)
      which is the same node powering this EEPROM. Adding 2.2k externals
      would parallel down to ~970 ohm, well below the 1.6k HDMI 1.4
      minimum sink impedance.
    * A0 = A1 = A2 = 0 (mandatory for I2C addr 0x50 EDID)
    * WP = GND (allow Zynq PS to program EDID at first boot, then lock
      via firmware command if desired)

Slave address (HDMI 1.4 Sec 8.1.4 + VESA E-DDC Sec 2.2.5):
    EDID block 0 / 1: 0xA0 (write) / 0xA1 (read) -> 7-bit 0x50
    E-DDC segment ptr: 0x60 (write only)
"""

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
    datasheet_revision="DS21203P (2007)",
    app_circuit_figure="DS Sec 5.0 + HDMI 1.4 Sec 8.1.4 (EDID at 0xA0)",
    local_datasheet_path="components/eeprom_24lc256_edid/datasheet.pdf",
    app_circuit_page="p.8 Sec 5.0 Device Addressing + HDMI 1.4 EDID spec",
    minimum_circuit_verified=True,
    symbol_token="24LC256",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    description="256 Kbit I2C EDID EEPROM on HDMI DDC bus (5V, addr 0x50)",
    supply_rail="+5V",
    external_parts=(
        ExternalPart(
            from_pin="VCC",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 2.0: 100nF V_CC decoupling cap close to pin 8",
        ),
        # No external DDC pull-ups: TPD12S016 SDA_B/SCL_B have internal
        # 1.75kohm pull-ups to 5V_OUT (TPD12S016 DS Sec 7.1, 7.3.15).
    ),
    strap_pins=(
        StrapPin(
            pin="A0",
            tied_to="GND",
            purpose="A0 = 0 (mandatory for EDID I2C addr 0x50)",
            justification="HDMI 1.4 Sec 8.1.4 / VESA E-DDC Sec 2.2.5",
        ),
        StrapPin(
            pin="A1",
            tied_to="GND",
            purpose="A1 = 0",
            justification="HDMI 1.4 Sec 8.1.4 / VESA E-DDC Sec 2.2.5",
        ),
        StrapPin(
            pin="A2",
            tied_to="GND",
            purpose="A2 = 0 (full EDID address = 0xA0/0xA1)",
            justification="HDMI 1.4 Sec 8.1.4 / VESA E-DDC Sec 2.2.5",
        ),
        StrapPin(
            pin="WP",
            tied_to="GND",
            purpose="Write protect disabled (Zynq PS programs EDID at first boot)",
            justification="DS Sec 2.4: WP=GND -> writes enabled",
        ),
    ),
    no_external_required=frozenset({
        # SDA / SCL pull-ups are integrated in TPD12S016 (1.75k to 5V_OUT)
        "SDA", "SCL",
    }),
    layout_notes=(
        LayoutNote(
            text="Place EDID EEPROM on the HDMI cable side of TPD12S016, between "
                 "TPD12S016 SDA_B / SCL_B and HDMI connector pins 15 / 16",
            severity="rule",
            justification="HDMI 1.4 Sec 8.1 / TPD12S016 DS Fig 15",
        ),
        LayoutNote(
            text="Route DDC SDA / SCL traces <= 20mm with V_CC bypass within 5mm "
                 "of pin 8 to stay within HDMI 1.4 DDC capacitive-load budget",
            severity="rule",
            justification="HDMI 1.4 Sec 8.1.1 + DS Sec 2.0",
        ),
        LayoutNote(
            text="EDID EEPROM V_CC must come from the same +5V node that supplies "
                 "TPD12S016 5V_OUT (TX role) so DDC pull-ups and EEPROM share a "
                 "single 5V reference",
            severity="rule",
            justification="HDMI 1.4 Sec 8.1.1 (DDC voltage level)",
        ),
    ),
)
