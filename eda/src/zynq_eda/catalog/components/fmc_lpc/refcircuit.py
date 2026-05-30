"""Hirose FX10A-168P-SV(91) - 168-position 0.5 mm stacking connector.

Datasheet: Hirose FX10 series catalog (2016-12, rev 4), distributed
locally as ``components/fmc_lpc/datasheet.pdf``. URL:
https://www.hirose.com/en/product/document?clcode=CL0681-2024-7-91&productname=FX10A-168P-SV(91)&series=FX10A

FX10A is Hirose's "15+ Gbps 0.5 mm stacking" family. The 168-position
variant has no ground plate but provides 168 single-ended contacts.

On this carrier we treat the FX10A pair as a generic high-density
mezzanine-style mate to the SoM and project the *VITA 57.1 LPC FMC*
pinout on top of it — so an off-the-shelf FMC LPC daughtercard can
plug into the carrier. The pinout assignment itself lives in
``projects/carrier/blocks/fmc_lpc.py``; this refcircuit declares only
the decoupling network required at the connector body.

VITA 57.1 LPC mandates 100 nF per VCC pin group + a bulk cap at the
connector. The standard does not specify a value for the bulk cap; we
use 10 uF as a common industry default.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


FMC_LPC_REFCIRCUIT = ReferenceCircuit(
    part_mpn="FX10A-168P-SV(91)",
    lcsc="C6624664",
    datasheet_url=(
        "https://www.hirose.com/en/product/document?"
        "clcode=CL0681-2024-7-91&productname=FX10A-168P-SV(91)&series=FX10A"
    ),
    datasheet_revision="Hirose FX10 series catalog, 2016-12 rev 4",
    app_circuit_figure="FX10A catalog mating spec + VITA 57.1 LPC carrier decoupling guidance",
    local_datasheet_path="components/fmc_lpc/datasheet.pdf",
    app_circuit_page="FX10 catalog pp. 3-5 (mating dims) + VITA 57.1 Sec 5.3 (FMC power)",
    minimum_circuit_verified=True,
    symbol_token="FMC_LPC_168P",
    footprint="Connector_FFC-FPC:FX10A-168P-SV1",
    description="Hirose FX10A 168-pin 0.5 mm SoM-mate connector (carries VITA 57.1 LPC pinout)",
    supply_rail="+3V3",
    external_parts=(
        # Decoupling/pull-ups attach to the FMC connector's REAL designator
        # pins (the generated bank symbol exposes mechanical designators
        # C/D/G/H, not logical rail names). These live on the
        # FMC_LPC_PWR_CLK_JTAG bank (J4C); the SoM J1/J2/J3 banks carry no
        # C/D designators, so each part lands exactly once. The J4C
        # ConnectorInstance sets decoupling_array=True, so these are drawn
        # as a labelled cap bank in open space (not clustered on the dense
        # adjacent power pins). Per-power-pin 100nF + per-rail 10u bulk
        # (VITA 57.1 Sec 5.3); designators verified vs connector_banks.py +
        # fmc_lpc_power_clk_jtag.py pin_to_net.
        *(
            ExternalPart(
                from_pin=p, to_net="GND", part_token="100n_0402_X7R",
                justification="VITA 57.1 Sec 5.3: 100nF per +3V3 carrier-side pin",
            )
            for p in ("C39", "D36", "D38", "D40")
        ),
        *(
            ExternalPart(
                from_pin=p, to_net="GND", part_token="100n_0402_X7R",
                justification="VITA 57.1 Sec 5.3: 100nF per VADJ carrier-side pin",
            )
            for p in ("C36", "C38", "C40", "D35", "D37", "D39")
        ),
        *(
            ExternalPart(
                from_pin=p, to_net="GND", part_token="100n_0402_X7R",
                justification="VITA 57.1 Sec 5.3: 100nF per +12V carrier-side pin",
            )
            for p in ("C35", "C37")
        ),
        ExternalPart(
            from_pin="C39", to_net="GND", part_token="10u_0603_X7R",
            justification="VITA 57.1 Sec 5.3: bulk decoupling for +3V3 at FMC connector",
        ),
        ExternalPart(
            from_pin="C36", to_net="GND", part_token="10u_0603_X7R",
            justification="VITA 57.1 Sec 5.3: bulk decoupling for VADJ at FMC connector",
        ),
        #
        # Management I2C pull-ups. VITA 57.1 LPC pins C30 (SCL) and C31 (SDA)
        # are 3.3V open-drain — the carrier owns the pull-ups.
        ExternalPart(
            from_pin="C30",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="VITA 57.1 Sec 7: FMC management I2C SCL pull-up (carrier-owned)",
        ),
        ExternalPart(
            from_pin="C31",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="VITA 57.1 Sec 7: FMC management I2C SDA pull-up (carrier-owned)",
        ),
        # PRSNT_M2C_L (pin H2) - daughtercard pulls low when seated.
        # Carrier needs a pull-up so an empty socket reads high.
        ExternalPart(
            from_pin="H2",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="VITA 57.1 Sec 5.4: PRSNT_M2C_L pull-up on carrier (active-low)",
        ),
    ),
    strap_pins=(),
    layout_notes=(
        LayoutNote(
            text="Decouple each FMC VCC/VADJ pin group within 3 mm of the connector body",
            severity="rule",
            justification="VITA 57.1 Sec 5.3: LPC carrier power-integrity requirement",
        ),
        LayoutNote(
            text="Route LA pairs as 100 ohm differential, intra-pair length match within "
                 "0.1 mm, inter-pair within 1 mm of the slowest pair",
            severity="rule",
            justification="VITA 57.1 Sec 5.5.2: LA pair signal integrity",
        ),
        LayoutNote(
            text="Route CLK0_M2C/CLK1_M2C as 100 ohm differential clock pairs; keep "
                 "trace length <= 50 mm and avoid layer changes",
            severity="rule",
            justification="VITA 57.1 Sec 5.5.3: clock distribution requirement",
        ),
        LayoutNote(
            text="VADJ supply must be remotely sensible from the FMC daughtercard "
                 "(see VITA 57.1 Sec 5.3.4); on this carrier VADJ is hard-tied to "
                 "+1V8 (no auto-negotiation supported)",
            severity="info",
            justification="Carrier-specific decision: fixed VADJ = +1V8",
        ),
        LayoutNote(
            text="Provide multiple ground vias under the connector body for "
                 "return-current control on the high-speed pairs",
            severity="rule",
            justification="VITA 57.1 Sec 5.5: signal-integrity practice",
        ),
    ),
)
