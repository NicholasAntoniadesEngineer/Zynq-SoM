"""USBLC6-4SC6 - Low-capacitance ESD protection for 4 USB 2.0 data lines.

Datasheet: STMicroelectronics USBLC6-2 / USBLC6-4, Rev 5, Oct 2011
URL: https://www.st.com/resource/en/datasheet/usblc6-4.pdf
Package: SOT-23-6L (3.0x1.75mm, 0.95mm pitch)

Monolithic TVS/ESD protection device — four steering-diode pairs to a
shared V_BUS clamp rail (rail-to-rail topology). Each I/O is clamped to
GND on the negative-going pulse and to V_BUS on the positive-going pulse.
Compliant to IEC 61000-4-2 level 4 (15 kV air, 8 kV contact). Line
capacitance C(I/O-GND) typ 2.5 pF (3.5 pF max) -- low enough for USB 2.0
HS (480 Mb/s) without measurable eye degradation.

Pin map (per DS Fig 1):
    1  I/O1  - data line 1 (e.g. USB D+)
    2  GND   - ground reference (return path for negative clamp)
    3  V_BUS - +5V clamp reference rail (anode of positive clamp diodes)
    4  I/O2  - data line 2 (e.g. USB D-)
    5  I/O3  - data line 3
    6  I/O4  - data line 4

On the carrier each USBLC6-4SC6 instance protects one USB 2.0 HS pair
(D+/D-). Pins 5/6 (I/O3, I/O4) are left available for protecting two
additional single-ended lines or wired NC -- the device tolerates floating
I/O pins (DS Sec 2.5 / Fig 14 shows the upstream-transceiver application
with all four lines wired through).

External parts (DS Fig 18 -- PCB Layout Considerations):
    C_BUS  100nF between V_BUS and GND  (DS Fig 18)

That's it. The data lines pass through without series resistors or
DC-blocking caps (the diode steering is intrinsically AC + DC compatible).
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


USBLC6_REFCIRCUIT = ReferenceCircuit(
    part_mpn="USBLC6-4SC6",
    lcsc="C111212",
    datasheet_url="https://www.st.com/resource/en/datasheet/usblc6-4.pdf",
    datasheet_revision="Rev 5, Oct 2011",
    app_circuit_figure="Figure 14 - USB 2.0 port application; Figure 18 - PCB layout",
    local_datasheet_path="components/usblc6/datasheet.pdf",
    app_circuit_page="p.8 Fig 14 (application) + p.9 Fig 18 (layout / C_BUS)",
    minimum_circuit_verified=True,
    symbol_token="USBLC6-4SC6",
    footprint="Package_TO_SOT_SMD:SOT-23-6",
    description="USB 2.0 / 480 Mb/s ESD protection, 4 lines, SOT-23-6L",
    external_parts=(
        # V_BUS (pin 3) is the +5V clamp reference rail; it requires a
        # local 100nF decoupling cap close to the device per DS Fig 18.
        ExternalPart(
            from_pin="VBUS",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 18 C_BUS: 100nF V_BUS decoupling (PCB layout)",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # Each I/O pin is a pure pass-through with internal diode steering;
        # no external R, C, or pull required on any data line.
        "I/O1", "I/O2", "I/O3", "I/O4",
    }),
    layout_notes=(
        LayoutNote(
            text=(
                "Place USBLC6 within 5mm of the USB connector on the data-line "
                "side -- the ESD protection MUST sit between the connector and "
                "the device being protected (DS Sec 2.3: 'put the protection "
                "device as close as possible to the disturbance source')"
            ),
            severity="rule",
            justification="DS Sec 2.3 / Fig 7 (optimised layout) + Fig 8",
        ),
        LayoutNote(
            text=(
                "Route USB D+/D- THROUGH the USBLC6 pads (tee-stub branch is "
                "unacceptable). The data line enters on one side of the SOT-23-6 "
                "and exits on the other; do not place the device on a stub off "
                "the main pair (DS Sec 2.3 Fig 7 'unsuitable layout' vs "
                "'optimised layout')"
            ),
            severity="rule",
            justification="DS Fig 7 (layout optimisation)",
        ),
        LayoutNote(
            text=(
                "Maintain 90 ohm differential impedance through the USBLC6 "
                "footprint. Length-match D+/D- through the package (the 0.04 pF "
                "C(I/O-I/O) typ value keeps the imbalance under USB 2.0 spec)"
            ),
            severity="rule",
            justification="USB 2.0 Sec 7.1.6 + DS Table 2 (line capacitance)",
        ),
        LayoutNote(
            text=(
                "Tie the GND pin (pin 2) directly to the PCB GND plane with the "
                "shortest possible trace -- the negative-going clamp current "
                "returns here, and L_GND.di/dt adds directly to the clamp "
                "voltage seen by the protected line (DS Sec 2.2)"
            ),
            severity="rule",
            justification="DS Sec 2.2 (overvoltage due to parasitic inductances)",
        ),
        LayoutNote(
            text=(
                "Tie the V_BUS pin (pin 3) to the USB +5V (or +VIN) rail through "
                "the shortest possible trace; the positive clamp diodes shunt to "
                "V_BUS, so L_VBUS in series with C_BUS hurts response time. "
                "The 100nF C_BUS cap should be within 2mm of pin 3"
            ),
            severity="rule",
            justification="DS Sec 2.2 + Fig 18",
        ),
    ),
)
