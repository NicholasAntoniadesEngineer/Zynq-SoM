from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
J23_MAP = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)"

TMDS_LINES = (
    "HDMI_RX_D2_P", "HDMI_RX_D2_N",
    "HDMI_RX_D1_P", "HDMI_RX_D1_N",
    "HDMI_RX_D0_P", "HDMI_RX_D0_N",
    "HDMI_RX_CLK_P", "HDMI_RX_CLK_N",
)

TERM_R = register(
    "hdmi_rx_term.term", "49.9R", "ohm",
    "One 50R-class sink termination per single-ended line, 8 total for the "
    "three data lanes + clock. A Zynq-7000 HR bank does NOT self-terminate "
    "TMDS_33 (DIFF_TERM is HP-bank / 2.5 V-only), so without this network HDMI "
    "RX simply does not work. YAGEO RC0603FR-0749R9L 1% (LCSC C114625) — the "
    "low DC error keeps the TMDS common mode centred.",
    "datasheet")

AVCC_RAIL = register(
    "hdmi_rx_term.avcc", "+3V3", "net",
    "AVCC is bank 33's own VCCO, so terminating to +3V3 tracks the bank I/O "
    "supply exactly — the correct TMDS_33 termination voltage. A series "
    "ferrite to isolate a dedicated AVCC island is a layout populate option, "
    "deliberately NOT a distinct netlist node.",
    "datasheet")

AVCC_HF = register("hdmi_rx_term.avcc_hf", "100n", "F",
                   "Bank-local HF bypass for AVCC (DEF-G), 50 V X7R. "
                   "LCSC C14663.", "datasheet")

AVCC_RESERVOIR = register(
    "hdmi_rx_term.avcc_reservoir", "1u", "F",
    "Charge reservoir for the 64 mA termination load swinging against AVCC, "
    "50 V X5R. LCSC C15849. On this IC-less sheet both caps anchor as rail-"
    "decoupling columns, not an IC cluster.",
    "datasheet")

TERM_DRAW_A = register(
    "hdmi_rx_term.term_draw", 0.064, "A",
    "Each driven-low line sinks ~8 mA through its 49.9R into the source's "
    "current-steering output; 8 lines -> ~64 mA worst case, sourced from AVCC.",
    "datasheet")


def circuit() -> Circuit:
    c = Circuit("hdmi_rx_term",
                "HDMI-RX TMDS sink termination (8x49.9R to AVCC=+3V3)")

    for i, net in enumerate(TMDS_LINES, start=1):
        c.part(f"R{i}", "Device:R", TERM_R, R_FP, LCSC="C114625")
        c.port(net, f"R{i}.1", expect=J23_MAP)
        c.net(AVCC_RAIL, f"R{i}.2")

    c.part("C1", "Device:C", AVCC_HF, C_FP, LCSC="C14663")
    c.part("C2", "Device:C", AVCC_RESERVOIR, C_FP, LCSC="C15849")
    c.net(AVCC_RAIL, "C1.1", "C2.1")
    c.net("GND", "C1.2", "C2.2")

    c.draws(AVCC_RAIL, TERM_DRAW_A,
            "8x TMDS sink termination 49.9R to AVCC (~8 mA/line driven low)")
    return c
