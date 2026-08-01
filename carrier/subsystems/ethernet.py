"""ethernet project bind — circuit + component basis: subsystems/ethernet/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.ethernet import ethernet as _lib

__all__ = ["circuit", "META"]

_SUB = "ethernet"
_RJ45 = "rj45_connector (wave 2)"

_CHASSIS = bind(
    _SUB, "CHASSIS_GND", "CHASSIS_GND",
    "Chassis-ground island: the Bob-Smith trunk's single 1n/2kV barrier cap "
    "bypasses to it. A separate net from signal GND, star-bonded elsewhere.",
    "policy")

_PHY = {
    f"MDI{i}_{s}": bind(
        _SUB, f"MDI{i}_{s}", f"ETH_PHY_MDI{i}_{s}",
        "Chip-side 1000BASE-T pair facing the SoM RTL8211F across J1. The SoM "
        "exposes only the MDI pairs — no CT-bias path crosses the mezzanine, so "
        "the chip-side centre taps stay NC and the PHY self-biases.",
        "datasheet")
    for i in range(4) for s in ("P", "N")
}

_MEDIA = {
    f"MX{i}_{s}": bind(
        _SUB, f"MX{i}_{s}", f"ETH_LINE_MDI_{i}_{s}",
        "Media-side pair to the RJ45 jack. The 1:1 winding is IN PHASE, so + "
        "couples to + (MDIx_P <-> LINE_x_P) — crossing the pair here inverts "
        "the link.",
        "datasheet")
    for i in range(4) for s in ("P", "N")
}

META = {
    "bind": {
        "CHASSIS_GND": _CHASSIS,
        **_PHY,
        **_MEDIA,
    },
    "expects": {
        "MX0_P": _RJ45, "MX1_P": _RJ45, "MX2_P": _RJ45, "MX3_P": _RJ45,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
