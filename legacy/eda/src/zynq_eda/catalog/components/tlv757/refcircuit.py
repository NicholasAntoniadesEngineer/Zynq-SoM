"""TLV75718/25/33PDBVR - 1A LDO regulators (1.8V / 2.5V / 3.3V fixed).

Datasheet: Texas Instruments TLV757P, SBVS322C, October 2017 - Revised March 2024
URL: https://www.ti.com/lit/ds/symlink/tlv757p.pdf
Package: SOT-23-5 (DBV)

Three fixed-output LDOs in the TLV757P family used to generate the
carrier's regulated rails from +VIN (5V from USB-C):
    - TLV75718 (1.8V)  used for FPGA 1.8V banks and 1.8V peripherals
    - TLV75725 (2.5V)  used for SSTL/DCI references
    - TLV75733 (3.3V)  used for the main +3V3 carrier rail (default)

Pin map (DBV / SOT-23-5, per DS Table 4-1):
    1  IN     - Input supply (1.45 - 5.5 V)
    2  GND
    3  EN     - Enable input (V_HI >= 1V to enable, V_LO <= 0.3V to disable)
    4  NC     - No internal connection (DS Table 4-1)
    5  OUT    - Regulated output (0.6 - 5 V, 1A continuous)

Minimum-circuit summary (per DS Sec 7.1.1 + Fig 7-4 Typical Application):
    * Cin  = 1 uF (>= 0.47 uF effective after DC bias derating) on IN
    * Cout = 1 uF (>= 0.47 uF effective) on OUT; max 200 uF
    * EN  pin must be driven (must not be left open). Pulled high to IN
      for always-on; otherwise tied to host GPIO.

The TLV757P has NO NR/SS pin -- pin 4 is NC. (The earlier TLV757x
non-P family had NR/SS; the P variant we use here does not. The KiCad
symbol Regulator_Linear:TLV75xxxPDBV correctly reflects pin 4 = NC.)
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


_VARIANT_DATASHEET = {
    "TLV75718PDBVR": "components/tlv757/tlv75718.pdf",
    "TLV75725PDBVR": "components/tlv757/tlv75725.pdf",
    "TLV75733PDBVR": "components/tlv757/tlv75733.pdf",
}


def _make_tlv757_refcircuit(
    voltage: str,
    mpn: str,
    lcsc: str,
    description: str,
) -> ReferenceCircuit:
    """Common reference-circuit factory for TLV75718/25/33 variants.

    All three variants share an identical external-component network --
    they differ only in regulated output voltage and the per-variant
    datasheet PDF (SBVS322C covers the whole family).
    """
    return ReferenceCircuit(
        part_mpn=mpn,
        lcsc=lcsc,
        datasheet_url="https://www.ti.com/lit/ds/symlink/tlv757p.pdf",
        datasheet_revision="SBVS322C, Oct 2017 - Rev Mar 2024",
        app_circuit_figure="Figure 7-4 - TLV757P Typical Application",
        local_datasheet_path=_VARIANT_DATASHEET[mpn],
        app_circuit_page="p.19, Figure 7-4",
        minimum_circuit_verified=True,
        symbol_token=mpn,
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        description=description,
        supply_rail="+VIN",
        external_parts=(
            # Input cap (DS Sec 7.1.1, Fig 7-4). Datasheet calls for >= 1 uF on
            # IN; we use a single ceramic 1 uF X7R 0402 close to pin 1.
            ExternalPart(
                from_pin="IN",
                to_net="GND",
                part_token="1u_0402_X7R",
                justification="DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic input cap close to pin 1",
            ),
            # Output cap (DS Sec 7.1.1, Fig 7-4). Datasheet requires >= 1 uF on
            # OUT for stability across the full V_OUT range; 1 uF X7R 0402
            # gives ~0.5 uF after 50% derating (DS Note 1) which still meets
            # the >= 0.47 uF effective requirement.
            ExternalPart(
                from_pin="OUT",
                to_net="GND",
                part_token="1u_0402_X7R",
                justification="DS Sec 7.1.1 + Fig 7-4: 1 uF ceramic output cap (>= 0.47 uF effective for stability)",
            ),
            # HF bypass on OUT (not in DS Fig 7-4 minimum, but standard
            # practice and recommended in DS Sec 7.4.1 layout to place
            # output caps as close as possible to the device).
            ExternalPart(
                from_pin="OUT",
                to_net="GND",
                part_token="100n_0402_X7R",
                justification="Additional HF bypass on output for transient response (complements 1 uF bulk)",
            ),
            # EN pin pull-up to IN keeps the LDO always-on. DS Sec 6.4.1
            # requires V_EN >= V_HI (1V min) for normal operation; pulling
            # to IN through 100k guarantees that with negligible standby
            # current (V_IN/100k <= 55 uA at 5.5V). Replace this 100k with
            # a GPIO drive when sequencing is required.
            ExternalPart(
                from_pin="EN",
                to_net="IN",
                part_token="100k_0402_1%",
                justification="DS Sec 6.4.1: EN pull-up to IN for always-on (V_EN >= V_HI = 1V); replace with GPIO for sequencing",
            ),
        ),
        strap_pins=(),
        # Pin 4 = NC per DS Table 4-1. KiCad symbol marks it pin_type
        # no_connect already (and hides it); we still list it explicitly
        # so the auto-NC pass leaves it alone.
        no_external_required=frozenset({"NC"}),
        layout_notes=(
            LayoutNote(
                text=(
                    f"Place 1 uF input and 1 uF output caps within 5 mm of "
                    f"pins 1 (IN) and 5 (OUT) respectively for {voltage} stability"
                ),
                severity="rule",
                justification="DS Sec 7.4.1 Layout Guidelines",
            ),
            LayoutNote(
                text=(
                    "Use a copper ground plane under the LDO and add thermal "
                    "vias around the device to distribute heat (P_D = (V_IN - V_OUT) * I_OUT)"
                ),
                severity="guideline",
                justification="DS Sec 7.4.1 + Sec 7.1.5 Power Dissipation",
            ),
            LayoutNote(
                text=(
                    "Keep IN trace short and low-impedance; if the input source "
                    "is more than a few inches away, add additional bulk input "
                    "capacitance in parallel with the 1 uF ceramic"
                ),
                severity="guideline",
                justification="DS Sec 7.3 Power Supply Recommendations",
            ),
        ),
    )


TLV75718_REFCIRCUIT = _make_tlv757_refcircuit(
    voltage="1.8V",
    mpn="TLV75718PDBVR",
    lcsc="C507270",
    description="1.8V 1A LDO (FPGA 1.8V bank supply, SOT-23-5)",
)

TLV75725_REFCIRCUIT = _make_tlv757_refcircuit(
    voltage="2.5V",
    mpn="TLV75725PDBVR",
    lcsc="C2872563",
    description="2.5V 1A LDO (SSTL/DCI reference supply, SOT-23-5)",
)

TLV75733_REFCIRCUIT = _make_tlv757_refcircuit(
    voltage="3.3V",
    mpn="TLV75733PDBVR",
    lcsc="C485517",
    description="3.3V 1A LDO (main +3V3 carrier rail, SOT-23-5)",
)
