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
from schgen.core.authoring import interface as _native_interface
INTERFACE = _native_interface('usb_pd')

I2C_BUS = "USB_PD_I2C"
I2C_SPEED_HZ = 400_000

DRAWS_NOTE = ("FUSB302B VDD (<1 mA); INT_N/I2C pull-ups are shared and live "
              "off-subsystem")
DRAWS_A = 0.002

RAIL_WORST_V = {"+VDD_LOGIC": 3.3, "+VBUS_SENSE": 21.0, "GND": 0.0}
VBUS_SENSE_PIN_ABSMAX_V = 28.0


def circuit(meta: Meta | dict | None = None) -> Circuit:
    from schgen.core.authoring import circuit as _native_circuit
    return _native_circuit('usb_pd', meta)
