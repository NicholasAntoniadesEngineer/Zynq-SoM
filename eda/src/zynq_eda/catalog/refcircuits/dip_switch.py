"""4-position DIP switch with pull resistors for boot mode straps."""

from __future__ import annotations

from scripts.carrier.model.refcircuit import ExternalPart, ReferenceCircuit
from scripts.carrier.refcircuits._paths import local_datasheet_path


DIP_SWITCH_REFCIRCUIT = ReferenceCircuit(
    part_mpn="DS-04P",
    lcsc="C18198092",
    datasheet_url="https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf",
    datasheet_revision="2020",
    app_circuit_figure="Boot mode strap switches",
    local_datasheet_path=local_datasheet_path("DS-04P"),
    app_circuit_page="Zynq boot mode: pull-up on each strap bit",
    minimum_circuit_verified=True,
    symbol_token="SW_DIP_4",
    footprint="Switch_SMD:DIP_Switch_x4",
    description="4-position 1.27mm DIP boot mode switch",
    supply_rail="+3V3",
    external_parts=(
        ExternalPart(
            from_pin="SW1",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Boot strap bit 0 pull-up (switch to GND when ON)",
        ),
        ExternalPart(
            from_pin="SW2",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Boot strap bit 1 pull-up",
        ),
        ExternalPart(
            from_pin="SW3",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Boot strap bit 2 pull-up",
        ),
        ExternalPart(
            from_pin="SW4",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Boot strap bit 3 pull-up",
        ),
    ),
)
