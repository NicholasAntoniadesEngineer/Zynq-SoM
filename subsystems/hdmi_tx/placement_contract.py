"""PLACEMENT CONTRACT (v2, CRITICAL) for the ``hdmi_tx`` subsystem — plain data.

hdmi_tx is the HDMI SOURCE port: host TMDS -> TPD12S016 (U1) -> HDMI Type-A
receptacle (J1). The TPD12S016PW is a FLOW-THROUGH HDMI companion: the eight TMDS
lines enter on the CONTROLLER/A side (U1 pins 15..23), cross the device's clamp
pads, and exit on the CABLE/B side to the receptacle. This contract was PROMOTED
from the D6 lightweight tier to a CRITICAL, datasheet-cited v2 (the HS-family
audit): the device must sit AT the HDMI connector, oriented so the TMDS pairs pass
THROUGH it (A-side -> controller, B-side -> connector) with the supply-pin bypass
tight to its pins, everything on one side. See
``subsystems/power/placement_contract.py`` for the schema rationale (library refs,
per-member checks, basis strings) and ``subsystems/usb_pd/placement_contract.py``
for the proximity/same_side + external exemplar.

PRIMARY CITATIONS (pdftotext-verified against the TI documents):
  * TPD12S016 datasheet SLLSE96F:
      - Sec 8.2 (Typical Application): "The TPD12S016 is placed as close as
        possible to the HDMI connector to provide voltage level translation,
        5V_OUT current limiting and overall ESD protection for the HDMI
        controller."
      - Sec 10.1 (Layout Guidelines): "The optimum placement is as close to the
        connector as possible." + "keeping any unprotected traces away from the
        protected traces which are between the TVS and the connector" +
        "Avoid using VIAs between the connector and an I/O protection pin".
      - Sec 7.3.4: "The PW and RKT packages offer seamless layout routing options
        ... The pin mapping follows the same order as the HDMI connector pin
        mapping." (this IS the flow-through basis — pins ordered for straight
        pass-through).
  * TPD12S016 PCB Layout app note SLLA324 (Feb 2012):
      - Sec 4 (PW package), Fig 8: "When routing TMDS lines from the HDMI
        transmitter, through the TPD12S016PW, and to the HDMI connector, one needs
        to keep differential pairs tight ... TMDS traces can be routed straight
        through on the top layer" (PW = the package this repo uses,
        TPD12S016PWR).
      - Sec 2.2: "Traces to and from these pins [DDC/HPD/etc] should be routed
        after those from the TMDS lines are routed first." (TMDS is the priority
        pass-through path).

hdmi_tx parts (from hdmi_tx.py, netlist-verified):
    U1  TPD12S016PWR   HDMI companion: 8-ch TMDS ESD clamp + I2C level shift +
                       5V/HPD housekeeping. Supply pins VCCA = 24 (+VDD_IO),
                       VCC5V = 11 (+5V). TMDS A-side (controller) pins
                       23/22/21/20/18/17/16/15; 5V_OUT = 13.
    J1  HDMI-019S      HDMI Type-A receptacle (the user-touchable, off-board port)
    C1  100n  -> U1.24 (VCCA)      supply bypass, controller-side rail
    C2  100n  -> U1.11 (VCC5V)     supply bypass, load-switch input rail
    C3  100n  -> U1.13 / J1.18     switched-cable +5V HF cap AT the connector
    C4  1u    -> U1.13 / J1.18     switched-cable +5V bulk AT the connector
    C5  10u   -> +VDD_IO           module bulk (rail bulk, not a per-pin bypass)
    R1  10k   -> U1.5  (LS_OE strap to V_CCA)
    R2  10k   -> U1.12 (CT_HPD strap to V_CCA)

Every threshold carries a ``basis`` string (a CITED SLLSE96F/SLLA324 reference or
``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

# TPD12S016PWR pins (authored by NUMBER, footprint-revision-independent).
_U1_VCCA = "24"                 # V_CCA, controller-side supply
_U1_VCC5V = "11"                # V_CC5V, load-switch input supply
_U1_5V_OUT = "13"               # switched cable +5V output (to receptacle pin 18)
# TMDS A-side (controller-facing) clamp pads — the pass-through IN edge.
_U1_TMDS_A = ["23", "22", "21", "20", "18", "17", "16", "15"]

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "hdmi_tx",
    "sheet": "hdmi_tx",
    "citations": ["TI TPD12S016 SLLSE96F", "TI SLLA324 (HDMI ESD PCB layout)"],
    "roles": {
        "U1": "hdmi_companion_esd", "J1": "hdmi_receptacle",
        "C1": "vcca_bypass", "C2": "vcc5v_bypass",
        "C3": "cable5v_hf", "C4": "cable5v_bulk",
    },
    "structures": [
        # ---- FLOW-THROUGH ESD at the connector: U1 <= 5 mm of J1 ---------------
        # SLLSE96F 8.2 / 10.1 place the companion "as close to the connector as
        # possible" so the protected TMDS traces between the TVS and the jack are
        # short and no via sits between the clamp pin and the connector. The 8
        # TMDS lines then pass THROUGH the device (A-side -> controller, B-side ->
        # J1) per 7.3.4 / SLLA324 Fig 8. Anchored to ANY pad of J1 (whole-connector
        # proximity — the lanes exit the dense receptacle wherever). No datasheet
        # number -> judgment 5.0 (a 24-pin TSSOP body at an HDMI-A jack).
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "SLLSE96F 8.2/10.1 + SLLA324 Fig 8 (companion AT the HDMI "
                  "connector, TMDS pass-through)|judgment:5.0"},
        # ---- SUPPLY BYPASS: VCCA 100 nF <= 2 mm of pin 24 ---------------------
        # SLLSE96F 10.1 says supply/VBUS caps go "close to their respective pins";
        # the datasheet numbers no distance -> judgment 2.0 (HF bypass wants the
        # shortest loop, same family as the pilot vcc_cap 2.0).
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCCA],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "SLLSE96F 10.1 (caps close to their pins; DS lists VBUS/VOTG_IN "
                  "in the TPD-family template — the principle applies to VCCA/"
                  "VCC5V here, shown at the pin in Fig 15/17)|judgment:2.0"},
        # ---- SUPPLY BYPASS: VCC5V 100 nF <= 2 mm of pin 11 --------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_VCC5V],
         "members": ["C2"], "max_mm": 2.0, "same_side": True,
         "basis": "SLLSE96F 10.1 (caps close to their pins; DS lists VBUS/VOTG_IN "
                  "in the TPD-family template — the principle applies to VCCA/"
                  "VCC5V here, shown at the pin in Fig 15/17)|judgment:2.0"},
        # ---- CABLE +5V caps AT the connector: C3(HF)/C4(bulk) near J1 ----------
        # hdmi_tx.py authors C3/C4 "at the connector per HDMI 1.4 Sec 4.2.7" (they
        # bypass the switched cable +5V feeding receptacle pin 18). Kept near the
        # 5V_OUT pin (13) which is the node they decouple; measured to J1 too via
        # same_side. HF tighter than bulk. Judgment distances (spec numbers a
        # position "at the connector", not a mm).
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_5V_OUT],
         "members": ["C3"], "max_mm": 3.0, "same_side": True,
         "basis": "HDMI 1.4 4.2.7 (cable +5V bypass at the connector), HF cap"
                  "|judgment:3.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_5V_OUT],
         "members": ["C4"], "max_mm": 5.0, "same_side": True,
         "basis": "HDMI 1.4 4.2.7 (cable +5V bypass at the connector), bulk cap"
                  "|judgment:5.0"},
        # ---- SAME SIDE: the companion + its bypass on one side ----------------
        {"type": "same_side", "ics": ["U1"],
         "basis": "SLLSE96F 10.1 — companion + bypass co-located (single-side "
                  "flow-through, avoid vias between clamp pin and connector)"},
    ],
    "stage_order": ["U1"],
    # ADVISORY intra-comment terms (recorded, NOT gated — the gate v1 checks no
    # pad-row orientation):
    #   * FLOW-THROUGH ORIENTATION (SLLSE96F 7.3.4 / SLLA324 Fig 8): U1 is oriented
    #     so its TMDS A-side pins (23/22/21/20/18/17/16/15) face the controller/
    #     SoM (the mezzanine) and its B-side pins face J1, so the 4 TMDS pairs pass
    #     straight THROUGH the device with no U-turn. A-side pin set recorded here
    #     (``_U1_TMDS_A``) for a future orientation-aware template term.
    #   * C5 (10u) is the module rail bulk on +VDD_IO (each module owns its bulk),
    #     not a per-pin bypass -> left to the packer (matches the camera/microsd
    #     10u peers). R1/R2 (10k straps to V_CCA) are static config, not layout-
    #     critical -> leftovers.
    "external": {
        # FLOW: the TMDS source path runs hdmi_tx -> the SoM/mezzanine (the Zynq
        # HDMI-TX bank drives the A-side lines). @som resolves to the SoM core
        # rectangle (E3). Keeps the companion's controller side pointed at the
        # module so the pass-through does not double back.
        "flow": ["hdmi_tx", "@som"],
    },
}
