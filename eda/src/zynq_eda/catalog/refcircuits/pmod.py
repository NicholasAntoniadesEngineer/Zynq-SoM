"""Digilent PMOD 2x6 right-angle header."""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import LayoutNote, ReferenceCircuit
from zynq_eda.catalog.refcircuits._paths import local_datasheet_path


PMOD_REFCIRCUIT = ReferenceCircuit(
    part_mpn="PM254R-12-08-H85",
    lcsc="C53026548",
    datasheet_url="https://datasheet.lcsc.com/lcsc/XFCN-PM254R-12-08-H85_C53026548.pdf",
    datasheet_revision="2023",
    app_circuit_figure="Digilent PMOD Interface Specification Rev E",
    local_datasheet_path=local_datasheet_path("PM254R-12-08-H85"),
    app_circuit_page="PMOD Spec Sec 2: 3.3V I/O, no mandatory passives",
    minimum_circuit_verified=True,
    symbol_token="PMOD_2x6_RA",
    footprint="Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical",
    description="PMOD 2x6 right-angle expansion header",
    supply_rail="+3V3",
    external_parts=(),
    no_external_required=frozenset({"IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7"}),
    layout_notes=(
        LayoutNote(
            text="PMOD pins are 3.3V LVCMOS; do not drive 5V",
            severity="rule",
            justification="Digilent PMOD Spec",
        ),
    ),
)
