"""SS14 - 1 A 40 V Schottky rectifier for carrier +VIN reverse-polarity protection.

Datasheet: Fairchild / ON Semiconductor SS12 - S100 series, Rev 1.9 (January 2015)
URL: https://www.onsemi.com/download/data-sheet/pdf/ss12-d.pdf
Package: SMA / DO-214AC (color band = cathode)

Used as the carrier's input-side reverse-polarity protector + bulk
decoupling node:

    +VIN_IN ---[Anode-->|-Cathode]--- +VIN ---+---+--- (LDOs / load switches)
                  SS14                          |   |
                                              C_bulk C_HF
                                                |   |
                                               GND GND

A wrong-polarity supply or a hot-swap transient that briefly pulls
+VIN_IN below ground is blocked by the SS14 body diode (V_RRM = 40 V,
DS Sec Absolute Maximum Ratings). At 1 A the forward voltage drop V_F
~= 0.5 V (DS Sec Electrical Characteristics), so downstream LDOs must
have enough headroom -- 5 V - 0.5 V = 4.5 V which still exceeds the
TLV75733 dropout requirement (V_IN_min = V_OUT + V_DO ~= 3.725 V).

Pin map (Device:D_Schottky symbol pins):
    1  K (cathode)  - to protected +VIN node
    2  A (anode)    - to raw +VIN_IN from USB-C
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


POWER_INPUT_REFCIRCUIT = ReferenceCircuit(
    part_mpn="SS14",
    lcsc="C83852",
    datasheet_url="https://datasheet.lcsc.com/lcsc/ON-Semicon-SS14_C83852.pdf",
    datasheet_revision="Rev 1.9, January 2015",
    app_circuit_figure="Series reverse-polarity protection + downstream bulk capacitance",
    local_datasheet_path="components/power_input/datasheet.pdf",
    app_circuit_page="p.2, Electrical Characteristics + p.4 DO-214AC SMA",
    minimum_circuit_verified=True,
    symbol_token="SS14",
    footprint="Diode_SMD:D_SMA",
    description="40 V 1 A Schottky reverse-polarity protector at +VIN input",
    supply_rail="+VIN_IN",
    pin_net_overrides=(
        # SS14 sits in series between the raw USB-C 5 V (+VIN_IN) and the
        # protected +VIN rail that feeds every downstream regulator.
        ("A", "+VIN_IN"),
        ("K", "+VIN"),
    ),
    external_parts=(
        # Bulk input capacitance after the Schottky (DS Sec Application
        # Information; standard practice for reverse-polarity protection
        # nodes). 100 uF 1206 carries the inrush charge of the downstream
        # LDOs while +VIN_IN ramps up.
        ExternalPart(
            from_pin="K",
            to_net="GND",
            part_token="100u_1206_X5R",
            justification="Bulk decoupling on the protected +VIN rail (>= 10 uF after derating)",
        ),
        # Mid-frequency bulk (covers the gap between the 100 uF ESL and
        # the per-IC 1 uF / 100 nF caps).
        ExternalPart(
            from_pin="K",
            to_net="GND",
            part_token="10u_0402_X5R",
            justification="Mid-frequency bulk between the 100 uF input bank and per-IC 1 uF caps",
        ),
        # HF bypass at the protected +VIN node.
        ExternalPart(
            from_pin="K",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="HF bypass at the protected +VIN rail entry point",
        ),
        # Raw-input-side bulk cap on +VIN_IN to absorb cable/transient
        # ringing before the Schottky (input-side decoupling, standard
        # practice for USB-C 5 V power input).
        ExternalPart(
            from_pin="A",
            to_net="GND",
            part_token="10u_0402_X5R",
            justification="Pre-Schottky input-side bulk to absorb cable inductance ringing",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset(),
    layout_notes=(
        LayoutNote(
            text=(
                "Place the SS14 in series with the +VIN trace immediately "
                "downstream of the USB-C VBUS pins; keep the loop to the bulk "
                "100 uF cap short to minimise inrush ringing"
            ),
            severity="rule",
            justification="Reverse-polarity protection standard practice + SS14 DS land pattern recommendation",
        ),
        LayoutNote(
            text=(
                "Use a wide copper pour for the +VIN_IN and +VIN traces (>= 30 mil "
                "or polygon flood) to carry up to 1 A continuous without "
                "exceeding the 1 W package dissipation rating (DS Thermal "
                "Characteristics, R_thJA = 88 degC/W)"
            ),
            severity="rule",
            justification="DS Sec Thermal Characteristics (88 degC/W)",
        ),
        LayoutNote(
            text=(
                "Orient the SS14 with the cathode band toward the protected "
                "+VIN node; current flows anode (+VIN_IN) to cathode (+VIN)"
            ),
            severity="info",
            justification="DS p.1 Figure shows cathode band orientation",
        ),
    ),
)
