"""2x7 JTAG header series resistors per Xilinx UG470."""

from __future__ import annotations

from scripts.carrier.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit
from scripts.carrier.refcircuits._paths import local_datasheet_path


JTAG_HEADER_REFCIRCUIT = ReferenceCircuit(
    part_mpn="ZX-PM2.54-2-7PY",
    lcsc="C7499342",
    datasheet_url="https://datasheet.lcsc.com/lcsc/Megastar-ZX-PM2-54-2-7PY_C7499342.pdf",
    datasheet_revision="2022",
    app_circuit_figure="Xilinx UG470 JTAG interface",
    local_datasheet_path=local_datasheet_path("ZX-PM2.54-2-7PY"),
    app_circuit_page="UG470 JTAG direct connection (optional 100R series)",
    minimum_circuit_verified=True,
    symbol_token="JTAG_2x7",
    footprint="Connector_PinHeader_2.54mm:PinHeader_2x07_P2.54mm_Vertical",
    description="2x7 2.54mm JTAG debug header",
    external_parts=(
        ExternalPart(
            from_pin="TCK",
            to_net="PL_TCK",
            part_token="100R_0402_1%",
            justification="UG470: optional 100R series on TCK for ringing control",
        ),
        ExternalPart(
            from_pin="TMS",
            to_net="PL_TMS",
            part_token="100R_0402_1%",
            justification="UG470: optional 100R series on TMS",
        ),
    ),
    layout_notes=(
        LayoutNote(
            text="Keep JTAG traces short; match TCK/TMS series resistor placement",
            severity="guideline",
        ),
    ),
)
