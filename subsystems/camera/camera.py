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
INTERFACE = RAILS + PORTS

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
    meta = Meta(meta)
    i2c_bus = meta.bus("i2c", I2C_BUS)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("camera", "RPi camera port: 2-lane MIPI CSI-2 (15P FFC)")
    c.use_part("SFW15R-1STE1LF", ref="J1")

    c.use_part("TPD4E02B04DQAR", ref="U1")
    c.use_part("TPD4E02B04DQAR", ref="U2")
    for name, p_pin, n_pin, term, esd, io_p, io_n in PAIRS:
        c.part(term, "Device:R", CAMERA_LANE_TERM, R0603, LCSC=LCSC_LANE_TERM)
        c.port(f"{name}_P", f"J1.{p_pin}", f"{term}.1", f"{esd}.{io_p}")
        c.port(f"{name}_N", f"J1.{n_pin}", f"{term}.2", f"{esd}.{io_n}")
        c.port_type(f"{name}_P", kind="diff_pair", pair_with=f"{name}_N",
                    impedance=LANE_IMPEDANCE,
                    expect=meta.expects.get(f"{name}_P", EXPECT_CSI))
    c.net("GND", "U1.GND", "U2.GND")
    c.nc("U1.6", "U1.7", "U1.9", "U1.10")
    c.nc("U2.6", "U2.7", "U2.9", "U2.10")

    c.part("R4", "Device:R", CAMERA_I2C_PULL, R0603, LCSC=LCSC_I2C_PULL)
    c.part("R5", "Device:R", CAMERA_I2C_PULL, R0603, LCSC=LCSC_I2C_PULL)
    c.port("CAM_SCL", "J1.13", "R4.2", "U2.4", kind="i2c", role="scl",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("CAM_SCL"))
    c.port("CAM_SDA", "J1.14", "R5.2", "U2.5", kind="i2c", role="sda",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("CAM_SDA"))
    c.net("+VDD_CAM", "R4.1", "R5.1")
    c.port("CAM_EN", "J1.11", **meta.expect_kw("CAM_EN"))
    c.port("CAM_LED", "J1.12", **meta.expect_kw("CAM_LED"))

    c.part("C1", "Device:C", CAMERA_RAIL_BYPASS, C0603, LCSC=LCSC_BYPASS)
    c.part("C2", "Device:C", CAMERA_RAIL_BULK, C0805, LCSC=LCSC_BULK)
    c.net("+VDD_CAM", "J1.15", "C1.1", "C2.1")
    c.net("GND", "J1.1", "J1.4", "J1.7", "J1.10", "C1.2", "C2.2",
          "J1.16", "J1.17")

    c.testpoint("CAM_SCL")
    c.testpoint("CAM_SDA")
    c.testpoint("CAM_EN")

    c.draws("+VDD_CAM", DRAWS_A, draws_note)
    return meta.finish(c)
