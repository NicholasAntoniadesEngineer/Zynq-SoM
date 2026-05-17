"""INA226AIDGSR - High-side bidirectional current/power monitor.

Datasheet: Texas Instruments INA226, Rev August 2015
URL: https://www.ti.com/lit/ds/symlink/ina226.pdf
Package: VSSOP-10 (DGS)

I2C 16-bit current/power monitor with 36V common-mode range (well above
all carrier rails: VIN 5V, +3V3, +1V8, +VCCO_xx up to 3V3). Used to
monitor power consumption on each major rail.

Pin map (per datasheet):
    1  IN+    - Differential input across shunt (+)
    2  IN-    - Differential input across shunt (-)
    3  VBUS   - Bus voltage input (can be same as IN+ for low-side)
    4  GND
    5  VS     - 2.7-5.5V supply
    6  SCL    - I2C clock
    7  SDA    - I2C data
    8  ALERT  - alert/conversion-ready output
    9  A0     - I2C address bit 0 (low/high/SDA/SCL)
    10 A1     - I2C address bit 1

R_sense selection (typical): 0.01 ohm 1206 for currents up to 8A,
                              0.1 ohm for currents up to 800mA.
Resolution: 2.5 uV/LSB on shunt.

For each rail we monitor, instantiate one INA226 with:
    R_sense in series with the rail
    A0/A1 strapped per the rail's I2C address
"""

from __future__ import annotations

from scripts.carrier.core.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


INA226_REFCIRCUIT = ReferenceCircuit(
    part_mpn="INA226AIDGSR",
    lcsc="C49851",
    datasheet_url="https://www.ti.com/lit/ds/symlink/ina226.pdf",
    datasheet_revision="Rev August 2015 (SBOS547A)",
    app_circuit_figure="Figure 32 - Typical Application Circuit",
    symbol_token="INA226AIDGSR",
    footprint="Package_SO:VSSOP-10_3x3mm_P0.5mm",
    description="Bidirectional I2C current/power monitor 16-bit, 36V common-mode",
    external_parts=(
        # VS supply decoupling
        ExternalPart(
            from_pin="VS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 9.2: VS decoupling - 100nF close to pin",
        ),
        # Differential input filter (recommended for noise immunity, DS Fig 32)
        # 10 ohm + 100nF on each side - we use 100R for cleanliness
        ExternalPart(
            from_pin="IN+",
            to_net="IN-",
            part_token="100n_0402_X7R",
            justification="DS Sec 9.3: Differential filter cap between IN+ / IN- (optional)",
        ),
        # I2C pull-ups (on the shared bus - one set per bus, not per IC)
        # We don't add pull-ups here because the bus shares pull-ups
        # with other I2C devices; tracked elsewhere
    ),
    strap_pins=(
        # Each INA226 instance gets its own A0/A1 strap to set bus address.
        # Specific values per-instance set in the sheet generator.
    ),
    no_external_required=frozenset({"ALERT"}),  # alert pin can be NC if unused
    layout_notes=(
        LayoutNote(
            text="Kelvin-sense the shunt: route IN+ / IN- as differential Kelvin connections from each side of the shunt resistor",
            severity="rule",
            justification="DS Sec 11 Layout - required for sub-mV accuracy",
        ),
        LayoutNote(
            text="Place R_sense in the high-side of the rail (between source and load)",
            severity="rule",
            justification="DS Sec 9.3 Application",
        ),
    ),
)
