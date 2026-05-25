"""Pulse HX5008NLT - 1000BASE-T Gigabit Ethernet magnetics module.

Datasheet: Pulse HX5008NL, ref design from 1000BASE-T magnetics class
URL: https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf
Package: SOIC-24-15.1mm (SOP-24 4x6 pairs)

A 4-pair Gigabit Ethernet magnetics module:
    - 4 transformers (one per pair) with 1:1 CT:CT ratio
    - Common-mode chokes on each pair
    - Center taps brought out for Bob Smith termination

Connects directly between RTL8211F MDI[0..3]_P/N pins (on the SoM J1) and
the RJ45 connector pairs. Bob Smith network (75 ohm + 1nF 2kV) on each
center tap to chassis GND for EMI/ESD.

Pin map (per datasheet Table 1):
    24-pin SOIC. Magnetics module: each pair occupies 6 consecutive pins.
    Pair 0 pins 1-6, Pair 1 pins 7-12, Pair 2 pins 13-18, Pair 3 pins 19-24.

The four "Bob Smith" centre-tap networks tie pair common modes to
chassis GND through 75R + 1nF 2kV, plus one common point. Required by
IEEE 802.3 for emissions control.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)
from zynq_eda.catalog.refcircuits._paths import local_datasheet_path


HX5008NLT_REFCIRCUIT = ReferenceCircuit(
    part_mpn="HX5008NLT",
    lcsc="C962544",
    datasheet_url="https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf",
    datasheet_revision="Rev 2.2",
    app_circuit_figure="Figure 1 - Application Schematic (1000BASE-T)",
    local_datasheet_path=local_datasheet_path("HX5008NLT"),
    app_circuit_page="p.4, Figure 1 + IEEE 802.3 Bob Smith",
    minimum_circuit_verified=True,
    symbol_token="HX5008NLT",
    footprint="Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm",
    description="1000BASE-T 4-pair Ethernet magnetics module, SOIC-24",
    external_parts=(
        # Bob Smith termination network - one per pair
        # 75 ohm resistor + 1nF 2kV cap from each centre tap to a common node,
        # then 1nF 2kV cap from common node to chassis GND.
        # Four pairs => four 75R + four 1nF caps + one common 1nF chassis cap
        ExternalPart(
            from_pin="CT_PAIR0",
            to_net="BS_COMMON",
            part_token="75R_0603_1%",
            justification="IEEE 802.3 Bob Smith termination, pair 0 center tap",
        ),
        ExternalPart(
            from_pin="CT_PAIR0",
            to_net="BS_COMMON",
            part_token="1n_2kV_0603_safety",
            justification="IEEE 802.3 Bob Smith 1nF per pair, pair 0",
        ),
        ExternalPart(
            from_pin="CT_PAIR1",
            to_net="BS_COMMON",
            part_token="75R_0603_1%",
            justification="IEEE 802.3 Bob Smith termination, pair 1 center tap",
        ),
        ExternalPart(
            from_pin="CT_PAIR1",
            to_net="BS_COMMON",
            part_token="1n_2kV_0603_safety",
            justification="IEEE 802.3 Bob Smith 1nF per pair, pair 1",
        ),
        ExternalPart(
            from_pin="CT_PAIR2",
            to_net="BS_COMMON",
            part_token="75R_0603_1%",
            justification="IEEE 802.3 Bob Smith termination, pair 2 center tap",
        ),
        ExternalPart(
            from_pin="CT_PAIR2",
            to_net="BS_COMMON",
            part_token="1n_2kV_0603_safety",
            justification="IEEE 802.3 Bob Smith 1nF per pair, pair 2",
        ),
        ExternalPart(
            from_pin="CT_PAIR3",
            to_net="BS_COMMON",
            part_token="75R_0603_1%",
            justification="IEEE 802.3 Bob Smith termination, pair 3 center tap",
        ),
        ExternalPart(
            from_pin="CT_PAIR3",
            to_net="BS_COMMON",
            part_token="1n_2kV_0603_safety",
            justification="IEEE 802.3 Bob Smith 1nF per pair, pair 3",
        ),
        ExternalPart(
            from_pin="BS_COMMON",
            to_net="CHASSIS_GND",
            part_token="1n_2kV_0603_safety",
            justification="IEEE 802.3 / EN 55032: 1nF/2kV common-mode cap to chassis GND",
        ),
        # PHY-side centre taps to +3V3 (DC bias via inductor/ferrite for PHY)
        # Some PHY designs require an inductor; RTL8211F datasheet ref design uses
        # the magnetics module's internal taps. No explicit DC bias L required here.
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # Differential pairs pass through the magnetics; no external R/C on data lines
        "MDI0_P", "MDI0_N", "MDI1_P", "MDI1_N",
        "MDI2_P", "MDI2_N", "MDI3_P", "MDI3_N",
        "TD0_P", "TD0_N", "TD1_P", "TD1_N",
        "TD2_P", "TD2_N", "TD3_P", "TD3_N",
    }),
    layout_notes=(
        LayoutNote(
            text="Route each MDI pair as 100 ohm differential impedance, matched length within 0.5mm",
            severity="rule",
            justification="IEEE 802.3 / Pulse layout guide",
        ),
        LayoutNote(
            text="Chassis GND must be isolated from signal GND - join only at one point near RJ45",
            severity="rule",
            justification="EMI compliance",
        ),
        LayoutNote(
            text="Place magnetics module within 30mm of RJ45 connector",
            severity="rule",
            justification="Reduce common-mode noise",
        ),
    ),
)
