"""TPS2051CDBVR - USB current-limited power switch (active-high enable).

Datasheet: Texas Instruments TPS20xxC / TPS20xxC-2, SLVSAU6H, June 2011 - Revised April 2016
URL: https://www.ti.com/lit/ds/symlink/tps2051c.pdf
Package: SOT-23-5 (DBV, 5-pin)

USB VBUS load switch with 0.5 A current limit, soft-start, reverse
current blocking, thermal protection, and a deglitched open-drain
overcurrent / overtemp fault flag. Used to source +5 V VBUS to the
USB-OTG receptacle from the carrier's +VIN rail under STM32 firmware
control; the switch protects against downstream shorts and over-load
without bringing down the rest of the board.

The 'C' suffix denotes the **active-high enable** variant (per DS
Sec 5 Device Comparison Table, p.4):
    * TPS2041C: EN low (logic-low enable), 0.5 A
    * TPS2051C: EN high (logic-high enable), 0.5 A <-- this part
    * TPS2061C / TPS2068C / TPS2069C: 1.0 / 1.5 / 1.5 A variants

Pin map (DBV / SOT-23-5, per DS Sec 6 Pin Configuration and Functions, p.4):
    1  OUT    - Power-switch output, connect to load (USB VBUS)
    2  GND    - Ground connection
    3  ~FLT   - Active-low open-drain fault flag (OC or OT)
    4  EN     - Logic-high enable (TPS2051C variant)
    5  IN     - Input supply / power-switch drain (4.5 - 5.5 V)

Min circuit (DS Fig 23 Typical Application + Sec 9.2.2.1 + Sec 11 Layout):
    * 0.1 uF on IN -> GND (close to IC)
    * 1 uF .. 150 uF on OUT -> GND (120-150 uF for USB-2.0 std VBUS)
    * 10 kOhm pull-up on ~FLT -> 3V3 (open-drain output)
    * EN driven by host GPIO (must not be left open)
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


TPS2051_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TPS2051CDBVR",
    lcsc="C129581",
    datasheet_url="https://www.ti.com/lit/ds/symlink/tps2051c.pdf",
    datasheet_revision="SLVSAU6H, Jun 2011 - Rev Apr 2016",
    app_circuit_figure="Figure 23 - Typical Application Schematic",
    local_datasheet_path="components/tps2051/datasheet.pdf",
    app_circuit_page="p.17, Figure 23",
    minimum_circuit_verified=True,
    symbol_token="TPS2051CDBVR",
    footprint="Package_TO_SOT_SMD:SOT-23-5",
    description="USB current-limited load switch, 0.5 A, active-high enable, SOT-23-5",
    supply_rail="+VIN",
    external_parts=(
        # Input cap (DS Sec 9.2.2.1: 0.1 uF or greater ceramic; the typical
        # application schematic on p.17 shows 0.1 uF). We use 1 uF for
        # better high-frequency decoupling at the switching node since the
        # power-switch turn-on rise time can excite cable inductance ringing.
        ExternalPart(
            from_pin="IN",
            to_net="GND",
            part_token="1u_0402_X7R",
            justification="DS Sec 9.2.2.1 + Fig 23: 0.1 uF min on IN (we use 1 uF for transient/inrush headroom)",
        ),
        # Additional HF bypass on IN matching the DS Fig 23 0.1 uF value.
        ExternalPart(
            from_pin="IN",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="DS Fig 23 + Sec 11 Layout: 0.1 uF ceramic close to IN/GND pins",
        ),
        # Output cap (DS Sec 9.2.2.1: 120-150 uF recommended for USB 2.0
        # VBUS standard compliance; 1-22 uF acceptable for non-USB-std
        # applications; 10 uF minimum if low input inductance). We use a
        # 100 uF 1206 to meet USB-2.0 VBUS capacitance with margin.
        ExternalPart(
            from_pin="OUT",
            to_net="GND",
            part_token="100u_1206_X5R",
            justification="DS Sec 9.2.2.1 + Fig 23: 120-150 uF for USB-2.0 VBUS; 100 uF 1206 carries the standard with derating",
        ),
        # HF bypass on OUT for downstream USB transient response.
        ExternalPart(
            from_pin="OUT",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="HF bypass on OUT for USB transient response (complements bulk cap)",
        ),
        # ~FLT pull-up to +3V3 (open-drain output asserted active-low
        # during OC / OT condition). 10k is the typical R_FAULT shown in
        # DS Fig 23.
        ExternalPart(
            from_pin="~{FLT}",
            to_net="+3V3",
            part_token="10k_0402_1%",
            justification="DS Sec 8.3.5 + Fig 23: ~FLT is open-drain, 10k pull-up to logic supply",
        ),
    ),
    strap_pins=(),
    # EN is driven by host GPIO (STM32_USBOTG_VBUS_EN) -- declare it
    # in pin_net_overrides so the auto-NC pass doesn't NC it.
    pin_net_overrides=(
        ("EN", "STM32_USBOTG_VBUS_EN"),
        ("~{FLT}", "STM32_USBOTG_OC_N"),
    ),
    no_external_required=frozenset(),
    layout_notes=(
        LayoutNote(
            text=(
                "Place the 0.1 uF input bypass cap near the IN and GND pins "
                "with a low-inductance trace"
            ),
            severity="rule",
            justification="DS Sec 11.1 Layout Guidelines #1",
        ),
        LayoutNote(
            text=(
                "Place the >= 10 uF output cap near the OUT and GND pins with "
                "a low-inductance trace (a 120-150 uF bulk is required for "
                "USB 2.0 VBUS standard compliance)"
            ),
            severity="rule",
            justification="DS Sec 11.1 Layout Guidelines #2 + USB 2.0 VBUS spec",
        ),
        LayoutNote(
            text=(
                "Add copper pour around the device on both sides of the "
                "SOT-23-5 to spread heat (DS Sec 11.3: theta_JA depends "
                "strongly on PCB copper area at the 0.5 A rated current)"
            ),
            severity="guideline",
            justification="DS Sec 11.3 Power Dissipation and Junction Temperature",
        ),
        LayoutNote(
            text=(
                "EN must not be left floating -- the input is driven directly "
                "from a STM32 GPIO. Keep the EN trace short to avoid noise "
                "coupling into the enable network at switch turn-on"
            ),
            severity="rule",
            justification="DS Sec 8.3.2 Enable: enable must not be left open",
        ),
    ),
)
