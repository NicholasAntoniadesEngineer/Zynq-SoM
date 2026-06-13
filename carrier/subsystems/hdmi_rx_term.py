"""hdmi_rx_term — HDMI-RX TMDS sink termination (SI-HDMIRX-TERM, DEF-6).

An HDMI/DVI sink on a Zynq-7000 HR I/O bank does NOT self-terminate TMDS_33
(the 7-series HR banks have no on-die TMDS termination, and DIFF_TERM is HP-
bank/2.5 V-only — see hdmi_rx.py SI-HDMIRX-TERM). The receiver MUST therefore
present the standard 50 ohm-to-AVCC source-termination on every single-ended
line: 2x 49.9 ohm/pair to a 3.3 V AVCC node, 8 resistors total for the three
data lanes + clock. WITHOUT this network HDMI RX simply does not work — it was
carried for several rounds as a docstring-only "MANDATORY layout note" because
the resistors belong at the RECEIVER (FPGA-bank) end, not on the connector
sheet, and the connector-sheet placer could not anchor an off-sheet AVCC trunk.

DEF-6 promotes it to a real, netlisted, gate-checked, BOM-counted network on
its own sheet, bound to the TMDS_RX_* ports (which merge with the FPGA bank-33
pins at board assembly). Placed physically next to the bank at layout.

AVCC = +3V3: bank 33's VCCO IS +3V3 (the carrier VCCO_33 rail), so terminating
to +3V3 tracks the bank I/O supply exactly — the correct TMDS_33 termination
voltage. AVCC is bypassed locally with 100 nF + 1 uF near the bank. A series
ferrite to isolate a dedicated AVCC island from +3V3 is a populate option at
layout (fit a 0 ohm / ferrite in the +3V3->AVCC trace); it is intentionally not
a distinct netlist node here, to keep the termination referenced to the proven
+3V3/VCCO_33 rail with no extra single-sourced part.

Termination R: YAGEO RC0603FR-0749R9L, 49.9 ohm 1% 0603 (LCSC C114625,
live-verified in hdmi_rx.py). Low DC error keeps the TMDS common-mode centred.
"""

from __future__ import annotations

from schgen.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
J23_MAP = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)"

# The 8 single-ended TMDS-RX lines (4 pairs), exactly as hdmi_rx.py exports
# them. Each gets one 49.9 ohm sink termination to AVCC (= +3V3).
TMDS_LINES = (
    "HDMI_RX_D2_P", "HDMI_RX_D2_N",
    "HDMI_RX_D1_P", "HDMI_RX_D1_N",
    "HDMI_RX_D0_P", "HDMI_RX_D0_N",
    "HDMI_RX_CLK_P", "HDMI_RX_CLK_N",
)


def circuit() -> Circuit:
    c = Circuit("hdmi_rx_term",
                "HDMI-RX TMDS sink termination (8x49.9R to AVCC=+3V3)")

    # 8x 49.9 ohm 1% from each TMDS single-ended line to the 3.3 V AVCC node.
    for i, net in enumerate(TMDS_LINES, start=1):
        c.part(f"R{i}", "Device:R", "49.9R", R_FP, LCSC="C114625")
        c.port(net, f"R{i}.1", expect=J23_MAP)   # merges with the bank-33 pin
        c.net("+3V3", f"R{i}.2")                  # AVCC = VCCO_33 = +3V3

    # AVCC bypass: 100 nF + 1 uF from +3V3 to GND placed NEXT TO THE BANK at
    # layout (LAYOUT NOTE, not netlisted here). AVCC == the +3V3 / VCCO_33 rail
    # that already carries board-wide 100 nF/bulk bypass, so this is a layout-
    # placement requirement (put a 0603 100 nF + a 1 uF inside the termination
    # island near bank 33), not a distinct schematic node — and a rail-to-rail
    # cap has no placement anchor on this IC-less sheet. Fit C14663 (100 nF) +
    # C15849 (1 uF), both 0603, when the AVCC island is poured.

    # power-tree budget: TMDS sink termination current is sourced from AVCC
    # (+3V3) — each driven-low line sinks ~8 mA through its 49.9R to the
    # source's current-steering output; 8 lines -> ~64 mA worst case.
    c.draws("+3V3", 0.064,
            "8x TMDS sink termination 49.9R to AVCC (~8 mA/line driven low)")
    return c
