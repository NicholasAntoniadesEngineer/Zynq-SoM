"""DS3231SN# - Extremely Accurate I2C-Integrated RTC/TCXO.

Datasheet: Analog Devices (formerly Maxim) DS3231 — distributed on the
carrier as ``components/ds3231/datasheet.pdf`` (Adafruit Precision RTC
breakout learn-guide bundle, last updated 2024-06-03; contains both the
electrical/pinout summary and a full reference schematic).
URL: https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231.pdf
Package: SOIC-16W (300 mil)

The DS3231 integrates a 32.768 kHz TCXO and a temperature-compensated
crystal inside the package — no external crystal load caps are needed.
The chip provides:

  * A precision real-time clock readable over I2C (slave address 0x68).
  * Battery-backed timekeeping from a CR1220 / CR2032 coin cell on VBAT
    (no external dropper resistor; the DS3231 internally switches its
    timekeeping domain to VBAT when VCC drops).
  * A 32.768 kHz square wave output (32K, open-drain) for external clocking.
  * A combined INT/SQW output (open-drain) for the alarm interrupt or a
    1 Hz square wave.
  * An RST_N output with an *internal* 50 kΩ pull-up to VCC that drops
    low when VCC falls below the power-fail trip point (~2.45 V).

Pin map (per datasheet):
    1   32kHz   - 32.768 kHz square-wave output (open-drain)
    2   VCC     - 2.3 V-5.5 V supply
    3   INT/SQW - Alarm interrupt OR 1 Hz/1 kHz/4 kHz/8 kHz output (open-drain)
    4   RST_N   - Power-fail / reset output (open-drain, internal 50k pull-up)
    5-12 N.C.   - "Internal use; connect to GND" (per Adafruit ref schematic)
    13  GND
    14  VBAT    - Backup battery input (2.3 V-5.5 V; from CR2032)
    15  SDA     - I2C data (open-drain)
    16  SCL     - I2C clock

I2C slave address (factory-fixed): 0b1101000x  → 0x68 (read/write encoded
in the LSB). No external address-strap pins.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


DS3231_REFCIRCUIT = ReferenceCircuit(
    part_mpn="DS3231SN#",
    lcsc="C722469",
    datasheet_url="https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231.pdf",
    datasheet_revision="Adafruit DS3231 breakout learn-guide bundle, 2024-06-03",
    app_circuit_figure="Adafruit DS3231 Precision RTC schematic (original-version, p. 24)",
    local_datasheet_path="components/ds3231/datasheet.pdf",
    app_circuit_page="p. 24 - Schematic and Fab Print for Original Version",
    minimum_circuit_verified=True,
    symbol_token="DS3231SN",
    footprint="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
    description="Extremely accurate I2C RTC with integrated TCXO + crystal, battery backup, SOIC-16W",
    supply_rail="+3V3",
    external_parts=(
        # VCC decoupling - Adafruit reference schematic shows a single 0.1uF
        # at VCC. The DS3231 has very low transient current (a few hundred
        # microamps), so a bulk cap is not required.
        ExternalPart(
            from_pin="VCC",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="Adafruit ref schematic: 0.1uF VCC decoupling at pin 2",
        ),
        # VBAT cell - direct CR2032 coin-cell holder. The DS3231 datasheet
        # explicitly shows VBAT going directly to the cell (no current-limit
        # resistor); the chip's internal trickle charger is *disabled* by
        # default and a primary-cell CR2032 cannot be charged anyway.
        ExternalPart(
            from_pin="VBAT",
            to_net="GND",
            part_token="batt_CR2032_holder",
            justification="DS Sec Power Control: VBAT direct to CR2032 primary cell",
        ),
        # VBAT decoupling - small cap shunts noise picked up on the battery
        # trace (long traces to the cell holder are susceptible).
        ExternalPart(
            from_pin="VBAT",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="Adafruit ref schematic: 0.1uF VBAT decoupling for noise immunity",
        ),
        # I2C pull-ups - 10k matches the Adafruit reference; 4.7k is also
        # acceptable per the I2C specification when sharing the bus with
        # other devices. Pulled to +3V3 (carrier I2C is 3.3V level).
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="I2C Sec 7: SDA pull-up (4k7 chosen for shared 3.3V I2C bus)",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="I2C Sec 7: SCL pull-up (4k7 chosen for shared 3.3V I2C bus)",
        ),
        # 32kHz open-drain output pull-up (Adafruit ref shows 10k to VCC).
        # Included so the output can be read as a clean digital signal.
        ExternalPart(
            from_pin="32kHz",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec 32kHz Output: open-drain output requires external pull-up",
        ),
        # INT/SQW open-drain output pull-up.
        ExternalPart(
            from_pin="INT_SQW",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec INT/SQW Output: open-drain output requires external pull-up",
        ),
        # NOTE: RST_N has an internal 50k pull-up per the datasheet, so no
        # external pull-up is required. Listed in no_external_required below.
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # RST_N has internal 50k pull-up (datasheet) — no external needed.
        "RST_N",
        # Pins 5-12 are "Internal use; should be GND" — handled at the
        # block level by tying to GND, not by an external passive.
        "N.C.1", "N.C.2", "N.C.3", "N.C.4",
        "N.C.5", "N.C.6", "N.C.7", "N.C.8",
    }),
    layout_notes=(
        LayoutNote(
            text="Place the 0.1uF VCC bypass within 5 mm of pin 2 (VCC)",
            severity="rule",
            justification="Standard SOIC decoupling practice; minimises supply impedance",
        ),
        LayoutNote(
            text="Keep the VBAT trace short and quiet — no switching signals "
                 "should cross it. Place the 0.1uF VBAT cap near pin 14",
            severity="rule",
            justification="Adafruit ref schematic; VBAT noise couples into TCXO",
        ),
        LayoutNote(
            text="Tie pins 5-12 directly to the GND plane (single via per pin)",
            severity="rule",
            justification="DS pin description: 'Internal use; should be GND'",
        ),
        LayoutNote(
            text="Avoid placing high-current switching regulators within 10 mm "
                 "of the DS3231 — the internal TCXO is temperature-sensitive",
            severity="guideline",
            justification="DS Sec Operating Characteristics: TCXO drift vs temperature",
        ),
    ),
)
