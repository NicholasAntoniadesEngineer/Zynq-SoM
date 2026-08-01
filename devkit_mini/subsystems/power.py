"""power project bind — circuit + component basis: subsystems/power/."""

from __future__ import annotations

from devkit_mini.basis import bind, register
from schgen.core.model import Circuit
from subsystems.power import power as _lib

_SUB = "power"
_BRINGUP = "bringup (wave 2 rail-enable cells, dossier section 3.1)"

# ANCHOR: copper_debt CD-01 greps this file for the phrase below — one line.
THERMAL_CREDIT_C_PER_W = register(
    "power.thermal_credit", 30, "C/W",
    "The thermal gate now credits a CONSERVATIVE pour-aware effective RthJA "
    "for the LM61460 (TI SNVSBD5D 7.3: 58.7 C/W bare vs 25 C/W on a 4-layer "
    "board), so U1 passes on real margin (Tj ~128 C < the 140 C guard) with NO "
    "waiver. The credit is PREDICATED ON COPPER: a full-board In1.Cu GND plane "
    "+ a per-buck thermal-via field at PGND1/PGND2 + local F.Cu/B.Cu pours. "
    "copper_debt CD-01 hard-verifies that copper every build, because without "
    "it Tj backs out to ~192 C — a board-dead thermal PASS-on-fiction.",
    "datasheet")

_VIN = bind(
    _SUB, "+VIN", "+VIN_SYS",
    "DEF-D: the buck input is the POST-shunt rail. RS1 series-inserts between "
    "the eFuse +VIN and the buck inputs (power_mon), so input-cap ripple and "
    "inrush flow through RS1 and land on the U1 +VIN telemetry channel. The "
    "input caps move with the pin.",
    "policy")

_REG_SIDE = {
    port: bind(_SUB, port, net,
               "DEF-D regulator-OUTPUT cluster (inductor node, output bulk, FB "
               "sense, BIAS tie, PG LED) — the reg side of its shunt. Splitting "
               "here is what makes the shunt measure CONSUMER draw only.",
               "policy")
    for port, net in (("+VOUT_5V_REG", "+5V_REG"),
                      ("+VOUT_3V3_REG", "+3V3_REG"),
                      ("+VOUT_1V8_REG", "+1V8_REG"))
}

_LOAD_SIDE = {
    port: bind(_SUB, port, net,
               "Board rail on the LOAD side of its shunt, carrying the measured "
               "consumers.",
               "policy")
    for port, net in (("+VOUT_5V", "+5V"), ("+VOUT_3V3", "+3V3"),
                      ("+VOUT_1V8", "+1V8"))
}

_EN = {
    port: bind(_SUB, port, net,
               "Rail enable driven by the bringup DIP-AND-STM32 cell (dossier "
               "3.1). It binds on the bringup sheet, so the adapter declares an "
               "explicit linker deferral rather than leaving a silent open.",
               "policy")
    for port, net in (("EN_VOUT_5V", "EN_5V0"), ("EN_VOUT_3V3", "EN_3V3"),
                      ("EN_VOUT_1V8", "EN_1V8"))
}

META = {
    "bind": {
        "+VIN": _VIN,
        **_REG_SIDE,
        **_LOAD_SIDE,
        "GND": "GND",
        **_EN,
    },
    "expects": {port: _BRINGUP for port in _EN},
    "notes": {
        "draws_5v": "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA",
        "draws_3v3": ("PG LED (330R ~3.9 mA) + 1V8 PG sense LED chain "
                      "(330R ~3.9 mA) + FB divider 27 uA"),
        "draws_1v8": "PG FET gate divider 10k+100k (16 uA), rounded up",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
