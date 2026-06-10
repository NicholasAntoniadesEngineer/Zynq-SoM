"""Amphenol RJHSE5380 - Shielded RJ45 8P8C jack with LEDs (no magnetics).

Datasheet: Amphenol Communications Solutions RJHSE-538x series (Rev C, 2018)
Drawing:   P-RJHSE-X380 (HIGH SPEED, RJ45, MODULAR JACK, 8 POSITION,
                         8 CONTACTS, SHIELDED, MAGNETICS-LESS)
Package:   RJ45 through-hole right-angle, 16.51 x 13.46mm body

The Amphenol RJHSE-538x series ships in two visual variants:
    * "WITHOUT LEDs" - the mechanical drawing in this folder (see
       ``datasheet.pdf`` page 1, title block confirms NO LEDs).
    * "WITH LEDs"    - same footprint plus two integrated LED windows
       (link, activity) brought out to extra pins; this is the
       RJHSE5380 part actually used on the carrier (LCSC C464586).

The carrier's KiCad symbol uses the "WITH LEDs" pinout (LED1_A, LED2_A
plus a common SHIELD pin). Both LEDs share their cathode on the PHY-
driven nets (active-low link/activity from the SoM PHY).

Because this part does NOT contain magnetics, all 1000BASE-T isolation /
common-mode termination must be supplied externally by the Pulse
HX5008NLT module (see ``components/hx5008nlt``). Allowing scope probes
on the MDI lines between PHY and magnetics is a deliberate debug
feature - hence the 'split' magnetics + bare-jack topology.

Pin map (per RJHSE-X380 mechanical drawing + carrier symbol):

     1  MDI lane 0 +  (cable-side; routed from HX5008NLT MX1+)
     2  MDI lane 0 -
     3  MDI lane 1 +
     4  MDI lane 1 -
     5  MDI lane 2 +
     6  MDI lane 2 -
     7  MDI lane 3 +
     8  MDI lane 3 -
     9  LED1 anode   (left LED window, typical green = Link/1000)
    11  LED2 anode   (right LED window, typical yellow = Activity)
    SH  Shield tab(s) bonded to CHASSIS_GND

External parts:
    * LED1 + LED2 current-limit resistors (330R typical, +3V3 supply).
      Approx forward current = (3.3V - V_F) / 330R = ~3-4 mA. Drive
      via active-low signals from the PHY's LED outputs (RTL8211F
      pins LED0..2 are open-drain).
    * Shield tab to CHASSIS_GND (direct copper, no resistor/cap - the
      HX5008NLT Bob Smith network already provides the AC-coupled
      shield-to-chassis return).

No external R/C on the MDI lines themselves: differential termination
is done inside the magnetics + PHY, not at the jack.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


RJ45_REFCIRCUIT = ReferenceCircuit(
    part_mpn="RJHSE5380",
    lcsc="C464586",
    datasheet_url="https://www.amphenol-cs.com/product-series/rjhse5380.html",
    datasheet_revision="Rev C (drawing P-RJHSE-X380, 2018-06-19)",
    app_circuit_figure="P-RJHSE-X380 mechanical drawing (carrier uses WITH-LEDs variant)",
    local_datasheet_path="components/rj45/datasheet.pdf",
    app_circuit_page="Sheet 1: P-RJHSE-X380 dimensions + materials + pin notes",
    minimum_circuit_verified=True,
    symbol_token="RJ45_RJHSE5380",
    footprint="Connector_RJ:RJ45_Amphenol_RJHSE5380_Horizontal",
    description="Shielded RJ45 8P8C jack with 2 integrated LEDs, magnetics-less",
    external_parts=(
        # LED1 - Link / 1000BASE-T indicator. Anode -> +3V3 via 330R, cathode
        # driven low by the PHY's LED output (open-drain).
        ExternalPart(
            from_pin="LED1_A",
            to_net="+3V3",
            part_token="330R_0402_1%",
            justification="LED current limit: I_LED = (3.3V - 2.0V V_F) / 330R "
                          "~ 4 mA (green/yellow 0603 LED, well below 20 mA max)",
        ),
        # LED2 - Activity indicator. Same drive scheme.
        ExternalPart(
            from_pin="LED2_A",
            to_net="+3V3",
            part_token="330R_0402_1%",
            justification="LED current limit (Activity LED), matches LED1 for "
                          "consistent brightness",
        ),
        # Shield to CHASSIS_GND. No resistor / cap: the Bob Smith network on
        # HX5008NLT (see ``components/hx5008nlt``) already provides the
        # AC-coupled chassis-to-shield return; bonding here is direct.
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # MDI lanes pass through to the magnetics; no external R / C on the
        # cable side (IEEE 802.3 termination is internal to the magnetics
        # module + PHY).
        "MDI0_P", "MDI0_N",
        "MDI1_P", "MDI1_N",
        "MDI2_P", "MDI2_N",
        "MDI3_P", "MDI3_N",
        # Shield tabs go straight to CHASSIS_GND copper pour.
        "SHIELD",
    }),
    layout_notes=(
        LayoutNote(
            text="Tie all shield-mounting legs (SH) directly to a CHASSIS_GND "
                 "copper island; that island bonds to signal GND only at a "
                 "single star point near the carrier power-entry connector",
            severity="rule",
            justification="EMC ground-loop avoidance + IEEE 802.3 Sec 14.7",
        ),
        LayoutNote(
            text="Keep RJ45 within 30mm of HX5008NLT magnetics; route the four "
                 "MDI pairs as 100R differential, length-matched within 0.5mm",
            severity="rule",
            justification="IEEE 802.3 Sec 40.7 + Pulse HX5008NL layout guide",
        ),
        LayoutNote(
            text="LED traces (LED1_A / LED2_A) are low-speed and may be routed "
                 "freely; keep them >= 3x line width from MDI pairs to avoid "
                 "coupling switching noise onto the cable",
            severity="guideline",
        ),
        LayoutNote(
            text="If the carrier uses a panel-mount RJ45 with screw shield "
                 "(not this part), bond chassis through the screws as well to "
                 "avoid a high-impedance shield path",
            severity="info",
        ),
    ),
)
