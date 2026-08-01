from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta
from subsystems.basis import (
    JTAG_CRYSTAL_FREQ,
    JTAG_CRYSTAL_LOAD,
    JTAG_LDO_CIN,
    JTAG_LDO_COUT,
    JTAG_MODE_PULLDOWN,
    JTAG_OE_PULLUP,
    JTAG_RESET_PULL,
    JTAG_SUPPLY_BYPASS,
)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"
LCSC_1U = "C15849"
LCSC_10U = "C15850"
LCSC_16P = "C162205"
LCSC_10K = "C25804"
LCSC_100K = "C25803"

RAILS = ("+VBUS_USB", "+3V3_ISLAND", "GND")
PORTS = ("USB_DP", "USB_DM",
         "JTAG_TCK", "JTAG_TDI", "JTAG_TMS", "JTAG_TDO",
         "UART_RXD", "UART_TXD")
INTERFACE = RAILS + PORTS

DRAWS_NOTE = ("CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull network")
DRAWS_A = 0.045
RESET_WAIVER = ("CH347 RST#: 10k pull-up + the chip's built-in power-on reset "
                "(DS 5.1); no external RC cap fitted by design")

CRYSTAL_LEGS = ("DBG_XI", "DBG_XO")


def circuit(meta: Meta | dict | None = None) -> Circuit:
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("usb_jtag",
                "USB-JTAG/UART bridge: CH347T, isolated")

    c.use_part("AP2112K-3.3TRG1", ref="U4")
    c.net("+VBUS_USB", "U4.VIN", "U4.EN")
    c.net("+3V3_ISLAND", "U4.VOUT")
    c.net("GND", "U4.GND")
    c.nc("U4.NC")
    for cap in c.decouple("U4.VIN", JTAG_LDO_CIN, footprint=C0603):
        cap.fields["LCSC"] = LCSC_1U
    for cap in c.decouple("U4.VOUT", JTAG_LDO_COUT, footprint=C0805):
        cap.fields["LCSC"] = LCSC_10U
    for cap in c.decouple("U4.VOUT", JTAG_SUPPLY_BYPASS, footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    c.use_part("CH347T", ref="U1", value="CH347T")
    c.net("+3V3_ISLAND", "U1.14")
    c.net("GND", "U1.18")
    for cap in c.decouple("U1.14", JTAG_SUPPLY_BYPASS, footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # CH347 UD+/UD- take the bus DIRECTLY — the datasheet forbids a series R.
    c.port("USB_DP", "U1.17")
    c.port("USB_DM", "U1.16")
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM",
                expect=meta.expects.get("USB_DP"))

    c.use_part("1C208000BC0R", ref="Y1", value=JTAG_CRYSTAL_FREQ)
    c.net("DBG_XI", "U1.19", "Y1.1")
    c.net("DBG_XO", "U1.20", "Y1.3")
    c.net("GND", "Y1.2", "Y1.4")
    for sig in CRYSTAL_LEGS:
        cap = c.part(c.auto_ref("C"), "Device:C", JTAG_CRYSTAL_LOAD, C0603,
                     LCSC=LCSC_16P)
        c.net(sig, f"{cap.ref}.1")
        c.net("GND", f"{cap.ref}.2")

    c.net("DBG_RST_N", "U1.1")
    c.pullup("U1.1", JTAG_RESET_PULL,
             "+3V3_ISLAND").fields["LCSC"] = LCSC_10K

    c.net("DBG_MODE_DTR1", "U1.10")
    c.net("DBG_MODE_RTS1", "U1.13")
    r_d = c.part(c.auto_ref("R"), "Device:R", JTAG_MODE_PULLDOWN, R0603,
                 LCSC=LCSC_10K)
    c.net("DBG_MODE_DTR1", f"{r_d.ref}.1")
    c.net("GND", f"{r_d.ref}.2")
    r_r = c.part(c.auto_ref("R"), "Device:R", JTAG_MODE_PULLDOWN, R0603,
                 LCSC=LCSC_10K)
    c.net("DBG_MODE_RTS1", f"{r_r.ref}.1")
    c.net("GND", f"{r_r.ref}.2")

    c.nc("U1.2", "U1.9", "U1.11", "U1.12", "U1.15")

    c.use_part("SN74LVC125ADR", ref="U2")
    c.net("+3V3_ISLAND", "U2.14")
    c.net("GND", "U2.7")
    for cap in c.decouple("U2.14", JTAG_SUPPLY_BYPASS, footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # CH347 pin 8 = TDI (bridge OUT), pin 7 = TDO (bridge IN): reads inverted.
    c.net("DBG_FT_TCK", "U1.6")
    c.net("DBG_FT_TMS", "U1.5")
    c.net("DBG_FT_TDI", "U1.8")
    c.net("DBG_FT_TDO", "U1.7")

    c.net("DBG_FT_TCK", "U2.2")
    c.port("JTAG_TCK", "U2.3", **meta.expect_kw("JTAG_TCK"))
    c.net("DBG_FT_TDI", "U2.5")
    c.port("JTAG_TDI", "U2.6", **meta.expect_kw("JTAG_TDI"))
    c.net("DBG_FT_TMS", "U2.12")
    c.port("JTAG_TMS", "U2.11", **meta.expect_kw("JTAG_TMS"))
    c.port("JTAG_TDO", "U2.9", **meta.expect_kw("JTAG_TDO"))
    c.net("DBG_FT_TDO", "U2.8")

    c.net("DBG_JTAG_OE_N", "U2.1", "U2.4", "U2.10", "U2.13")
    c.pullup("U2.1", JTAG_OE_PULLUP,
             "+3V3_ISLAND").fields["LCSC"] = LCSC_100K
    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("DBG_JTAG_OE_N", "SW1.1")
    c.net("GND", "SW1.8")
    c.nc("SW1.2", "SW1.3", "SW1.4", "SW1.5", "SW1.6", "SW1.7")

    c.port("UART_RXD", "U1.3", **meta.expect_kw("UART_RXD"))
    c.port("UART_TXD", "U1.4", **meta.expect_kw("UART_TXD"))

    c.testpoint("+3V3_ISLAND")
    c.testpoint("UART_TXD")
    c.testpoint("UART_RXD")

    c.draws("+3V3_ISLAND", DRAWS_A, draws_note)
    c.waive_reset("DBG_RST_N", RESET_WAIVER)

    return meta.finish(c)
