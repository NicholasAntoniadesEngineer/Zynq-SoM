from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    CAMERA_I2C_PULL,
    CAMERA_LANE_TERM,
    CAMERA_RAIL_BULK,
    CAMERA_RAIL_BYPASS,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_LANE_TERM = "C22775"
LCSC_I2C_PULL = "C23162"
LCSC_BYPASS = "C14663"
LCSC_BULK = "C15850"

RAILS = ("+VDD_CAM", "GND")
PORTS = (
    "CSI_D0_P", "CSI_D0_N",
    "CSI_D1_P", "CSI_D1_N",
    "CSI_CLK_P", "CSI_CLK_N",
    "CAM_SCL", "CAM_SDA",
    "CAM_EN", "CAM_LED",
)
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('camera')

I2C_BUS = "CAM_CCI"
I2C_SPEED_HZ = 400_000
LANE_IMPEDANCE = 100

EXPECT_CSI = "host MIPI CSI-2 receiver (diff_pair @100R, LVDS-class lanes)"
EXPECT_CTRL = "host camera-control bank (3.3 V logic)"

DRAWS_NOTE = "RPi camera module budget (V2/IMX219 typ ~250 mA incl. I2C pull-ups)"
DRAWS_A = 0.300

PAIRS = (
    ("CSI_D0", "3", "2", "R1", "U1", "IO1", "IO2"),
    ("CSI_D1", "6", "5", "R2", "U1", "IO3", "IO4"),
    ("CSI_CLK", "9", "8", "R3", "U2", "IO1", "IO2"),
)


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('camera', meta)
