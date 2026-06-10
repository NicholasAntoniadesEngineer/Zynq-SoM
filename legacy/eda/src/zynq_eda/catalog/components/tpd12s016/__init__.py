"""TPD12S016PWR HDMI ESD / level translator (TX + RX variants).

Same silicon used twice on the carrier: once on the HDMI source path
(``TPD12S016_TX_REFCIRCUIT`` — drives the connector's +5V VBUS, sources
HPD), once on the HDMI sink path (``TPD12S016_RX_REFCIRCUIT`` — consumes
+5V coming from the source, generates HPD). Pin assignments differ but
the part is identical; one datasheet covers both.
"""

from zynq_eda.catalog.components.tpd12s016.refcircuit import (
    TPD12S016_RX_REFCIRCUIT,
    TPD12S016_TX_REFCIRCUIT,
)

__all__ = [
    "TPD12S016_RX_REFCIRCUIT",
    "TPD12S016_TX_REFCIRCUIT",
]
