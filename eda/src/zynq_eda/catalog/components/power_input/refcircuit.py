"""Power input protection and bulk decoupling at +VIN entry."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


POWER_INPUT_REFCIRCUIT = ReferenceCircuit(
    part_mpn="SS14",
    lcsc="C83852",
    datasheet_url="https://datasheet.lcsc.com/lcsc/ON-Semicon-SS14_C83852.pdf",
    datasheet_revision="Rev 2020",
    app_circuit_figure="Typical reverse-polarity + bulk input network",
    local_datasheet_path="components/power_input/datasheet.pdf",
    app_circuit_page="p.3, Schottky reverse protection",
    minimum_circuit_verified=True,
    symbol_token="SS14",
    footprint="Diode_SMD:D_SMA",
    description="Reverse-polarity Schottky + bulk caps at +VIN input",
    supply_rail="+VIN",
    external_parts=(
        ExternalPart(
            from_pin="ANODE",
            to_net="+VIN_IN",
            part_token="schottky_SS14",
            justification="Reverse polarity protection at carrier input",
        ),
        ExternalPart(
            from_pin="CATHODE",
            to_net="+VIN",
            part_token="100u_1206_X5R",
            justification="Bulk input cap after Schottky (10uF min per LDO apps)",
        ),
        ExternalPart(
            from_pin="CATHODE",
            to_net="+VIN",
            part_token="100n_0402_X7R",
            justification="HF bypass at protected +VIN rail",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Place Schottky close to input connector; bulk cap within 5mm of downstream LDOs",
            severity="rule",
        ),
    ),
)
