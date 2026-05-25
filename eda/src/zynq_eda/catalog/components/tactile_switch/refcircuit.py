"""Tactile switch with pull-up and debounce capacitor."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, ReferenceCircuit


TACTILE_SWITCH_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TS-1002S-06026C",
    lcsc="C455112",
    datasheet_url="https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf",
    datasheet_revision="2021",
    app_circuit_figure="Typical tact switch to GPIO",
    local_datasheet_path="components/tactile_switch/datasheet.pdf",
    app_circuit_page="Switch DS + debounce cap to GND",
    minimum_circuit_verified=True,
    symbol_token="SW_TACT_6x6",
    footprint="Button_Switch_SMD:SW_SPST_Tactile_6x6mm",
    description="6x6mm tactile switch with pull-up and debounce",
    supply_rail="+3V3",
    external_parts=(
        ExternalPart(
            from_pin="SW",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="Pull-up: switch active-low to GND",
        ),
        ExternalPart(
            from_pin="SW",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="Debounce / ESD shunt at switch node",
        ),
    ),
)
