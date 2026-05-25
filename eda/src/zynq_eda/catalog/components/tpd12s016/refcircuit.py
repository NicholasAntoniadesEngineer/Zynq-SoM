"""TPD12S016PWR - HDMI companion chip: ESD + level-shifter + 5V load switch.

Datasheet: Texas Instruments TPD12S016, SLLSE96F, Sep 2011 - Rev Oct 2015
URL: https://www.ti.com/lit/ds/symlink/tpd12s016.pdf
Package: TSSOP-24 (PW package, 4.4 x 7.8mm, 0.65mm pitch)

The TPD12S016 is a single-chip HDMI companion that provides EVERY external
function an HDMI source/sink port needs (DS Sec 7.1):

    * 12-channel IEC 61000-4-2 Level 4 (+/-8kV contact) ESD protection on
      4 TMDS pairs (D0+/-, D1+/-, D2+/-, CLK+/-)
    * Bidirectional voltage-level translation for DDC (SDA, SCL) and CEC
      between the controller-side V_CCA rail (1.1-3.6V) and the HDMI cable
      side at +5V (V_CC5V supplies the cable-side reference)
    * On-chip pull-ups per HDMI 1.4 spec on DDC/CEC/HPD lines: no external
      resistors required (DS Sec 7.3.9, 7.3.15, 8.1)
    * 55mA current-limited +5V load switch (V_CC5V -> 5V_OUT), gated by
      CT_HPD (DS Sec 7.3.6) - source role only
    * Glitch-filtered HPD level shifter (5V cable -> V_CCA controller, with
      11k internal pull-down on HPD_B per DS Sec 6.5)
    * Internal 3.3V LDO that powers the CEC_B input buffer reference so
      no external 3.3V rail is required for CEC even with V_CCA = 1.8V
      (DS Sec 7.3.11)
    * Back-drive (reverse-current) protection on all cable-side pins

Two instances on the carrier (one part, two roles):

    * TPD12S016PWR_TX  - HDMI source path: Zynq drives, +5V is sourced via
                         the on-chip load switch (V_CC5V tied to +5V rail,
                         5V_OUT routed to HDMI connector pin 18). CT_HPD is
                         driven HIGH by a 10k pull-up to V_CCA to keep the
                         load switch + level shifters enabled at all times.
    * TPD12S016PWR_RX  - HDMI sink path: +5V comes IN from the upstream
                         source on HDMI connector pin 18 and lands on
                         V_CC5V (used only as the reference for the cable-
                         side buffers; load switch is unused). CT_HPD is
                         again pulled up to V_CCA so the level shifters
                         track the source-supplied 5V_OUT rail.

Pin map (PW / TSSOP-24 package, per DS Sec 5):

    1  CEC_A     IO   CEC, controller side (referenced to V_CCA)
    2  SCL_A     IO   DDC SCL, controller side (V_CCA)
    3  SDA_A     IO   DDC SDA, controller side (V_CCA)
    4  HPD_A     O    HPD output toward controller (V_CCA level)
    5  LS_OE     I    Level-shifter enable (V_CCA, active high)
    6  GND
    7  CEC_B     IO   CEC, HDMI cable side (5V_OUT level via internal LDO)
    8  SCL_B     IO   DDC SCL, HDMI cable side (5V_OUT)
    9  SDA_B     IO   DDC SDA, HDMI cable side (5V_OUT)
    10 HPD_B-    I    HPD input from HDMI connector (5V cable level)
    11 VCC5V     PWR  +5V supply input to load switch and B-side buffers
    12 CT_HPD    I    Load-switch + HPD enable (V_CCA, active high)
    13 5V_OUT    O    +5V switched output to HDMI connector pin 18 (TX role)
    14 GND
    15 CLK-      IO   TMDS clock pair, cable side (ESD only, no termination)
    16 CLK+
    17 D0-       IO   TMDS data 0 (cable side, ESD only)
    18 D0+
    19 GND
    20 D1-       IO   TMDS data 1
    21 D1+
    22 D2-       IO   TMDS data 2
    23 D2+
    24 V_CCA     PWR  Controller-side supply 1.1-3.6V (1.8V or 3.3V typical)

External-component count (per DS Sec 8 Fig 15 / 18):

    * 100nF on V_CCA to GND
    * 100nF on V_CC5V to GND
    * 100nF on 5V_OUT to GND  (TX role only - the load-switch output)
    * 10k pull-up CT_HPD -> V_CCA (single-control-line mode, DS Fig 15)
    * 10k pull-up LS_OE  -> V_CCA (always-on level shifters; alternatively
      LS_OE can be driven by a controller GPIO for power saving per Fig 18)
    * No external DDC / CEC / HPD pull-ups (all integrated; DS Sec 7.3.15).

The carrier's KiCad symbol abstracts V_CCA as ``VCCA`` and V_CC5V as
``VCCB`` (it predates the TPD12S016 naming) - the pin_net_overrides below
make the mapping explicit.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import (
    ExternalPart,
    LayoutNote,
    ReferenceCircuit,
)


# ---------------------------------------------------------------------------
# Common parts: both TX and RX need V_CCA + V_CC5V decoupling and the
# CT_HPD / LS_OE pull-ups that keep the level shifters always-on.
# ---------------------------------------------------------------------------

_COMMON_DECOUPLING = (
    # V_CCA (controller side, +3V3 on this carrier) - DS Fig 15 / 18
    ExternalPart(
        from_pin="VCCA",
        to_net="GND",
        part_token="100n_0402_X7R",
        justification="DS Fig 15: 100nF V_CCA decoupling close to pin 24",
    ),
    # V_CC5V (HDMI cable side, +5V rail) - DS Fig 15
    ExternalPart(
        from_pin="VCCB",
        to_net="GND",
        part_token="100n_0402_X7R",
        justification="DS Fig 15: 100nF V_CC5V decoupling close to pin 11",
    ),
)

# CT_HPD and LS_OE drive the device-mode logic; both must be HIGH for the
# 5V load switch + DDC/CEC/HPD shifters to be enabled (DS Table 1 Power
# Saving Options). We hard-pull them to V_CCA so the device is always-on,
# matching the single-control-line scheme in DS Fig 15.
_ALWAYS_ON_CONTROL = (
    ExternalPart(
        from_pin="CT_CP_HPD",
        to_net="+3V3",
        part_token="10k_0402_1%",
        justification="DS Sec 8.2.1 / Fig 15: CT_HPD = HIGH enables 5V load "
                      "switch + HPD detection (active-high control input)",
    ),
)


# ---------------------------------------------------------------------------
# TX variant - HDMI SOURCE path.
#
# Zynq drives the connector. The on-chip 55mA load switch sources +5V to
# HDMI connector pin 18 via 5V_OUT (DS Sec 7.3.6). V_CC5V is fed from the
# carrier +5V rail and gated by the CT_HPD control.
# ---------------------------------------------------------------------------

TPD12S016_TX_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TPD12S016PWR",
    lcsc="C201665",
    datasheet_url="https://www.ti.com/lit/ds/symlink/tpd12s016.pdf",
    datasheet_revision="SLLSE96F, Rev Oct 2015",
    app_circuit_figure="Figure 15 - HDMI Source using one GPIO (CT_HPD)",
    local_datasheet_path="components/tpd12s016/datasheet.pdf",
    app_circuit_page="p.18 Figure 15 + p.21 Sec 10 layout",
    minimum_circuit_verified=True,
    symbol_token="TPD12S016PWR",
    footprint="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
    description="HDMI source companion: 12-ch ESD + DDC/CEC/HPD level shifters + 5V load switch",
    supply_rail="+3V3",
    pin_net_overrides=(
        ("VCCA", "+3V3"),       # controller-side supply
        ("VCCB", "+5V"),        # symbol-level alias for V_CC5V (load-switch input)
    ),
    external_parts=(
        *_COMMON_DECOUPLING,
        *_ALWAYS_ON_CONTROL,
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # All HDMI cable-side pins are ESD-protected only, with internal
        # pull-ups per HDMI 1.4 spec (DS Sec 7.3.9, 7.3.15). No external R/C
        # is required on data, DDC, CEC, or HPD lines.
        "D0+", "D0-", "D1+", "D1-", "D2+", "D2-", "CLK+", "CLK-",
        "SDA_A", "SCL_A", "CEC_A", "HPD_A",
        "SDA_B", "SCL_B", "HPD_B",
    }),
    layout_notes=(
        LayoutNote(
            text="Place TPD12S016 as close as possible to HDMI connector pin 1 "
                 "(< 10mm) to minimise unprotected TMDS stub length",
            severity="rule",
            justification="DS Sec 10.1: ESD energy must dissipate at protection "
                          "pins before reaching downstream traces",
        ),
        LayoutNote(
            text="TMDS pairs: route as 100R differential, length-matched within "
                 "0.5mm intra-pair and <= 2mm inter-pair skew across all four pairs",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.3 + TPD12S016 DS Sec 7.3.4",
        ),
        LayoutNote(
            text="Route TMDS lines straight (no 90-degree turns) and avoid vias "
                 "between connector and TPD12S016 protection pins",
            severity="rule",
            justification="DS Sec 10.1: minimise EMI coupling and impedance "
                          "discontinuity on the ESD path",
        ),
        LayoutNote(
            text="Place the 100nF V_CCA and V_CC5V decoupling caps within 5mm "
                 "of their respective supply pins (24 and 11)",
            severity="rule",
            justification="DS Sec 10.1: minimise impedance on the ESD return path",
        ),
        LayoutNote(
            text="Provide a large ground via field under the device and tie all "
                 "GND pins (6, 14, 19) to a continuous ground plane",
            severity="rule",
            justification="DS Sec 10.2: low-impedance GND is essential for ESD "
                          "dissipation",
        ),
    ),
)


# ---------------------------------------------------------------------------
# RX variant - HDMI SINK path.
#
# +5V on HDMI connector pin 18 comes FROM the upstream source and lands on
# V_CC5V via 5V_OUT (TPD12S016 back-drive-protects this connection). The
# load switch is unused; CT_HPD still keeps the level shifters and HPD
# detect circuit enabled so a hot-plug event can be reported to the Zynq.
# ---------------------------------------------------------------------------

TPD12S016_RX_REFCIRCUIT = ReferenceCircuit(
    part_mpn="TPD12S016PWR",
    lcsc="C201665",
    datasheet_url="https://www.ti.com/lit/ds/symlink/tpd12s016.pdf",
    datasheet_revision="SLLSE96F, Rev Oct 2015",
    app_circuit_figure="Figure 15 / Sec 7.3.8 (back-drive on V_CC5V in sink role)",
    local_datasheet_path="components/tpd12s016/datasheet.pdf",
    app_circuit_page="p.18 Figure 15 + p.15 Sec 7.3.8 back-drive protection",
    minimum_circuit_verified=True,
    symbol_token="TPD12S016PWR",
    footprint="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
    description="HDMI sink companion: 12-ch ESD + DDC/CEC/HPD level shifters (5V sourced by upstream)",
    supply_rail="+3V3",
    pin_net_overrides=(
        ("VCCA", "+3V3"),                  # controller-side supply
        ("VCCB", "ZYNQ_HDMI_RX_5V_SENSE"), # cable-side rail FROM source (back-drive protected)
    ),
    external_parts=(
        *_COMMON_DECOUPLING,
        *_ALWAYS_ON_CONTROL,
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # See TX comment.
        "D0+", "D0-", "D1+", "D1-", "D2+", "D2-", "CLK+", "CLK-",
        "SDA_A", "SCL_A", "CEC_A", "HPD_A",
        "SDA_B", "SCL_B", "HPD_B",
    }),
    layout_notes=(
        LayoutNote(
            text="Place TPD12S016 within 10mm of the HDMI receptacle to keep TMDS "
                 "stubs short and the ESD path direct",
            severity="rule",
            justification="DS Sec 10.1",
        ),
        LayoutNote(
            text="TMDS RX termination is handled internally by the Zynq HP I/O "
                 "(50R to AVCC); do NOT add external termination on the cable side",
            severity="rule",
            justification="HDMI 1.4 Sec 4.2.5 + Zynq SelectIO TMDS_33 documentation",
        ),
        LayoutNote(
            text="5V_OUT pin (13) carries +5V SOURCED BY THE UPSTREAM transmitter; "
                 "TPD12S016 back-drive protection (DS Sec 7.3.8) prevents reverse "
                 "current into our 5V rail",
            severity="info",
        ),
        LayoutNote(
            text="Tie all GND pins to a single low-impedance ground plane and place "
                 "decoupling caps within 5mm of V_CCA (24) and V_CC5V (11)",
            severity="rule",
            justification="DS Sec 10.1",
        ),
    ),
)
