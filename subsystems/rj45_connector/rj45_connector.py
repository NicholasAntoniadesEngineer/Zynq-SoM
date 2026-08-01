from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import RJ45_LED_SERIES

R_FP = "Resistor_SMD:R_0603_1608Metric"

LCSC_LED_SERIES = "C23138"

RAILS = ("+VLED", "GND", "CHASSIS_GND")
MDI_PORTS = (
    "RJ45_MDI0_P", "RJ45_MDI0_N",
    "RJ45_MDI1_P", "RJ45_MDI1_N",
    "RJ45_MDI2_P", "RJ45_MDI2_N",
    "RJ45_MDI3_P", "RJ45_MDI3_N",
)
PORTS = MDI_PORTS
INTERFACE = RAILS + PORTS

PAIR_IMPEDANCE = 100

MDI_CONTACTS = {
    1: "RJ45_MDI0_P", 2: "RJ45_MDI0_N",
    3: "RJ45_MDI1_P", 6: "RJ45_MDI1_N",
    4: "RJ45_MDI2_P", 5: "RJ45_MDI2_N",
    7: "RJ45_MDI3_P", 8: "RJ45_MDI3_N",
}

DRAWS_NOTE = "RJ45 housing LEDs (2x 330R port-present indicator)"
DRAWS_A = 0.008


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("rj45_connector", "RJ45 8P8C jack (plain, ext. magnetics)")
    c.use_part("KH-5224-8P8C-D", ref="J1")

    for pin, net in MDI_CONTACTS.items():
        c.port(net, f"J1.{pin}")
    for n in range(4):
        c.port_type(f"RJ45_MDI{n}_P", kind="diff_pair",
                    pair_with=f"RJ45_MDI{n}_N", impedance=PAIR_IMPEDANCE,
                    **meta.expect_kw(f"RJ45_MDI{n}_P"))

    # The LED diodes are INSIDE the KH-5224 housing (pins 9-12 are its anodes
    # and cathodes) — adding a Device:LED here would put two LEDs in series.
    rl = c.part("R1", "Device:R", RJ45_LED_SERIES, R_FP, LCSC=LCSC_LED_SERIES)
    c.net("+VLED", f"{rl.ref}.1")
    c.net("RJ45_LED_L", f"{rl.ref}.2", "J1.9")
    c.net("GND", "J1.10")
    rr = c.part("R2", "Device:R", RJ45_LED_SERIES, R_FP, LCSC=LCSC_LED_SERIES)
    c.net("+VLED", f"{rr.ref}.1")
    c.net("RJ45_LED_R", f"{rr.ref}.2", "J1.11")
    c.net("GND", "J1.12")

    c.net("CHASSIS_GND", "J1.13")

    c.draws("+VLED", DRAWS_A, draws_note)
    return meta.finish(c)
