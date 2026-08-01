"""pmod project bind — circuit + component basis: subsystems/pmod/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.pmod import pmod as _lib

_SUB = "pmod"
_J2_MAP = "som_j2_connector"

_PORT_NETS = {
    "PMOD0": ["IO_L2_P_13", "IO_L2_N_13", "IO_L3_P_13", "IO_L3_N_13",
              "IO_L4_P_13", "IO_L4_N_13", "IO_L5P_13", "IO_L5_N_13"],
    "PMOD1": ["IO_L7_P_13", "IO_L7_N_13", "IO_L8_P_13", "IO_L8_N_13",
              "IO_L9_DQS_P_13", "IO_L9_DQS_N_13", "IO_L10_P_13",
              "IO_L10_N_13"],
}

_VCC_PMOD = bind(
    _SUB, "+VCC_PMOD", "+3V3_PMOD",
    "Bringup-gated module rail (SY6280 cell 7) with 100n + 10u per port, "
    "budgeted ~100 mA per module per the Digilent Pmod spec.",
    "policy")

_SIGNALS = {
    f"{port}_SIG{io}": bind(
        _SUB, f"{port}_SIG{io}", net,
        "Bank-13 net taken VERBATIM from carrier/som_interface.json. These are "
        "8 intact LVDS-capable pairs, which REQUIRES +VCCO_13 = +3V3 in the "
        "rail map. IO_L5P_13 genuinely has no underscore before P (SoM symbol "
        "quirk) — do not 'fix' it.",
        "policy")
    for port, nets in _PORT_NETS.items()
    for io, net in enumerate(nets, start=1)
}

META = {
    "bind": {
        "+VCC_PMOD": _VCC_PMOD,
        "GND": "GND",
        **_SIGNALS,
    },
    "expects": {sig: _J2_MAP for sig in _SIGNALS},
    "notes": {"draws": "2x Pmod module budget ~100 mA each"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
