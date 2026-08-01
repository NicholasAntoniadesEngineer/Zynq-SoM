"""rj45_connector project bind — circuit + basis: subsystems/rj45_connector/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.rj45_connector import rj45_connector as _lib

__all__ = ["circuit", "META"]

_SUB = "rj45_connector"

_VLED = bind(
    _SUB, "+VLED", "+3V3",
    "The two housing LEDs (330R, ~4 mA) ride the EN-gated +3V3 buck rail "
    "DELIBERATELY, so they read as 'main +3V3 is up' rather than 'port "
    "present'. Never re-rail to +VIN_SYS with the existing 330R — ~55 mA would "
    "destroy the LED (audit 2026-06-19/20).",
    "datasheet")

_CHASSIS = bind(
    _SUB, "CHASSIS_GND", "CHASSIS_GND",
    "Shield/shell (J1.13) bonds to the chassis island — the same separate net "
    "the ethernet C5 isolation barrier bonds to, kept off signal GND and "
    "star-bonded elsewhere. The M3 corner holes live on the mechanical sheet, "
    "not here, so the placer corner-forces them as their own cluster.",
    "policy")

_MDI = {
    f"RJ45_MDI{i}_{s}": bind(
        _SUB, f"RJ45_MDI{i}_{s}", f"ETH_LINE_MDI_{i}_{s}",
        "Line-side 1000BASE-T pair facing the magnetics' MEDIA side. This "
        "adapter BINDS these rather than deferring them: it is the peer sheet "
        "that resolves the ethernet subsystem's own MXn deferral.",
        "policy")
    for i in range(4) for s in ("P", "N")
}

META = {
    "bind": {
        "+VLED": _VLED,
        "GND": "GND",
        "CHASSIS_GND": _CHASSIS,
        **_MDI,
    },
    "notes": {"draws": "RJ45 housing LEDs (2x 330R port-present indicator)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
