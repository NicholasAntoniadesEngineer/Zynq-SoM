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
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('pmod')

DRAWS_NOTE = "2x Pmod module budget ~100 mA each"
DRAWS_A = 0.200

RAIL_NOM_V = {"+VCC_PMOD": 3.3, "GND": 0.0}

BYPASS_REFS = (("C1", PMOD_RAIL_BYPASS, C0603, LCSC_BYPASS),
               ("C2", PMOD_RAIL_BULK, C0805, LCSC_BULK),
               ("C3", PMOD_RAIL_BYPASS, C0603, LCSC_BYPASS),
               ("C4", PMOD_RAIL_BULK, C0805, LCSC_BULK))


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('pmod', meta)
