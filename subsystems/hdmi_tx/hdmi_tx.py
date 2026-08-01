from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    HDMI_TX_CABLE_BULK,
    HDMI_TX_CABLE_BYPASS,
    HDMI_TX_RAIL_BULK,
    HDMI_TX_RAIL_BYPASS,
    HDMI_TX_STRAP_PULL,
)

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"
LCSC_1U = "C15849"
LCSC_10U = "C15850"
LCSC_10K = "C25804"

RAILS = ("+VDD_IO", "+5V", "GND", "CHASSIS_GND")
TMDS_PORTS = (
    "TMDS_D2_P", "TMDS_D2_N",
    "TMDS_D1_P", "TMDS_D1_N",
    "TMDS_D0_P", "TMDS_D0_N",
    "TMDS_CLK_P", "TMDS_CLK_N",
)
CTRL_PORTS = ("CEC", "DDC_SCL", "DDC_SDA", "HPD")
PORTS = TMDS_PORTS + CTRL_PORTS
INTERFACE = RAILS + PORTS

DDC_BUS = "HDMI_TX_DDC"
DDC_SPEED_HZ = 100_000

DRAWS_VCCA_NOTE = "TPD12S016 ICCA + LS_OE/CT_HPD straps"
DRAWS_VCCA_A = 0.002
DRAWS_5V_NOTE = ("HDMI source +5V to cable — TPD12S016 switch limit 55 mA "
                 "(DS 7.3.10)")
DRAWS_5V_A = 0.055

TMDS_LANES = (
    ("TMDS_D2_P", "23", "1"), ("TMDS_D2_N", "22", "3"),
    ("TMDS_D1_P", "21", "4"), ("TMDS_D1_N", "20", "6"),
    ("TMDS_D0_P", "18", "7"), ("TMDS_D0_N", "17", "9"),
    ("TMDS_CLK_P", "16", "10"), ("TMDS_CLK_N", "15", "12"),
)
TMDS_PAIRS = (
    ("TMDS_D2_P", "TMDS_D2_N"),
    ("TMDS_D1_P", "TMDS_D1_N"),
    ("TMDS_D0_P", "TMDS_D0_N"),
    ("TMDS_CLK_P", "TMDS_CLK_N"),
)
SHIFTED = (
    ("CEC", "HDMI_TX_CON_CEC", "1", "7", "13"),
    ("DDC_SCL", "HDMI_TX_CON_SCL", "2", "8", "15"),
    ("DDC_SDA", "HDMI_TX_CON_SDA", "3", "9", "16"),
    ("HPD", "HDMI_TX_CON_HPD", "4", "10", "19"),
)


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    ddc_bus = meta.bus("ddc", DDC_BUS)
    draws_vcca = meta.note("draws_vcca", DRAWS_VCCA_NOTE)
    draws_5v = meta.note("draws_5v", DRAWS_5V_NOTE)

    c = Circuit("hdmi_tx", "HDMI TX: TPD12S016 + HDMI-A receptacle (source)")
    c.use_part("TPD12S016PWR", ref="U1")
    c.use_part("HDMI-019S", ref="J1")

    c.net("+VDD_IO", "U1.24")
    c.net("+5V", "U1.11")
    for cap in c.decouple("U1.24", HDMI_TX_RAIL_BYPASS, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    for cap in c.decouple("U1.11", HDMI_TX_RAIL_BYPASS, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.part("C5", "Device:C", HDMI_TX_RAIL_BULK, C0805, LCSC=LCSC_10U)
    c.net("+VDD_IO", "C5.1")
    c.net("GND", "C5.2")

    for port, upin, jpin in TMDS_LANES:
        c.port(port, f"U1.{upin}", f"J1.{jpin}")
    for p_pos, p_neg in TMDS_PAIRS:
        c.port_type(p_pos, kind="tmds_pair", pair_with=p_neg,
                    **meta.expect_kw(p_pos))

    c.port("CEC", "U1.1", **meta.expect_kw("CEC"))
    c.port("DDC_SCL", "U1.2", kind="i2c", role="scl",
           bus=ddc_bus, speed_hz=DDC_SPEED_HZ, **meta.expect_kw("DDC_SCL"))
    c.port("DDC_SDA", "U1.3", kind="i2c", role="sda",
           bus=ddc_bus, speed_hz=DDC_SPEED_HZ, **meta.expect_kw("DDC_SDA"))
    c.port("HPD", "U1.4", **meta.expect_kw("HPD"))
    for _name, bnet, _a, bpin, jpin in SHIFTED:
        c.net(bnet, f"U1.{bpin}", f"J1.{jpin}")

    c.net("HDMI_TX_CON_5V0", "U1.13", "J1.18")
    for ref, val, lcsc in (("C3", HDMI_TX_CABLE_BYPASS, LCSC_100N),
                           ("C4", HDMI_TX_CABLE_BULK, LCSC_1U)):
        c.part(ref, "Device:C", val, C_FP, LCSC=lcsc)
        c.net("HDMI_TX_CON_5V0", f"{ref}.1")
        c.net("GND", f"{ref}.2")

    c.net("HDMI_TX_LS_OE", "U1.5")
    c.net("HDMI_TX_CT_HPD", "U1.12")
    c.pullup("U1.5", HDMI_TX_STRAP_PULL, "+VDD_IO",
             footprint=R_FP).fields["LCSC"] = LCSC_10K
    c.pullup("U1.12", HDMI_TX_STRAP_PULL, "+VDD_IO",
             footprint=R_FP).fields["LCSC"] = LCSC_10K

    c.net("GND", "U1.6", "U1.14", "U1.19",
          "J1.2", "J1.5", "J1.8", "J1.11", "J1.17")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    c.nc("J1.14")

    c.testpoint("+5V")
    c.testpoint("DDC_SCL")
    c.testpoint("DDC_SDA")

    c.draws("+VDD_IO", DRAWS_VCCA_A, draws_vcca)
    c.draws("+5V", DRAWS_5V_A, draws_5v)
    c.waive_pull("DDC_SCL",
                 "DDC pull-ups integrated in TPD12S016 (DS 7.3.9/7.3.15)")
    c.waive_pull("DDC_SDA",
                 "DDC pull-ups integrated in TPD12S016 (DS 7.3.9/7.3.15)")
    return meta.finish(c)
