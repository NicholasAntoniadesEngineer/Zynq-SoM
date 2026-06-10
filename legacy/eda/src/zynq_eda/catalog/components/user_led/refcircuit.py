"""YONGYUTAI YLED0603G - Green 0603 SMD LED.

Datasheet: YONGYUTAI YLED0603G LED Diode datasheet, Rev 2.0, distributed
locally as ``components/user_led/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/YONGYUTAI-YLED0603G_C19273151.pdf

A standard 0603 (1.6 x 0.8 x 0.6 mm) green chip LED used on the carrier
as user-facing status indicators (boot LEDs, fault LEDs, etc.).

Electrical characteristics (datasheet Sec 3 + 4, T = 25 deg C):

    Parameter            Symbol  Min  Typ  Max  Unit  Conditions
    Forward voltage      Vf      2.6  --   3.2  V     If = 5 mA
    Peak forward current Ifp     --   --   100  mA    duty <= 0.1, 10 % pulse
    DC forward current   If      --   --   25   mA    derate above 25 deg C
    Reverse voltage      Vr      --   --   5    V
    Wavelength           WLD     510  --   531  nm
    Luminous intensity   Iv      173  --   358  mcd   If = 5 mA
    Half-angle           2theta  --   120  --   deg

Series resistor calculation for a 3.3 V GPIO driving the LED to GND
through a current-limit resistor:

    R_min = (V_gpio - Vf_max) / If_max = (3.3 - 3.2) / 0.025 = 4 ohm  (lower bound)
    R_330 = (3.3 - 2.9) / 0.330k       =  ~1.2 mA       (chosen)
    R_typ = (3.3 - 2.6) / 0.330k       =  ~2.1 mA at Vf_min

330 ohm gives 1.2-2.1 mA which is plenty for a 173-358 mcd green LED
viewed indoors and stays well within the GPIO sink limit (Zynq PL bank
LVCMOS33 sinks ~12 mA per pin). The conservative value extends LED
life and keeps each indicator below the per-pin GPIO drive limit.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


USER_LED_REFCIRCUIT = ReferenceCircuit(
    part_mpn="YLED0603G",
    lcsc="C19273151",
    datasheet_url="https://datasheet.lcsc.com/lcsc/YONGYUTAI-YLED0603G_C19273151.pdf",
    datasheet_revision="YONGYUTAI YLED0603G Rev 2.0, 2022",
    app_circuit_figure="LED + series-R indicator (datasheet Sec 4 'Photoelectric parameters')",
    local_datasheet_path="components/user_led/datasheet.pdf",
    app_circuit_page="YLED0603G p. 2 (electrical) + p. 3 (If vs Vf curve)",
    minimum_circuit_verified=True,
    symbol_token="LED_0603",
    footprint="LED_SMD:LED_0603_1608Metric",
    description="0603 green status LED (Vf 2.6-3.2 V, lambda 510-531 nm) with series-R",
    supply_rail="+3V3",
    external_parts=(
        # Series current-limit resistor. The anode pin of the LED symbol
        # connects to the host GPIO via this 330 ohm resistor.
        ExternalPart(
            from_pin="ANODE",
            to_net="GPIO",
            part_token="330R_0402_1%",
            justification="Limit If to 1.2-2.1 mA at Vf 2.9-2.6 V from a 3.3 V GPIO source",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # Cathode is tied directly to GND on the block sheet.
        "CATHODE",
    }),
    layout_notes=(
        LayoutNote(
            text="Place the series resistor right next to the LED on the same "
                 "layer; keep the GPIO trace from the SoM as direct as possible",
            severity="rule",
            justification="Minimises trace inductance and EMI from GPIO toggling",
        ),
        LayoutNote(
            text="Orient the LED with its anode (marked side) toward the "
                 "series resistor; KiCad footprint pin 2 = cathode",
            severity="rule",
            justification="Polarity reversal: LED will not light",
        ),
        LayoutNote(
            text="Add silkscreen label (e.g. 'D1 - HEARTBEAT') so the LED's "
                 "function is obvious to a user with no schematic",
            severity="guideline",
        ),
        LayoutNote(
            text="If multiple user LEDs are placed in a row, match their "
                 "spacing (e.g. 2 mm pitch) for a clean visual indicator bar",
            severity="info",
        ),
    ),
)
