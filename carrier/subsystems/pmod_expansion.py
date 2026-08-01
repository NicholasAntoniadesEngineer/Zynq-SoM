"""pmod_expansion project bind — circuit + basis: subsystems/pmod_expansion/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.pmod_expansion import pmod_expansion as _lib

_SUB = "pmod_expansion"
_J2_MAP = "som_j2_connector (PL bank 13, +VCCO_13=+3V3, LVCMOS33)"

_VDD_PMOD = bind(
    _SUB, "+VDD_PMOD", "+3V3",
    "The carrier SOURCES +VCCO_13 = +3V3 (som_conn_gen VCCO_RAIL_MAP), so bank "
    "13 runs LVCMOS33 and the Pmod's 3.3 V level-safety is structural — no "
    "translation needed. This +3V3 is the SY6280 load-switch INPUT.",
    "policy")

_VSW_PMOD = bind(
    _SUB, "+VSW_PMOD", "+3V3_PMODX",
    "The manually-gated OUTPUT rail the port provides, default-OFF (constraint "
    "C1). The SY6280 enable is LOCAL: SW1 pos 1 closes +3V3 onto EN_PMODX and a "
    "100k pulldown holds it low, so the port is dark at power-up and an "
    "unpowered peripheral can never be back-fed from it.",
    "policy")

_PMOD_IO = {
    f"PMOD_IO{n}": bind(
        _SUB, f"PMOD_IO{n}", f"PMODX_IO{n}",
        "One of the eight bank-13 pins verified FREE against every subsystem "
        "and the wave-3 FUNCTION_MAP before claiming. L12/L13/L14 keep their "
        "MRCC/SRCC clock capability — Pmod IO is plain GPIO.",
        "policy")
    for n in range(1, 9)
}

META = {
    "bind": {
        "+VDD_PMOD": _VDD_PMOD,
        "+VSW_PMOD": _VSW_PMOD,
        "GND": "GND",
        **_PMOD_IO,
    },
    "expects": {p: _J2_MAP for p in _PMOD_IO},
    "notes": {"draws_pmod": "1x Pmod module budget ~100 mA (Digilent spec) "
                            "+ status LED"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
