from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    USB_PD_CC_FILTER,
    USB_PD_VBUS_BYPASS,
    USB_PD_VDD_BULK,
    USB_PD_VDD_BYPASS,
)

LIB_ID = "Interface_USB:FUSB302BMPX"
FOOTPRINT = "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm"

LCSC_BYPASS = "C14663"
LCSC_BULK = "C15850"
LCSC_CC_FILTER = "C113796"

RAILS = ("+VDD_LOGIC", "+VBUS_SENSE", "GND")
PORTS = ("CC1", "CC2", "I2C_SDA", "I2C_SCL", "INT_N")
INTERFACE = RAILS + PORTS

I2C_BUS = "USB_PD_I2C"
I2C_SPEED_HZ = 400_000

DRAWS_NOTE = ("FUSB302B VDD (<1 mA); INT_N/I2C pull-ups are shared and live "
              "off-subsystem")
DRAWS_A = 0.002

RAIL_WORST_V = {"+VDD_LOGIC": 3.3, "+VBUS_SENSE": 21.0, "GND": 0.0}
VBUS_SENSE_PIN_ABSMAX_V = 28.0


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    i2c_bus = meta.bus("i2c", I2C_BUS)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("usb_pd", "USB-PD: FUSB302B Type-C controller")
    c.use_part("FUSB302BMPX", ref="U1", lib_id=LIB_ID, footprint=FOOTPRINT)

    # +VDD_LOGIC must be ALWAYS-ON: the PHY brings the 20 V in, so it cannot
    # depend on a rail it creates. +VBUS_SENSE is raw, ahead of any eFuse.
    c.net("+VDD_LOGIC", "U1.3", "U1.4")
    c.net("+VBUS_SENSE", "U1.2")
    c.net("GND", "U1.8", "U1.9", "U1.15")
    for cap, lcsc in zip(c.decouple("U1.3", USB_PD_VDD_BYPASS,
                                    USB_PD_VDD_BULK),
                         (LCSC_BYPASS, LCSC_BULK), strict=True):
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.2", USB_PD_VBUS_BYPASS):
        cap.fields["LCSC"] = LCSC_BYPASS

    cc1 = c.port("CC1", "U1.10", "U1.11", **meta.expect_kw("CC1"))
    cc2 = c.port("CC2", "U1.1", "U1.14", **meta.expect_kw("CC2"))
    for net in (cc1, cc2):
        ref = c.auto_ref("C")
        c.part(ref, "Device:C", USB_PD_CC_FILTER, LCSC=LCSC_CC_FILTER)
        c.net(net.name, f"{ref}.1")
        c.net("GND", f"{ref}.2")

    c.port("I2C_SDA", "U1.7",
           kind="i2c", role="sda", bus=i2c_bus, speed_hz=I2C_SPEED_HZ,
           **meta.expect_kw("I2C_SDA"))
    c.port("I2C_SCL", "U1.6",
           kind="i2c", role="scl", bus=i2c_bus, speed_hz=I2C_SPEED_HZ,
           **meta.expect_kw("I2C_SCL"))
    c.port("INT_N", "U1.5", **meta.expect_kw("INT_N"))

    c.nc("U1.12", "U1.13")

    c.draws("+VDD_LOGIC", DRAWS_A, draws_note)

    return meta.finish(c)
