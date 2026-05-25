"""XUNPU TS-1002S-06026C - 6x6 mm SMD tactile switch.

Datasheet: XUNPU TS-1002S series mechanical drawing, distributed
locally as ``components/tactile_switch/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf

A 6 x 6 mm SMD momentary push-button (4-pin), through-hole metal dome.
The four solder pads form two electrically-common pairs:
pads 1 + 2 share one terminal, pads 3 + 4 share the other. Pressing
the button closes pads 1/2 to pads 3/4.

Electrical highlights (catalog page 1):
    - Rated voltage / current: 12 V DC, 50 mA
    - Contact resistance: <= 100 m ohm
    - Insulation resistance: >= 100 M ohm at 100 V DC
    - Operating force: 160 g (default H=4.3mm) or 260 g (H=4.5mm)
    - Mechanical life: typical 100k cycles
    - Travel: 0.2 +/- 0.1 mm

Circuit diagram (datasheet schematic):

    1 -+        +- 3
       |        |
       +--/  --+
       |        |
    2 -+        +- 4

Used on the carrier as:
  1. PS reset push-button (active-low SRST_N)
  2. Future user inputs (mapped in carrier blocks)

The reference circuit is a host GPIO held high by a pull-up, pulled low
when the button is pressed, with an HF cap to debounce and absorb ESD.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


TACTILE_SWITCH_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TS-1002S-06026C",
    lcsc="C455112",
    datasheet_url="https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf",
    datasheet_revision="XUNPU TS-1002S series mechanical drawing, Rev A",
    app_circuit_figure="Datasheet 'CIRCUIT DIAGRAM' + typical GPIO push-button topology",
    local_datasheet_path="components/tactile_switch/datasheet.pdf",
    app_circuit_page="TS-1002S mechanical p. 1 + typical GPIO debounce topology",
    minimum_circuit_verified=True,
    symbol_token="SW_TACT_6x6",
    footprint="Button_Switch_SMD:SW_SPST_Tactile_6x6mm",
    description="6x6 mm SMD momentary tactile switch (active-low GPIO input)",
    supply_rail="+3V3",
    external_parts=(
        # Pull-up biases the GPIO high while the button is open.
        ExternalPart(
            from_pin="SW",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="GPIO pull-up: button shorts SW to GND when pressed",
        ),
        # 100 nF debounce cap absorbs contact bounce (typically 1-5 ms) and
        # provides an ESD shunt at the user-touch button.
        ExternalPart(
            from_pin="SW",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="Hardware debounce (RC ~ 1 ms with 10k pull-up) + ESD shunt at button face",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # The other two button terminals (the second pad pair) are wired
        # straight to GND on the block sheet (datasheet schematic).
        "GND",
    }),
    layout_notes=(
        LayoutNote(
            text="Place the 100 nF debounce cap within 5 mm of the switch "
                 "so the RC network sees the bounce node directly",
            severity="rule",
            justification="Debounce cap must be local to be effective",
        ),
        LayoutNote(
            text="Place the switch on the carrier edge or top side for user "
                 "access; provide silkscreen labelling (e.g. 'PS_RST')",
            severity="guideline",
        ),
        LayoutNote(
            text="Route the GPIO trace from switch to host SoM as a short, "
                 "low-impedance signal; avoid running it parallel to clocks",
            severity="guideline",
            justification="Tactile switches act as ESD entry points",
        ),
    ),
)
