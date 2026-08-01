from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    PMOD_EXP_ENABLE_PULLDOWN,
    PMOD_EXP_ILIM_SET,
    PMOD_EXP_INPUT_BULK,
    PMOD_EXP_INPUT_BYPASS,
    PMOD_EXP_LED_SERIES,
    PMOD_EXP_OUTPUT_BYPASS,
    PMOD_EXP_SOCKET_BULK,
    PMOD_EXP_SOCKET_BYPASS,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_100N = "C14663"
LCSC_10U = "C15850"
LCSC_13K = "C22797"
LCSC_100K = "C25803"
LCSC_330R = "C23138"
LCSC_RED = "C2286"

RAILS = ("+VDD_PMOD", "+VSW_PMOD", "GND")
PORTS = ("PMOD_IO1", "PMOD_IO2", "PMOD_IO3", "PMOD_IO4",
         "PMOD_IO5", "PMOD_IO6", "PMOD_IO7", "PMOD_IO8")
INTERFACE = RAILS + PORTS

DRAWS_PMOD_A = 0.104
DRAWS_PMOD_NOTE = ("1x Pmod module budget ~100 mA (Digilent spec) + status LED")

RAIL_WORST_V = {"+VDD_PMOD": 3.3, "+VSW_PMOD": 3.3, "GND": 0.0}

PAD = {p: 2 * p - 1 for p in range(1, 7)}
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})

IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

IO_PORTS = list(PORTS)

ESD_CH = ["1", "3", "6", "4"]


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    c = Circuit("pmod_expansion",
                "Pmod expansion (2x6, bank 13, ESD, gated 3V3)")

    c.use_part("SY6280AAC", ref="U1")
    c.net("+VDD_PMOD", "U1.IN")
    c.net("+VSW_PMOD", "U1.OUT")
    c.net("GND", "U1.GND")
    c.net("EN_PMODX", "U1.EN")
    rset = c.part(c.auto_ref("R"), "Device:R", PMOD_EXP_ILIM_SET, R0603,
                  LCSC=LCSC_13K)
    c.net("BS_ISET_PMODX", "U1.ISET", f"{rset.ref}.1")
    c.net("GND", f"{rset.ref}.2")
    for cap in c.decouple("U1.IN", PMOD_EXP_INPUT_BYPASS, footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N
    cin = c.part(c.auto_ref("C"), "Device:C", PMOD_EXP_INPUT_BULK, C0805,
                 LCSC=LCSC_10U)
    c.net("+VDD_PMOD", f"{cin.ref}.1")
    c.net("GND", f"{cin.ref}.2")
    for cap in c.decouple("U1.OUT", PMOD_EXP_OUTPUT_BYPASS, footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("+VDD_PMOD", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    c.net("EN_PMODX", "SW1.8")
    rpd = c.part(c.auto_ref("R"), "Device:R", PMOD_EXP_ENABLE_PULLDOWN, R0603,
                 LCSC=LCSC_100K)
    c.net("EN_PMODX", f"{rpd.ref}.1")
    c.net("GND", f"{rpd.ref}.2")
    c.nc("SW1.2", "SW1.4", "SW1.6")

    d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP, LCSC=LCSC_RED)
    rl = c.part(c.auto_ref("R"), "Device:R", PMOD_EXP_LED_SERIES, R0603,
                LCSC=LCSC_330R)
    c.net("+VSW_PMOD", f"{d.ref}.2")
    c.net("BS_PG_PMODX", f"{d.ref}.1", f"{rl.ref}.1")
    c.net("GND", f"{rl.ref}.2")

    c.use_part("DS1024-2x6R2", ref="J1")
    c.use_part("TPD4E1U06DBVR", ref="U2", value="TPD4E1U06")
    c.use_part("TPD4E1U06DBVR", ref="U3", value="TPD4E1U06")

    for io in range(1, 9):
        som_port = IO_PORTS[io - 1]
        esd_ref = "U2" if io <= 4 else "U3"
        esd_pin = ESD_CH[(io - 1) % 4]
        c.port(som_port, f"J1.{PAD[IO_POS[io]]}", f"{esd_ref}.{esd_pin}",
               **meta.expect_kw(som_port))

    c.net("GND", "U2.2", "U3.2")
    c.nc("U2.5", "U3.5")

    cbyp = c.part(c.auto_ref("C"), "Device:C", PMOD_EXP_SOCKET_BYPASS, C0603,
                  LCSC=LCSC_100N)
    cblk = c.part(c.auto_ref("C"), "Device:C", PMOD_EXP_SOCKET_BULK, C0805,
                  LCSC=LCSC_10U)
    c.net("+VSW_PMOD", f"J1.{PAD[6]}", f"J1.{PAD[12]}",
          f"{cbyp.ref}.1", f"{cblk.ref}.1")
    c.net("GND", f"J1.{PAD[5]}", f"J1.{PAD[11]}",
          f"{cbyp.ref}.2", f"{cblk.ref}.2")

    c.testpoint("+VSW_PMOD")
    c.draws("+VSW_PMOD", DRAWS_PMOD_A,
            meta.note("draws_pmod", DRAWS_PMOD_NOTE))

    return meta.finish(c)
