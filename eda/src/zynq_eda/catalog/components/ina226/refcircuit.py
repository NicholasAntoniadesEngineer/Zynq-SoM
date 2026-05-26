"""INA226AIDGSR - I2C 36 V bidirectional current / voltage / power monitor.

Datasheet: Texas Instruments INA226, SBOS547B, June 2011 - Revised September 2024
URL: https://www.ti.com/lit/ds/symlink/ina226.pdf
Package: VSSOP-10 (DGS, 3 x 4.9 mm)

16-bit I2C current shunt + bus voltage monitor with a 0 - 36 V common-
mode input range (independent of the V_S supply). Used to instrument
each major rail on the carrier so the STM32 co-processor can read
back live current / bus-voltage / power figures over I2C2 and react
to over-/under-limit conditions via the open-drain ALERT pin.

Pin map (DGS / VSSOP-10, per DS Sec 4 Pin Configuration and Functions, p.3):
    1  A1     - Address bit 1 (strap to GND/SCL/SDA/VS for 4 of 16 addresses)
    2  A0     - Address bit 0 (strap as above)
    3  Alert  - Open-drain alert / conversion-ready output (active low)
    4  SDA    - I2C data (open-drain, bidirectional)
    5  SCL    - I2C clock (open-drain input)
    6  VS     - 2.7 - 5.5 V chip supply
    7  GND    - Analog + digital ground (single tied pin)
    8  Vbus   - Bus-voltage sense input (0 - 36 V, separate from VS)
    9  Vin-   - Differential shunt sense, load side
   10  Vin+   - Differential shunt sense, supply side

Min circuit (DS Fig 8-1 Typical Circuit Configuration, p.28):
    * R_shunt across Vin+ / Vin- (sized to the monitored rail's I_max)
    * 0.1 uF bypass on VS -> GND, close to pin 6
    * 4.7 k pull-ups on SDA / SCL / Alert to the I2C bus supply
    * A0 / A1 strapped per instance for unique addresses
    * Vbus connected to the rail being monitored (DS Fig 8-1 + Fig 8-4
      layout example note (1): "connect the Vbus pin to the power
      supply rail")

I2C address (Table 6-2, p.18):
    A1 = GND, A0 = GND  ->  1000000 = 0x40
    A1 = GND, A0 = VS   ->  1000001 = 0x41
    A1 = GND, A0 = SDA  ->  1000010 = 0x42
    A1 = GND, A0 = SCL  ->  1000011 = 0x43
    A1 = VS,  A0 = GND  ->  1000100 = 0x44
    A1 = VS,  A0 = VS   ->  1000101 = 0x45
    A1 = VS,  A0 = SDA  ->  1000110 = 0x46
    A1 = VS,  A0 = SCL  ->  1000111 = 0x47
    A1 = SDA, A0 = GND  ->  1001000 = 0x48
    ... (16 total)

R_shunt selection (DS Sec 6.5 Programming + Eq 7):
    Shunt full-scale = 81.92 mV (16-bit, 2.5 uV/LSB).
    For I_max <= 8 A use a 10 mOhm shunt (full-scale at 8.192 A).
    On the carrier we standardise on 10 mOhm (R_SENSE_10mR_2010_1%)
    for all 6 monitored rails -- a single SKU for the entire BOM.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


INA226_REFCIRCUIT = ReferenceCircuit(
    part_mpn="INA226AIDGSR",
    lcsc="C49851",
    datasheet_url="https://www.ti.com/lit/ds/symlink/ina226.pdf",
    datasheet_revision="SBOS547B, Jun 2011 - Rev Sep 2024",
    app_circuit_figure="Figure 8-1 - Typical Circuit Configuration",
    local_datasheet_path="components/ina226/datasheet.pdf",
    app_circuit_page="p.28, Figure 8-1",
    minimum_circuit_verified=True,
    symbol_token="INA226AIDGSR",
    footprint="Package_SO:VSSOP-10_3x3mm_P0.5mm",
    description="Bidirectional I2C current/voltage/power monitor, 16-bit, 36 V common-mode, VSSOP-10",
    supply_rail="+3V3",
    external_parts=(
        # R_SENSE shunt: defining current-sense element.
        # The KiCad Sensor_Energy:INA226 symbol names the differential
        # sense pins ``Vin+`` and ``Vin-`` (per DS Sec 4 Table 4-1); the
        # shunt sits between these two pins, with the Kelvin connection
        # to the actual shunt resistor pads handled in layout.
        ExternalPart(
            from_pin="Vin+",
            to_net="Vin-",
            part_token="R_SENSE_10mR_2010_1%",
            justification=(
                "DS Sec 6.5 + Eq 7: R_SENSE = V_FS / I_max. 10 mOhm gives "
                "81.92 mV full-scale at 8.192 A (matches the 16-bit / 2.5 uV "
                "LSB native range); standardised across all 6 carrier instances"
            ),
        ),
        # VS supply decoupling (DS Sec 8.3 Power Supply Recommendations
        # + Fig 8-1: 0.1 uF C_BYPASS close to VS / GND pins).
        ExternalPart(
            from_pin="VS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Sec 8.3 + Fig 8-1: 0.1 uF C_BYPASS on VS as close as possible to the device",
        ),
        # I2C bus pull-ups (DS Fig 8-1 shows pull-ups to VS). Each I2C
        # bus only needs one set of pull-ups; we put 4.7 k on each
        # INA226 to keep the bus topology simple. If multiple INA226
        # share a bus the parallel resistance still meets the I2C
        # spec (5 INA226 in parallel = 940 Ohm, well above 500 Ohm
        # min for fast-mode).
        ExternalPart(
            from_pin="SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Fig 8-1 + Sec 8.2.1.2: I2C SDA pull-up to bus supply",
        ),
        ExternalPart(
            from_pin="SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Fig 8-1 + Sec 8.2.1.2: I2C SCL pull-up to bus supply",
        ),
        # ALERT open-drain output (DS Sec 6.3.5). The DS explicitly says
        # 'The alert pin must to be pulled up to the V_VS pin voltage
        # via the pull-up resistors' (Sec 8.2.1.2).
        ExternalPart(
            from_pin="~{Alert}",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="DS Sec 8.2.1.2 + Fig 8-1: ALERT open-drain pull-up to V_VS",
        ),
    ),
    strap_pins=(
        # A0 / A1 per-instance straps are decided at the block level
        # (each rail gets a unique I2C address via net_overrides on the
        # IcInstance), not in the shared refcircuit.
    ),
    pin_net_overrides=(
        # Vbus measures the rail being monitored (DS Fig 8-4 layout
        # example note (1): 'connect the Vbus pin to the power supply
        # rail'). Default to +VIN since that is the only rail wired
        # through the existing power_mon block; per-instance blocks
        # override this via IcInstance.net_overrides for other rails.
        ("Vbus", "+VIN"),
        # Vin+ (pin 10) is the supply-side shunt-sense input; it sits on
        # the +VIN rail and the shunt R_SENSE connects from here to Vin-.
        # Per DS Sec 4 Table 4-1, Vin+ is a high-impedance differential
        # sense input -- naming it explicitly so the IC pin shares the
        # same +VIN node as Vbus and the R_SENSE near-side terminal.
        ("Vin+", "+VIN"),
        # Vin- (pin 9) is the load-side shunt-sense input, electrically
        # one shunt resistor downstream of +VIN. The shunt's far terminal
        # carries a local label "Vin-" (raw to_net from the R_SENSE
        # ExternalPart), so we name the IC pin with the same label so
        # KiCad joins the IC pin and the shunt's far terminal on one net.
        # Without this entry the IC pin is electrically isolated and the
        # shunt is just a floating two-pin resistor.
        ("Vin-", "Vin-"),
    ),
    lib_symbol_pin_type_overrides=(
        # The stock ``Sensor_Energy:INA226`` symbol declares Vbus
        # (pin 8) as ``input``. Per the datasheet (Sec 4 Table 4-1
        # + Sec 8 Functional Description), Vbus is a high-impedance
        # voltage SENSE node tied directly to the bus rail it
        # measures -- it does not consume current and is NOT driven
        # by any active output in the schematic. KiCad's ERC treats
        # ``input`` as a sink that must be paired with an ``output``
        # driver on the same net; a ``power:PWR_FLAG`` (Power output
        # category) on +VIN does not satisfy this. Overriding to
        # ``passive`` matches the pin's real electrical character
        # and clears the spurious ``pin_not_driven`` ERC violation
        # without globally relaxing the rule.
        ("Vbus", "passive"),
    ),
    no_external_required=frozenset(),
    layout_notes=(
        LayoutNote(
            text=(
                "Kelvin-connect IN+ and IN- to the shunt resistor pads (4-wire "
                "or true Kelvin geometry). Route the sense traces away from "
                "the high-current shunt-to-load and shunt-to-source paths"
            ),
            severity="rule",
            justification="DS Sec 8.4.1 Layout Guidelines",
        ),
        LayoutNote(
            text=(
                "Place the 0.1 uF VS bypass cap as close as possible to the VS "
                "(pin 6) and GND (pin 7) pins of the device"
            ),
            severity="rule",
            justification="DS Sec 8.3 Power Supply Recommendations + Fig 8-4",
        ),
        LayoutNote(
            text=(
                "Route Vin+ / Vin- as a tight differential pair from the shunt "
                "back to pins 9/10 to reject common-mode noise on long sense traces"
            ),
            severity="guideline",
            justification="DS Sec 8.4.1 Layout Guidelines",
        ),
        LayoutNote(
            text=(
                "Connect the Vbus pin (8) directly to the monitored power rail "
                "via a via to the power plane; the bus voltage measurement is "
                "independent of V_S, so noisy or switching rails can be sensed "
                "without affecting the device supply"
            ),
            severity="info",
            justification="DS Fig 8-4 note (1)",
        ),
    ),
)
