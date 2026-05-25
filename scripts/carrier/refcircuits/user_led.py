"""User GPIO LED with series resistor."""

from __future__ import annotations

from scripts.carrier.model.refcircuit import ExternalPart, ReferenceCircuit
from scripts.carrier.refcircuits._paths import local_datasheet_path


USER_LED_REFCIRCUIT = ReferenceCircuit(
    part_mpn="YLED0603G",
    lcsc="C19273151",
    datasheet_url="https://datasheet.lcsc.com/lcsc/YONGYUTAI-YLED0603G_C19273151.pdf",
    datasheet_revision="2022",
    app_circuit_figure="Typical GPIO LED indicator",
    local_datasheet_path=local_datasheet_path("YLED0603G"),
    app_circuit_page="LED DS: If=5mA at 2V with 330R from 3.3V",
    minimum_circuit_verified=True,
    symbol_token="LED_0603",
    footprint="LED_SMD:LED_0603_1608Metric",
    description="0603 user status LED with series resistor",
    supply_rail="+3V3",
    external_parts=(
        ExternalPart(
            from_pin="ANODE",
            to_net="GPIO",
            part_token="330R_0402_1%",
            justification="Limit LED current to ~3mA from 3.3V GPIO",
        ),
    ),
    no_external_required=frozenset({"CATHODE"}),
)
