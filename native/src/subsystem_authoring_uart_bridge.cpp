#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/uart_bridge/uart_bridge.py.
CircuitSheetIr uart_bridge(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("uart_bridge", "UART bridge: CP2102N USB-UART", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        p.value = "CP2102N-A02";
        c.use_part("CP2102N-A02-GQFN24R", p);
    }
    c.net("+VDD_IO", {"U1.5", "U1.6", "U1.7"}, std::nullopt);
    c.net("GND", {"U1.2", "U1.25"}, std::nullopt);
    c.decouple("U1.7", {"100n", "10u"}, std::nullopt, "GND", "Device:C", "");
    c.decouple("U1.6", {"100n"}, std::nullopt, "GND", "Device:C", "");
    c.decouple("U1.5", {"100n"}, std::nullopt, "GND", "Device:C", "");
    c.net("CP2102N_RST_N", {"U1.9"}, std::nullopt);
    c.pullup("U1.9", "1k", "+VDD_IO", "Device:R", "");
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("USB_VBUS");
        c.port("USB_VBUS", {}, t, false);
    }
    c.net("CP2102N_VBUS_SNS", {"U1.8"}, std::nullopt);
    c.series("USB_VBUS", "CP2102N_VBUS_SNS", "22k1", "R", "Device:R", "");
    c.series("CP2102N_VBUS_SNS", "GND", "47k5", "R", "Device:R", "");
    {
        AuthoringPort t;
        c.port("USB_DP", {"U1.3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("USB_DM", {"U1.4"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "usb_hs_pair";
        t.pair_with = "USB_DM";
        t.expect = meta.expect("USB_DP", std::nullopt);
        c.port_type("USB_DP", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("UART_TXD");
        c.port("UART_TXD", {"U1.21"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("UART_RXD");
        c.port("UART_RXD", {"U1.20"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("UART_RTS_N");
        c.port("UART_RTS_N", {"U1.19"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("UART_CTS_N");
        c.port("UART_CTS_N", {"U1.18"}, t, false);
    }
    c.nc({"U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15", "U1.16", "U1.17", "U1.22", "U1.23", "U1.24"});
    c.testpoint("UART_RXD", std::nullopt);
    c.testpoint("UART_TXD", std::nullopt);
    c.draws("+VDD_IO", 0.015, meta.note("draws", "CP2102N active ~14 mA typ + RST 1k pull-up"));
    c.waive("reset_waivers", "CP2102N_RST_N", "open-drain RST: 1k pull-up only, internal POR; no RC cap");
    c.field("C1", "LCSC", "C14663");
    c.field("C2", "LCSC", "C15850");
    c.field("C3", "LCSC", "C14663");
    c.field("C4", "LCSC", "C14663");
    c.field("R1", "LCSC", "C21190");
    c.field("R2", "LCSC", "C25961");
    c.field("R3", "LCSC", "C23061");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
