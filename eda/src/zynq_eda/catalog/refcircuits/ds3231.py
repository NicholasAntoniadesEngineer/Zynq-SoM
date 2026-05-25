"""DS3231SN# - Extremely Accurate I2C-Integrated RTC/TCXO.

Datasheet: Analog Devices (Maxim) DS3231, Rev 10, 2015
URL: https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231.pdf
Package: SOIC-16W (300 mil)

Provides battery-backed real-time clock with internal TCXO (no external
crystal required). 32.768 kHz square-wave output and INT/SQW alarm.
Backup via CR2032 lithium cell.

Pin map (per datasheet):
    1  32kHz   - 32.768 kHz output (open drain) - optional
    2  VCC     - Main supply (2.3-5.5V)
    3  INT/SQW - Interrupt or 1Hz square wave output (open drain)
    4  RST_N   - Reset / power-fail indicator (open drain)
    5-12 NC    - Internal use; should be GND
    13 GND
    14 VBAT    - Backup battery input (~3V)
    15 SDA     - I2C data
    16 SCL     - I2C clock
"""

from __future__ import annotations

from scripts.carrier.refcircuits._paths import local_datasheet_path
from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


DS3231_REFCIRCUIT = ReferenceCircuit(
    part_mpn="DS3231SN#",
    lcsc="C722469",
    datasheet_url="https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231.pdf",
    datasheet_revision="Rev 10, 2015",
    app_circuit_figure="Figure 1 - Typical Operating Circuit",
    local_datasheet_path=local_datasheet_path("DS3231SN#"),
    app_circuit_page="Figure 1 - Typical Operating Circuit",
    minimum_circuit_verified=True,
    symbol_token="DS3231SN",
    footprint="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
    description="Accurate I2C RTC with internal TCXO, battery backup, SOIC-16W",
    external_parts=(
        # VCC bulk decoupling
        ExternalPart(
            from_pin="VCC",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 1: 100nF VCC decoupling",
        ),
        # VBAT decoupling (backup battery input)
        ExternalPart(
            from_pin="VBAT",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 1: 100nF VBAT decoupling for noise immunity",
        ),
        # I2C pull-ups (shared bus)
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec Electrical Characteristics: I2C pull-up (one per bus)",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec Electrical Characteristics: I2C pull-up (one per bus)",
        ),
        # RST_N pull-up (open-drain)
        ExternalPart(
            from_pin="RST_N",
            to_net="VCC",
            part_token="10k_0402_1%",
            justification="DS Sec Power Control: RST_N is open-drain, requires pull-up",
        ),
        # 32kHz output pull-up (if used; open-drain)
        ExternalPart(
            from_pin="32kHz",
            to_net="VCC",
            part_token="10k_0402_1%",
            justification="DS Sec 32kHz Output: open-drain pull-up if 32kHz used",
        ),
        # INT_SQW pull-up (open-drain)
        ExternalPart(
            from_pin="INT_SQW",
            to_net="VCC",
            part_token="10k_0402_1%",
            justification="DS Sec INT/SQW Output: open-drain pull-up",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        "5", "6", "7", "8", "9", "10", "11", "12",  # internal NC pins per DS
    }),
    layout_notes=(
        LayoutNote(
            text="Connect VBAT to CR2032 backup battery through a 10k current-limit resistor (DS Fig 1)",
            severity="rule",
            justification="DS Power Control section",
        ),
        LayoutNote(
            text="Keep VBAT and VCC bypass caps close to the IC for low ESR",
            severity="guideline",
        ),
    ),
)
