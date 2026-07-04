"""PLACEMENT CONTRACT (v2, CRITICAL) for the ``hdmi_rx_term`` subsystem — data only.

hdmi_rx_term is the SI companion to ``hdmi_rx``: the HDMI-RX TMDS sink source-
termination network (SI-HDMIRX-TERM / DEF-6). A Zynq-7000 HR I/O bank has NO on-die
TMDS termination (DIFF_TERM is HP-bank / 2.5 V-only), so an HDMI/DVI SINK on an HR
bank MUST present the standard external 50 ohm-to-AVCC source-termination on every
single-ended TMDS line: 8 x 49.9 ohm to a local AVCC = 3.3 V node (four pairs =
data D2/D1/D0 + clock), plus the AVCC bank-local bypass (100 nF + 1 uF). This is a
NEW CRITICAL contract (the HS-family audit; the subsystem previously carried no
placement contract at all).

The defining requirement: the 8 termination resistors and the AVCC bypass MUST sit
AT the FPGA/mezzanine TMDS-RX pins (the receiver end), clustered at the mezzanine
RX escape — because the termination is a RECEIVER-side element and the stub from
the bank pin to the resistor must be short. On this carrier the receiver bank-33
pins are the SoM's DF40 mezzanine (som_j2, net HDMI_RX_D*/CLK*), so the cluster is
pinned NEAR that connector via the composition ``near_max`` term. This subsystem is
IC-LESS (no local anchor IC), so the intra-zone terms cluster the 8 resistors + the
2 bypass caps against R1 as the cluster anchor.

RED-ON-BEFORE FINDING (empirical, orchestrator re-verify): unlike hdmi_tx/camera,
this island is GREEN-ON-BEFORE and HONESTLY so. The ten parts are identical-value
passives, so the value-sorted packer already (a) clusters them on one side
(intra-zone proximity + same_side pass) and (b) net-affinity-pulls the whole island
flush against som_j2 (measured near_max edge gap ~0.8 mm << the 10 mm cap). There
is NO scattered defect to paint red without inventing a requirement the board does
not violate (a LAW-4 softening in reverse). The contract stands as the GUARD that
keeps the island seated once templates begin moving parts — the near_max regression
tripwire — not as a red-on-before proof. (One SI concern the CURRENT gate cannot
express: whether the island's side MATCHES the DF40 escape side is a cross-sheet
same-side relation with no structure type today; recorded for a future gate term.)

PRIMARY CITATIONS (pdftotext-verified):
  * Xilinx XAPP460 (v1.1, June 24 2011) "Video Connectivity Using TMDS I/O",
    Implementation section (p.23):
      - "TMDS_33 signals require 50 ohm termination to 3.3 V at the receiver."
        (the 50 ohm source-termination to AVCC = 3.3 V, placed AT the receiver.)
      - "TMDS_33 inputs require VCCO = 2.5V/3.3V and VCCAUX = 3.3V." + the RX
        electrical model "AVcc = 3.3V" (Receiver Electrical Considerations) — AVCC
        is the +3V3 / VCCO_33 rail this sheet terminates to.
  * hdmi_rx.py SI-HDMIRX-TERM note (the repo's own DEF-6 spec): "the 7-series HR
    banks have no on-die TMDS termination ... The receiver MUST present the
    standard 50 ohm-to-AVCC source-termination on every single-ended line: 2x
    49.9 ohm/pair to a 3.3 V AVCC node, 8 resistors total ... Placed physically
    next to the bank at layout."

hdmi_rx_term parts (from hdmi_rx_term.py, netlist-verified):
    R1..R8  49.9R   one per TMDS single-ended line (D2 P/N, D1 P/N, D0 P/N,
                    CLK P/N), each to AVCC (= +3V3 = VCCO_33)
    C1  100n   AVCC HF bypass (+3V3 -> GND), bank-local
    C2  1u     AVCC charge-reservoir bypass (+3V3 -> GND), bank-local

Every threshold carries a ``basis`` string (a CITED XAPP460 reference or
``judgment:<value>`` — LAW 7 / LAW 4).
"""

from __future__ import annotations

# the 8 termination resistors (four TMDS pairs), R1..R8 (hdmi_rx_term.py order:
# D2 P/N, D1 P/N, D0 P/N, CLK P/N).
_TERMS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "hdmi_rx_term",
    "sheet": "hdmi_rx_term",
    "citations": ["Xilinx XAPP460 v1.1 (Video Connectivity Using TMDS I/O)",
                  "repo DEF-6 SI-HDMIRX-TERM (hdmi_rx.py)"],
    "roles": {
        "R1": "tmds_term", "R2": "tmds_term", "R3": "tmds_term",
        "R4": "tmds_term", "R5": "tmds_term", "R6": "tmds_term",
        "R7": "tmds_term", "R8": "tmds_term",
        "C1": "avcc_hf", "C2": "avcc_bulk",
    },
    "structures": [
        # ---- TERM CLUSTER: the 8 x 49.9R packed together at the RX escape ------
        # XAPP460 p.23 "50 ohm termination to 3.3 V at the receiver": all 8 source-
        # terminations belong at the bank pins, tight together so each single-ended
        # stub (bank pin -> 49.9R -> AVCC) is short and the four pairs stay matched.
        # IC-less sheet -> R1 is the cluster anchor; R2..R8 must sit within a tight
        # span of it. Anchor-pin absent -> measured to any pad of R1. No datasheet
        # mm -> judgment 12.0 (a 2x4 grid of 0603 terms at a DF40 escape spans a
        # few mm per row; 12 mm bounds the whole 8-part cluster).
        {"type": "proximity", "anchor": "R1",
         "members": ["R2", "R3", "R4", "R5", "R6", "R7", "R8"],
         "max_mm": 12.0, "same_side": True,
         "basis": "XAPP460 p.23 (50R term at the receiver) — 8 TMDS terms clustered "
                  "at the bank escape|judgment:12.0"},
        # ---- AVCC BYPASS at the term cluster: C1(HF)/C2(bulk) near the terms ----
        # The 100 nF + 1 uF AVCC bypass (hdmi_rx_term.py DEF-G "bank-local bypass")
        # feeds the terms' ~64 mA sink swing against AVCC, so it must sit inside the
        # termination island next to the resistors. Anchored to R1 (the cluster
        # anchor) since there is no IC body. HF tighter than bulk. Judgment (the
        # repo notes "in the termination island next to bank 33", no mm).
        {"type": "proximity", "anchor": "R1",
         "members": ["C1"], "max_mm": 5.0, "same_side": True,
         "basis": "DEF-G bank-local AVCC bypass (HF) at the term island"
                  "|judgment:5.0"},
        {"type": "proximity", "anchor": "R1",
         "members": ["C2"], "max_mm": 8.0, "same_side": True,
         "basis": "DEF-G bank-local AVCC bypass (bulk) at the term island"
                  "|judgment:8.0"},
        # ---- SAME SIDE: the whole termination island on one side --------------
        {"type": "same_side", "ics": ["R1"],
         "basis": "XAPP460 receiver-end termination island co-located on one "
                  "side (short single-ended stubs, no mid-stub via)"},
    ],
    "stage_order": ["R1"],
    # ADVISORY (recorded, NOT gated): the AVCC island may fit a 0 ohm / ferrite in
    # the +3V3->AVCC trace at layout (hdmi_rx_term.py) — a populate option, not a
    # netlist node, so no placement term. The bank-33 RX pins that these terms
    # merge with live on som_j2 (the DF40 mezzanine); the near_max term below pins
    # the whole island against that connector.
    "external": {
        # NEAR_MAX (E5-lite, D11 edge-gap): the termination island MUST hug the
        # mezzanine RX escape (som_j2 carries the FPGA bank-33 HDMI_RX_* pins these
        # terms merge with). The single-ended stub from the bank pin to the 49.9R
        # must be short (an over-long stub reflects the TMDS edge), so the island
        # sits AT the connector. XAPP460 numbers no inter-part mm -> judgment 10.0
        # zone edge-gap (the edge gap is <= any part-to-part distance, so a 10 mm
        # gap keeps every term within a short stub of the escape).
        "near_max": [
            {"other": "som_j2", "max_mm": 10.0,
             "basis": "XAPP460 p.23 (term AT the receiver) — island at the SoM "
                      "mezzanine bank-33 RX escape|judgment:10.0 edge-gap (D11)"},
        ],
    },
}
