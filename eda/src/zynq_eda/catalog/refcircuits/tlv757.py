"""TLV75718/25/33PDBVR - 1A LDO regulators (1.8V / 2.5V / 3.3V fixed).

Datasheet: Texas Instruments TLV757P, Rev Sep 2017
URL: https://www.ti.com/lit/ds/symlink/tlv757p.pdf
Package: SOT-23-5 (DBV)

Three fixed-output LDOs in the TLV757P family used to generate the
selectable VCCO bank supplies for the Zynq SoM. Each VCCO_xx bank rail
has 3 footprints fitted (only ONE populated per bank via 0R jumper):
    - TLV75718 (1.8V)  for LVDS / DDR / 1.8V banks
    - TLV75725 (2.5V)  for SSTL / DCI references
    - TLV75733 (3.3V)  for general-purpose 3.3V GPIO (default)

Pin map (per datasheet):
    1  IN     - Input supply
    2  GND
    3  EN     - Enable input (active high, internal pull-down)
    4  NR/SS  - Noise reduction / soft-start (optional cap to GND)
    5  OUT    - Regulated output
"""

from __future__ import annotations

from scripts.carrier.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)
from scripts.carrier.refcircuits._paths import local_datasheet_path


def _make_tlv757_refcircuit(
    voltage: str,
    mpn: str,
    lcsc: str,
    description: str,
) -> ReferenceCircuit:
    """Common reference-circuit factory for TLV75718/25/33 variants."""
    return ReferenceCircuit(
        part_mpn=mpn,
        lcsc=lcsc,
        datasheet_url="https://www.ti.com/lit/ds/symlink/tlv757p.pdf",
        datasheet_revision="Rev Sep 2017",
        app_circuit_figure="Figure 18 - Typical Application",
        local_datasheet_path=local_datasheet_path(mpn),
        app_circuit_page="p.18, Figure 18",
        minimum_circuit_verified=True,
        symbol_token=mpn,
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        description=description,
        external_parts=(
            ExternalPart(
                from_pin="IN",
                to_net="GND",
                part_token="1u_0402_X7R",
                justification="DS Sec 8.2.2: 1uF input cap",
            ),
            ExternalPart(
                from_pin="OUT",
                to_net="GND",
                part_token="1u_0402_X7R",
                justification="DS Sec 8.2.2: 1uF output cap (min 1uF for stability)",
            ),
            ExternalPart(
                from_pin="OUT",
                to_net="GND",
                part_token="100n_0402_X7R",
                justification="DS Sec 8.2.2: HF bypass on output for transient response",
            ),
            ExternalPart(
                from_pin="EN",
                to_net="IN",
                part_token="100k_0402_1%",
                justification="DS Sec 8.3.3: EN pull-up to IN for always-on (or GPIO control)",
            ),
            ExternalPart(
                from_pin="NR_SS",
                to_net="GND",
                part_token="10n_0402_X7R",
                justification="DS Sec 7.5: 10nF NR/SS cap for low-noise startup (optional but recommended)",
            ),
        ),
        strap_pins=(),
        no_external_required=frozenset(),
        layout_notes=(
            LayoutNote(
                text=f"Place 1uF output cap within 5mm of OUT pin for {voltage} stability",
                severity="rule",
                justification="DS Sec 10.2 Layout",
            ),
        ),
    )


TLV75718_REFCIRCUIT = _make_tlv757_refcircuit(
    voltage="1.8V",
    mpn="TLV75718PDBVR",
    lcsc="C507270",
    description="1.8V 1A LDO (VCCO bank supply, alternate)",
)

TLV75725_REFCIRCUIT = _make_tlv757_refcircuit(
    voltage="2.5V",
    mpn="TLV75725PDBVR",
    lcsc="C2872563",
    description="2.5V 1A LDO (VCCO bank supply, alternate)",
)

TLV75733_REFCIRCUIT = _make_tlv757_refcircuit(
    voltage="3.3V",
    mpn="TLV75733PDBVR",
    lcsc="C485517",
    description="3.3V 1A LDO (VCCO bank supply, default)",
)
