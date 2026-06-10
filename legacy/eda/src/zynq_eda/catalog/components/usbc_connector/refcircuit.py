"""TYPE-C-31-M-12 - 16-pin USB Type-C SMD receptacle (USB 2.0 only variant).

Datasheet: Korean Hroparts Elec TYPE-C-31-M-12 (mechanical only, 1 page)
LCSC: C165948
Package: USB Type-C SMD receptacle, 16 active pins + 4 shield tabs

This is the 16-pin USB-C receptacle variant -- USB 2.0 data only, no
USB 3.x SuperSpeed lanes (the full 24-pin USB-C 3.x receptacle has 8
extra pins for TX/RX SS lanes that this part omits). It still carries
all USB-C-mandated 5A current rating, CC pins, SBU pins, and the
reversible-orientation D+/D- pairs.

Pin map (per the mechanical drawing in `datasheet.pdf` -- the
manufacturer's "1 of 1" sheet -- and USB Type-C R2.1 Sec 3.2):

    Side A             Side B
    A1  GND            B1  GND
    A4  VBUS           B4  VBUS
    A5  CC1            B5  CC2
    A6  D+1 (DP1)      B6  D+2 (DP2)
    A7  D-1 (DN1)      B7  D-2 (DN2)
    A8  SBU1           B8  SBU2
    A9  VBUS           B9  VBUS
    A12 GND            B12 GND
    Shield (4 tabs)    -> via 1Mohm + 100nF AC-coupling to chassis GND

Reversible-orientation pairing: depending on plug orientation, either
DP1/DN1 (A6/A7) or DP2/DN2 (B6/B7) carry the USB 2.0 data. The carrier
ties A6+B6 -> USB_DP and A7+B7 -> USB_DM so either orientation works
without an external mux.

CC1 (A5) and CC2 (B5) advertise the role:
  - As a SINK (this carrier's default): 5.1 kOhm Rd pull-down on EACH CC pin.
  - With FUSB302 active: the FUSB302's internal PDWN switches own Rd and
    the external 5.1k is a redundant fallback (mechanical-only sink mode).

Mechanical / electrical ratings (from the drawing):
    Current rating         5 A
    Voltage rating         20 V
    Insulation resistance  >= 100 Mohm
    Dielectric withstand   AC 100 V for 1 minute
    Mating cycles          10 000
    Operating temperature  -30 degC to +80 degC
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


USBC_DEVICE_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TYPE-C-31-M-12",
    lcsc="C165948",
    datasheet_url="https://datasheet.lcsc.com/lcsc/2304140030_Korean-Hroparts-Elec-TYPE-C-31-M-12_C165948.pdf",
    datasheet_revision="2020.12.08 (drawing rev A)",
    app_circuit_figure=(
        "Mechanical drawing (TYPE-C-31-M-12 page 1/1) + "
        "USB Type-C R2.1 Sec 4.5 (sink Rd termination)"
    ),
    local_datasheet_path="components/usbc_connector/datasheet.pdf",
    app_circuit_page="Mechanical 1/1 + USB-C R2.1 Sec 4.5",
    minimum_circuit_verified=True,
    symbol_token="USBC_16P",
    footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    description="USB Type-C 16P SMD receptacle (USB 2.0 only), sink role",
    external_parts=(
        # ---- CC1 / CC2 sink-role advertisement ----
        # USB Type-C R2.1 Sec 4.5.1.2.1: a Sink shall implement Rd = 5.1k +/- 20%
        # to GND on each CC pin. Even with FUSB302 on the same CC lines the
        # external 5.1k is a safe redundancy for the mechanical-only fallback
        # (FUSB302 absent / unpowered).
        ExternalPart(
            from_pin="CC1",
            to_net="GND",
            part_token="5k1_0402_1%",
            justification=(
                "USB-C R2.1 Sec 4.5.1.2.1: 5.1k Rd on CC1 advertises sink role; "
                "redundant fallback when FUSB302 owns CC termination"
            ),
        ),
        ExternalPart(
            from_pin="CC2",
            to_net="GND",
            part_token="5k1_0402_1%",
            justification=(
                "USB-C R2.1 Sec 4.5.1.2.1: 5.1k Rd on CC2 (one per pin for "
                "reversibility); same fallback rationale as CC1"
            ),
        ),
        # ---- VBUS bulk + HF bypass ----
        # USB-PD R3.1 Sec 7.1.16 requires a sink to present 1-10 uF of bulk
        # capacitance on VBUS to absorb voltage transitions; USB 2.0 Sec
        # 7.2.4.1 calls for a 1-10 uF bulk + 100 nF HF bypass on each port.
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="10u_0402_X5R",
            justification="USB-PD R3.1 Sec 7.1.16: VBUS bulk capacitance (1-10uF sink)",
        ),
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="USB 2.0 Sec 7.2.4.1: 100nF VBUS HF bypass at receptacle",
        ),
        # ---- Shield AC-coupling to chassis GND ----
        # USB-IF "Compliance Plan for USB Type-C R2.0" Sec 5.2 / EMC best
        # practice: connect connector shield to CHASSIS_GND (the mounting
        # plane) through a 1Mohm bleed resistor in parallel with a 100nF
        # AC-coupling cap. This keeps DC isolation between the cable shield
        # and the board's signal-GND while shunting ESD/EMI energy.
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="1M_0402_1%",
            justification="USB-IF Compliance: 1Mohm shield-to-CHASSIS bleed resistor",
        ),
        ExternalPart(
            from_pin="SHIELD",
            to_net="CHASSIS_GND",
            part_token="100n_0402_X7R",
            justification="USB-IF Compliance: 100nF shield AC-coupling to chassis",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # Data lines pass straight through to the next stage (USBLC6 ESD
        # array on its way to the USB PHY). No termination, pull-up, or
        # series resistor at the connector pin.
        "D+", "D-",
        # SBU1 / SBU2 are reserved for USB-C alternate-mode (DisplayPort
        # AUX, USB-PD VDM debug). Unused on this carrier; routed to STM32
        # only when the OTG block needs an ID-hint signal.
        "SBU1", "SBU2",
    }),
    layout_notes=(
        LayoutNote(
            text=(
                "USB 2.0 D+/D- routing: 90 ohm differential impedance from the "
                "connector pads through the USBLC6 to the USB PHY. Tie A6/B6 "
                "together and A7/B7 together as close to the connector as "
                "possible (reversible orientation)"
            ),
            severity="rule",
            justification="USB 2.0 Sec 7.1.6 + USB-C R2.1 Sec 3.2 reversibility",
        ),
        LayoutNote(
            text=(
                "VBUS routing: minimum 0.5mm trace width per VBUS pin (the "
                "connector has 4 VBUS pins to share 5A; >= 0.5mm per pin "
                "supports >1A each without exceeding IPC-2221 20degC rise)"
            ),
            severity="rule",
            justification="IPC-2221A Table 6-4 + 5A nameplate (Mechanical 4-1)",
        ),
        LayoutNote(
            text=(
                "Connector shield tabs go to CHASSIS_GND ONLY -- a separate "
                "copper region from signal GND, joined back through the 1Mohm "
                "+ 100nF AC-coupling network. Do NOT short shield to signal GND "
                "directly (creates ground loops + EMI re-radiation)"
            ),
            severity="rule",
            justification="USB-IF EMC compliance + standard shield-discharge practice",
        ),
        LayoutNote(
            text=(
                "Place the 5.1k Rd resistors (CC1, CC2) within 5mm of the "
                "connector CC pins. Place VBUS bulk + HF bypass within 10mm "
                "of the nearest VBUS pin"
            ),
            severity="guideline",
            justification="Minimise CC capacitance tolerance + VBUS ESR",
        ),
        LayoutNote(
            text=(
                "Mechanical: TYPE-C-31-M-12 footprint is the HRO variant with "
                "0.5/3.5 mm SMT lead pitch. Use the Connector_USB:USB_C_"
                "Receptacle_HRO_TYPE-C-31-M-12 footprint exactly; the through-"
                "hole alignment posts are not interchangeable across vendors"
            ),
            severity="info",
            justification="HRO mechanical drawing (page 1/1)",
        ),
    ),
)
