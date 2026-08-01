from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import ETHERNET_BOB_SMITH_C, ETHERNET_BOB_SMITH_R

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_1206_3225Metric"
LCSC_BOB_SMITH_R = "C4275"
LCSC_BOB_SMITH_C = "C9196"

# CHASSIS_GND is a chassis-ground island, star-bonded to signal GND off-sheet.
RAILS = ("CHASSIS_GND",)
MDI_PORTS = (
    "MDI0_P", "MDI0_N",
    "MDI1_P", "MDI1_N",
    "MDI2_P", "MDI2_N",
    "MDI3_P", "MDI3_N",
)
MX_PORTS = (
    "MX0_P", "MX0_N",
    "MX1_P", "MX1_N",
    "MX2_P", "MX2_N",
    "MX3_P", "MX3_N",
)
PORTS = MDI_PORTS + MX_PORTS
INTERFACE = RAILS + PORTS

PAIR_IMPEDANCE = 100

#            ch  td_p td_n  mx_p mx_n  mct  tct
CHANNELS = [(0,   2,   3,   23,  22,  24,  1),
            (1,   5,   6,   20,  19,  21,  4),
            (2,   8,   9,   17,  16,  18,  7),
            (3,  11,  12,   14,  13,  15, 10)]


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    c = Circuit("ethernet", "Ethernet: HX5008NL magnetics + Bob-Smith")
    t1 = c.use_part("HX5008NLT", ref="T1")
    t1.fields["ALT_LCSC"] = "C47575004"

    for ch, td_p, td_n, mx_p, mx_n, _mct, tct in CHANNELS:
        c.port(f"MDI{ch}_P", f"T1.{td_p}")
        c.port(f"MDI{ch}_N", f"T1.{td_n}")
        c.port(f"MX{ch}_P", f"T1.{mx_p}")
        c.port(f"MX{ch}_N", f"T1.{mx_n}")
        c.nc(f"T1.{tct}")

    for n in range(4):
        c.port_type(f"MDI{n}_P", kind="diff_pair",
                    pair_with=f"MDI{n}_N", impedance=PAIR_IMPEDANCE)
        c.port_type(f"MX{n}_P", kind="diff_pair",
                    pair_with=f"MX{n}_N", impedance=PAIR_IMPEDANCE,
                    **meta.expect_kw(f"MX{n}_P"))

    # Bob-Smith: each MEDIA centre tap -> 75R || 1n(2kV) into the BS_COMMON
    # trunk, which reaches CHASSIS_GND through one 2kV isolation cap.
    for ch, _td_p, _td_n, _mx_p, _mx_n, mct, _tct in CHANNELS:
        c.part(f"R{ch + 1}", "Device:R", ETHERNET_BOB_SMITH_R, R_FP,
               LCSC=LCSC_BOB_SMITH_R)
        c.part(f"C{ch + 1}", "Device:C", ETHERNET_BOB_SMITH_C, C_FP,
               LCSC=LCSC_BOB_SMITH_C)
        c.net(f"MCT{ch + 1}", f"T1.{mct}", f"R{ch + 1}.1", f"C{ch + 1}.1")
        c.net("BS_COMMON", f"R{ch + 1}.2", f"C{ch + 1}.2")

    c.part("C5", "Device:C", ETHERNET_BOB_SMITH_C, C_FP,
           LCSC=LCSC_BOB_SMITH_C)
    c.net("BS_COMMON", "C5.1")
    c.net("CHASSIS_GND", "C5.2")
    return meta.finish(c)
