#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/usb_jtag/usb_jtag.py.
CircuitSheetIr usb_jtag(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("usb_jtag", "USB-JTAG/UART bridge: CH347T, isolated", context);
    {
        AuthoringPartSelection p;
        p.ref = "U4";
        c.use_part("AP2112K-3.3TRG1", p);
    }
    c.net("+VBUS_USB", {"U4.VIN", "U4.EN"}, std::nullopt);
    c.net("+3V3_ISLAND", {"U4.VOUT"}, std::nullopt);
    c.net("GND", {"U4.GND"}, std::nullopt);
    c.nc({"U4.NC"});
    c.decouple("U4.VIN", {"1u"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U4.VOUT", {"10u"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0805_2012Metric");
    c.decouple("U4.VOUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        p.value = "CH347T";
        c.use_part("CH347T", p);
    }
    c.net("+3V3_ISLAND", {"U1.14"}, std::nullopt);
    c.net("GND", {"U1.18"}, std::nullopt);
    c.decouple("U1.14", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPort t;
        c.port("USB_DP", {"U1.17"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("USB_DM", {"U1.16"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "usb_hs_pair";
        t.pair_with = "USB_DM";
        t.expect = meta.expect("USB_DP", std::nullopt);
        c.port_type("USB_DP", t);
    }
    {
        AuthoringPartSelection p;
        p.ref = "Y1";
        p.value = "8MHz";
        c.use_part("1C208000BC0R", p);
    }
    c.net("DBG_XI", {"U1.19", "Y1.1"}, std::nullopt);
    c.net("DBG_XO", {"U1.20", "Y1.3"}, std::nullopt);
    c.net("GND", {"Y1.2", "Y1.4"}, std::nullopt);
    c.auto_ref("C");
    c.part("C5", "Device:C", "16p", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C162205"}});
    c.net("DBG_XI", {"C5.1"}, std::nullopt);
    c.net("GND", {"C5.2"}, std::nullopt);
    c.auto_ref("C");
    c.part("C6", "Device:C", "16p", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C162205"}});
    c.net("DBG_XO", {"C6.1"}, std::nullopt);
    c.net("GND", {"C6.2"}, std::nullopt);
    c.net("DBG_RST_N", {"U1.1"}, std::nullopt);
    c.pullup("U1.1", "10k", "+3V3_ISLAND", "Device:R", "");
    c.net("DBG_MODE_DTR1", {"U1.10"}, std::nullopt);
    c.net("DBG_MODE_RTS1", {"U1.13"}, std::nullopt);
    c.auto_ref("R");
    c.part("R2", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("DBG_MODE_DTR1", {"R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.auto_ref("R");
    c.part("R3", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.net("DBG_MODE_RTS1", {"R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    c.nc({"U1.2", "U1.9", "U1.11", "U1.12", "U1.15"});
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("SN74LVC125ADR", p);
    }
    c.net("+3V3_ISLAND", {"U2.14"}, std::nullopt);
    c.net("GND", {"U2.7"}, std::nullopt);
    c.decouple("U2.14", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.net("DBG_FT_TCK", {"U1.6"}, std::nullopt);
    c.net("DBG_FT_TMS", {"U1.5"}, std::nullopt);
    c.net("DBG_FT_TDI", {"U1.8"}, std::nullopt);
    c.net("DBG_FT_TDO", {"U1.7"}, std::nullopt);
    c.net("DBG_FT_TCK", {"U2.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("JTAG_TCK");
        c.port("JTAG_TCK", {"U2.3"}, t, false);
    }
    c.net("DBG_FT_TDI", {"U2.5"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("JTAG_TDI");
        c.port("JTAG_TDI", {"U2.6"}, t, false);
    }
    c.net("DBG_FT_TMS", {"U2.12"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("JTAG_TMS");
        c.port("JTAG_TMS", {"U2.11"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("JTAG_TDO");
        c.port("JTAG_TDO", {"U2.9"}, t, false);
    }
    c.net("DBG_FT_TDO", {"U2.8"}, std::nullopt);
    c.net("DBG_JTAG_OE_N", {"U2.1", "U2.4", "U2.10", "U2.13"}, std::nullopt);
    c.pullup("U2.1", "100k", "+3V3_ISLAND", "Device:R", "");
    {
        AuthoringPartSelection p;
        p.ref = "SW1";
        c.use_part("DSHP04TSGER", p);
    }
    c.net("DBG_JTAG_OE_N", {"SW1.1"}, std::nullopt);
    c.net("GND", {"SW1.8"}, std::nullopt);
    c.nc({"SW1.2", "SW1.3", "SW1.4", "SW1.5", "SW1.6", "SW1.7"});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("UART_RXD");
        c.port("UART_RXD", {"U1.3"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("UART_TXD");
        c.port("UART_TXD", {"U1.4"}, t, false);
    }
    c.testpoint("+3V3_ISLAND", std::nullopt);
    c.testpoint("UART_TXD", std::nullopt);
    c.testpoint("UART_RXD", std::nullopt);
    c.draws("+3V3_ISLAND", 0.045, meta.note("draws", "CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull network"));
    c.waive("reset_waivers", "DBG_RST_N", "CH347 RST#: 10k pull-up + the chip's built-in power-on reset (DS 5.1); no external RC cap fitted by design");
    c.field("C1", "LCSC", "C15849");
    c.field("C2", "LCSC", "C15850");
    c.field("C3", "LCSC", "C14663");
    c.field("C4", "LCSC", "C14663");
    c.field("R1", "LCSC", "C25804");
    c.field("C7", "LCSC", "C14663");
    c.field("R4", "LCSC", "C25803");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
