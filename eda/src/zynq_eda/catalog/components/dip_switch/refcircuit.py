"""HANBO DS-04P - 4-position SMD DIP switch (1.27 mm spacing).

Datasheet: HANBO DS-04P mechanical drawing, distributed locally as
``components/dip_switch/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf

A 4-position SPST DIP switch on a 1.27 mm pitch SMD package. Each
switch has two solder pads (top + bottom); when the slide is OFF the
contacts are open, when ON they short the top pad to the bottom pad.

Electrical highlights (catalog page 1):
    - Non-switching current rating: 100 mA at 50 V DC
    - Switching current rating: 25 mA at 24 V DC
    - Contact resistance: 50 m ohm initial, 100 m ohm after life
    - Insulation resistance: >= 100 M ohm at 100 V DC
    - Dielectric strength: 300 V AC for 60 s
    - Mechanical life: 1000 cycles
    - Operating temperature: -30 to +85 deg C

Circuit diagram (datasheet schematic) - 4 independent SPST switches:

      1 o      o 3      o 5      o 7
        |        |        |        |
        +--/  --+--/  --+--/  --+--/  --+
        |        |        |        |
      2 o      o 4      o 6      o 8

Used on the carrier as the Zynq boot-mode strap selector (SW1..SW4 drive
BOOT_MODE[3:0]). The bottom-row pads (2/4/6/8) tie to GND on the block
sheet; the top-row pads (1/3/5/7) drive the boot strap nets through
10k pull-ups to +3V3.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


DIP_SWITCH_REFCIRCUIT = ReferenceCircuit(
    part_mpn="DS-04P",
    lcsc="C18198092",
    datasheet_url="https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf",
    datasheet_revision="HANBO DS-04P mechanical drawing, Rev A",
    app_circuit_figure="Boot-strap topology: pull-up + DIP-to-GND",
    local_datasheet_path="components/dip_switch/datasheet.pdf",
    app_circuit_page="DS-04P schematic p. 1 + Zynq-7000 TRM Sec 6.3.6 boot-mode strap usage",
    minimum_circuit_verified=True,
    symbol_token="SW_DIP_4",
    footprint="Switch_SMD:DIP_Switch_x4",
    description="4-position SMD SPST DIP switch on 1.27 mm pitch (boot-mode straps)",
    supply_rail="+3V3",
    external_parts=(
        # 10k pull-up per strap line - flipping the switch ON pulls the
        # line to GND, OFF leaves the line high.
        ExternalPart(
            from_pin="SW1",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Zynq-7000 TRM Sec 6.3.6: strap pull-up (>=4.7k, <=20k)",
        ),
        ExternalPart(
            from_pin="SW2",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Zynq-7000 TRM Sec 6.3.6: strap pull-up",
        ),
        ExternalPart(
            from_pin="SW3",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Zynq-7000 TRM Sec 6.3.6: strap pull-up",
        ),
        ExternalPart(
            from_pin="SW4",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Zynq-7000 TRM Sec 6.3.6: strap pull-up",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # The four bottom-row pads tie straight to GND on the block sheet.
        "GND",
    }),
    layout_notes=(
        LayoutNote(
            text="Place the 10k pull-ups within 10 mm of the DIP switch so "
                 "the strap network is short and immune to coupling",
            severity="rule",
            justification="Zynq-7000 TRM Sec 6.3.6: strap timing margin at PS_POR_B release",
        ),
        LayoutNote(
            text="Provide silkscreen labelling (1 / 2 / 3 / 4 and ON marking) "
                 "so the boot mode is visible without instructions",
            severity="rule",
            justification="User-facing component requires legible orientation",
        ),
        LayoutNote(
            text="Route strap traces to the SoM J1 mate via short, direct "
                 "paths - do not loop or share vias with other PS signals",
            severity="guideline",
        ),
        LayoutNote(
            text="Boot straps are latched only at PS_POR_B release - the DIP "
                 "switch is not hot-swappable. Document this in the user guide",
            severity="info",
            justification="Zynq-7000 TRM Sec 6.3.6 timing",
        ),
    ),
)
