from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    HDMI_RX_CEC_PULL,
    HDMI_RX_DET_BOTTOM,
    HDMI_RX_DET_TOP,
    HDMI_RX_EDID_BYPASS,
    HDMI_RX_HPD_ASSERT,
)

U_LIB = "Memory_EEPROM:M24C02-WMN"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_HPD_ASSERT = "C21190"
LCSC_CEC_PULL = "C22967"
LCSC_DET_TOP = "C25804"
LCSC_DET_BOTTOM = "C22809"
LCSC_EDID_BYPASS = "C14663"

RAILS = ("+VDD_LOGIC", "GND", "CHASSIS_GND")
TMDS_PORTS = (
    "TMDS_RX_D2_P", "TMDS_RX_D2_N",
    "TMDS_RX_D1_P", "TMDS_RX_D1_N",
    "TMDS_RX_D0_P", "TMDS_RX_D0_N",
    "TMDS_RX_CLK_P", "TMDS_RX_CLK_N",
)
CTRL_PORTS = ("HDMI_5V_DET", "CEC")
PORTS = TMDS_PORTS + CTRL_PORTS
INTERFACE = RAILS + PORTS

TMDS_LANES = (
    ("TMDS_RX_D2_P", 1, "U2", "IO1"), ("TMDS_RX_D2_N", 3, "U2", "IO2"),
    ("TMDS_RX_D1_P", 4, "U2", "IO3"), ("TMDS_RX_D1_N", 6, "U2", "IO4"),
    ("TMDS_RX_D0_P", 7, "U3", "IO1"), ("TMDS_RX_D0_N", 9, "U3", "IO2"),
    ("TMDS_RX_CLK_P", 10, "U3", "IO3"), ("TMDS_RX_CLK_N", 12, "U3", "IO4"),
)
TMDS_PAIRS = (
    ("TMDS_RX_D2_P", "TMDS_RX_D2_N"),
    ("TMDS_RX_D1_P", "TMDS_RX_D1_N"),
    ("TMDS_RX_D0_P", "TMDS_RX_D0_N"),
    ("TMDS_RX_CLK_P", "TMDS_RX_CLK_N"),
)

DRAWS_NOTE = ("CEC 27k pull-up (EEPROM + EDID WC# are cable-5V-fed)")
DRAWS_A = 0.001


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)

    c = Circuit("hdmi_rx", "HDMI RX: HDMI-A sink + EDID EEPROM")
    c.use_part("HDMI-019S", ref="J1")
    c.use_part("M24C02-WMN6TP", ref="U1", lib_id=U_LIB)
    c.part("R1", "Device:R", HDMI_RX_HPD_ASSERT, R_FP, LCSC=LCSC_HPD_ASSERT)
    c.part("R2", "Device:R", HDMI_RX_CEC_PULL, R_FP, LCSC=LCSC_CEC_PULL)
    c.part("R3", "Device:R", HDMI_RX_DET_TOP, R_FP, LCSC=LCSC_DET_TOP)
    c.part("R4", "Device:R", HDMI_RX_DET_BOTTOM, R_FP, LCSC=LCSC_DET_BOTTOM)
    c.part("C1", "Device:C", HDMI_RX_EDID_BYPASS, C_FP, LCSC=LCSC_EDID_BYPASS)

    c.use_part("TPD4E02B04DQAR", ref="U2")
    c.use_part("TPD4E02B04DQAR", ref="U3")
    for net, jpin, esd_ref, esd_io in TMDS_LANES:
        c.port(net, f"J1.{jpin}", f"{esd_ref}.{esd_io}")
    c.net("GND", "U2.GND", "U3.GND")
    c.nc("U2.NC", "U3.NC")
    for p_pos, p_neg in TMDS_PAIRS:
        c.port_type(p_pos, kind="tmds_pair", pair_with=p_neg,
                    **meta.expect_kw(p_pos))

    c.net("HDMI_RX_SDA", "J1.16", "U1.5")
    c.net("HDMI_RX_SCL", "J1.15", "U1.6")

    c.use_part("TPD4E05U06DQAR", ref="U4")
    c.net("HDMI_RX_SCL", "U4.D1+")
    c.net("HDMI_RX_SDA", "U4.D1-")
    c.net("GND", "U4.GND")
    c.nc("U4.NC")

    # COMP-1: WC# (U1.7) is hardwired to the EEPROM's OWN cable-5V VCC node
    # (U1.8) — a gated 3V3 rail is dead in the board-off EDID read, unprotecting.
    c.net("HDMI_RX_5V", "J1.18", "U1.8", "U1.7", "C1.1", "R1.1", "R3.1")
    c.net("GND", "C1.2")
    c.net("HDMI_RX_HPD", "J1.19", "R1.2", "U4.D2-")
    c.port("HDMI_5V_DET", "R3.2", "R4.1", **meta.expect_kw("HDMI_5V_DET"))
    c.net("GND", "R4.2")

    c.port("CEC", "J1.13", "R2.2", "U4.D2+", **meta.expect_kw("CEC"))
    c.net("+VDD_LOGIC", "R2.1")

    c.net("GND", "J1.2", "J1.5", "J1.8", "J1.11", "J1.17",
          "U1.1", "U1.2", "U1.3", "U1.4")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    c.nc("J1.14")

    c.draws("+VDD_LOGIC", DRAWS_A, draws_note)
    return meta.finish(c)
