"""hdmi_tx project bind — circuit + component basis: subsystems/hdmi_tx/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.hdmi_tx import hdmi_tx as _lib

__all__ = ["circuit", "META"]

_SUB = "hdmi_tx"
_J2_MAP = "som_j2_connector (wave 3 PL function map)"

_VDD_IO = bind(
    _SUB, "+VDD_IO", "+3V3_HDMI_TX",
    "V_CCA controller side on the bringup SY6280-gated module rail. This sheet "
    "only decouples it (DS Fig 15) and owns its 10u bulk — each module owns its "
    "bulk, matching the camera/microsd peers.",
    "datasheet")

_5V = bind(
    _SUB, "+5V", "+5V_HDMI_TX",
    "V_CC5V cable side, also a gated module rail. It is the load-switch INPUT: "
    "the TPD's integrated 55 mA current-limited switch drives the cable +5V "
    "from it (DS 7.3.10).",
    "datasheet")

_TMDS = {
    f"TMDS_{lane}_{s}": bind(
        _SUB, f"TMDS_{lane}_{s}", f"ZYNQ_HDMI_TX_TMDS_{n}_{s}",
        "TMDS line from the Zynq PL flowing THROUGH the TPD clamp pads to the "
        "receptacle — one net per lane, no series element.",
        "datasheet")
    for lane, n in (("D2", "2"), ("D1", "1"), ("D0", "0"), ("CLK", "CLK"))
    for s in ("P", "N")
}

_DDC = {
    port: bind(_SUB, port, net,
               "HDMI DDC (I2C) to the Zynq PL. Pull-ups are INTEGRATED in the "
               "TPD12S016 (DS 7.3.9 / 7.3.15) — none on-board, and the library "
               "waives the design-rule that would demand them.",
               "datasheet")
    for port, net in (("DDC_SCL", "ZYNQ_HDMI_TX_SCL"),
                      ("DDC_SDA", "ZYNQ_HDMI_TX_SDA"))
}

META = {
    "bind": {
        "+VDD_IO": _VDD_IO,
        "+5V": _5V,
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        **_TMDS,
        "CEC": "ZYNQ_HDMI_TX_CEC",
        **_DDC,
        "HPD": "ZYNQ_HDMI_TX_HPD",
    },
    "expects": {
        "TMDS_D2_P": _J2_MAP,
        "TMDS_D1_P": _J2_MAP,
        "TMDS_D0_P": _J2_MAP,
        "TMDS_CLK_P": _J2_MAP,
        "CEC": _J2_MAP,
        "DDC_SCL": _J2_MAP,
        "DDC_SDA": _J2_MAP,
        "HPD": _J2_MAP,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
