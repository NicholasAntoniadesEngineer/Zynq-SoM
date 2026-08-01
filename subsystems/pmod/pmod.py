from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import PMOD_RAIL_BULK, PMOD_RAIL_BYPASS, PMOD_SERIES_DAMPING

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_SERIES_DAMPING = "C8218"
LCSC_BYPASS = "C14663"
LCSC_BULK = "C15850"

PAD = {p: 2 * p - 1 for p in range(1, 7)}
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})

IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

ESD_CH = ["1", "3", "6", "4"]
LCSC_TPD = "C124691"

PORTS_DEF = (("J1", "PMOD0"), ("J2", "PMOD1"))

RAILS = ("+VCC_PMOD", "GND")
PORTS = tuple(f"{port}_SIG{io}"
              for _jref, port in PORTS_DEF
              for io in range(1, 9))
INTERFACE = RAILS + PORTS

DRAWS_NOTE = "2x Pmod module budget ~100 mA each"
DRAWS_A = 0.200

RAIL_NOM_V = {"+VCC_PMOD": 3.3, "GND": 0.0}

BYPASS_REFS = (("C1", PMOD_RAIL_BYPASS, C0603, LCSC_BYPASS),
               ("C2", PMOD_RAIL_BULK, C0805, LCSC_BULK),
               ("C3", PMOD_RAIL_BYPASS, C0603, LCSC_BYPASS),
               ("C4", PMOD_RAIL_BULK, C0805, LCSC_BULK))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("pmod", "2x Pmod host ports (bank 13, 200R series, gated 3V3)")
    vcc_pins: list[str] = []
    gnd_pins: list[str] = []
    esd_gnd: list[str] = []
    esd_nc: list[str] = []
    rnum = 1
    for pidx, (jref, port) in enumerate(PORTS_DEF):
        c.use_part("DS1024-2x6R2", ref=jref)
        esd_lo = f"U{2 * pidx + 1}"
        esd_hi = f"U{2 * pidx + 2}"
        c.use_part("TPD4E1U06DBVR", ref=esd_lo, value="TPD4E1U06")
        c.use_part("TPD4E1U06DBVR", ref=esd_hi, value="TPD4E1U06")

        # The clamp rides the BOUND signal net, not the socket leg: a 4-channel
        # array on the leg would mesh the placer's float-net lineariser.
        for io in range(1, 9):
            ref = f"R{rnum}"
            rnum += 1
            c.part(ref, "Device:R", PMOD_SERIES_DAMPING, R0603,
                   LCSC=LCSC_SERIES_DAMPING)
            esd_ref = esd_lo if io <= 4 else esd_hi
            c.port(f"{port}_SIG{io}", f"{ref}.1",
                   f"{esd_ref}.{ESD_CH[(io - 1) % 4]}",
                   **meta.expect_kw(f"{port}_SIG{io}"))
            c.net(f"{port}_IO{io}", f"{ref}.2", f"{jref}.{PAD[IO_POS[io]]}")

        gnd_pins += [f"{jref}.{PAD[5]}", f"{jref}.{PAD[11]}"]
        vcc_pins += [f"{jref}.{PAD[6]}", f"{jref}.{PAD[12]}"]
        esd_gnd += [f"{esd_lo}.2", f"{esd_hi}.2"]
        esd_nc += [f"{esd_lo}.5", f"{esd_hi}.5"]

    for ref, val, fp, lcsc in BYPASS_REFS:
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
    c.net("+VCC_PMOD", *vcc_pins, "C1.1", "C2.1", "C3.1", "C4.1")
    c.net("GND", *gnd_pins, *esd_gnd, "C1.2", "C2.2", "C3.2", "C4.2")
    c.nc(*esd_nc)

    c.draws("+VCC_PMOD", DRAWS_A, draws_note)
    return meta.finish(c)
