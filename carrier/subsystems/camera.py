"""camera project bind — circuit + component basis: subsystems/camera/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.camera import camera as _lib

_SUB = "camera"
_J3_35 = "som_j3_connector (PL bank 35, LVDS_25, +VCCO_35=2.5V)"
_J3_33 = "som_j3_connector (PL bank 33, +VCCO_33=3.3V)"

_VDD_CAM = bind(
    _SUB, "+VDD_CAM", "+3V3_CAM",
    "Bring-up-gated module rail (bringup_modules SY6280 cell 4, 523 mA limit "
    "vs the 300 mA budget), peer of +3V3_PMOD / +3V3_SD. The camera-control "
    "I2C pull-ups tie to this GATED rail, not to a live one, so a powered-down "
    "camera is not back-fed through its own bus pull-ups.",
    "policy")

_CSI = {
    port: bind(_SUB, port, net,
               "MIPI D-PHY lane to bank 35, which is LVDS_25 (+VCCO_35 = 2.5 V "
               "from a local LDO). That makes bank 35 a 2.5 V-only bank, which "
               "is why the 3.3 V control lines go to bank 33 instead.",
               "datasheet")
    for port, net in (("CSI_D0_P", "CAM_D0_P"), ("CSI_D0_N", "CAM_D0_N"),
                      ("CSI_D1_P", "CAM_D1_P"), ("CSI_D1_N", "CAM_D1_N"),
                      ("CSI_CLK_P", "CAM_CLK_P"), ("CSI_CLK_N", "CAM_CLK_N"))
}

_CAM_I2C = {
    port: bind(_SUB, port, port,
               "Dedicated CAM_I2C bus — a Zynq-fabric bus (AXI IIC / PS I2C via "
               "EMIO) on bank 33, a DIFFERENT controller domain from the "
               "STM32_I2C2 management trunk.",
               "policy")
    for port in ("CAM_SCL", "CAM_SDA")
}

META = {
    "bind": {
        "+VDD_CAM": _VDD_CAM,
        "GND": "GND",
        **_CSI,
        **_CAM_I2C,
        "CAM_EN": "CAM_EN",
        "CAM_LED": "CAM_LED",
    },
    "expects": {
        **{p: _J3_35 for p in _CSI},
        **{p: _J3_33 for p in _CAM_I2C},
        "CAM_EN": _J3_33,
        "CAM_LED": _J3_33,
    },
    "buses": {"i2c": "CAM_I2C"},
    "notes": {"draws": "RPi camera module budget (camera_csi.md: V2 typ ~250 mA)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
