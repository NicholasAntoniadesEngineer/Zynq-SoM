#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/hdmi_tx/hdmi_tx.py.
CircuitSheetIr hdmi_tx(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("hdmi_tx", "HDMI TX: TPD12S016 + HDMI-A receptacle (source)", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("TPD12S016PWR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("HDMI-019S", p);
    }
    c.net("+VDD_IO", {"U1.24"}, std::nullopt);
    c.net("+5V", {"U1.11"}, std::nullopt);
    c.decouple("U1.24", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U1.11", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("C5", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VDD_IO", {"C5.1"}, std::nullopt);
    c.net("GND", {"C5.2"}, std::nullopt);
    {
        AuthoringPort t;
        c.port("TMDS_D2_P", {"U1.23", "J1.1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_D2_N", {"U1.22", "J1.3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_D1_P", {"U1.21", "J1.4"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_D1_N", {"U1.20", "J1.6"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_D0_P", {"U1.18", "J1.7"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_D0_N", {"U1.17", "J1.9"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_CLK_P", {"U1.16", "J1.10"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_CLK_N", {"U1.15", "J1.12"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_D2_N";
        t.expect = meta.expect_kw("TMDS_D2_P");
        c.port_type("TMDS_D2_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_D1_N";
        t.expect = meta.expect_kw("TMDS_D1_P");
        c.port_type("TMDS_D1_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_D0_N";
        t.expect = meta.expect_kw("TMDS_D0_P");
        c.port_type("TMDS_D0_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_CLK_N";
        t.expect = meta.expect_kw("TMDS_CLK_P");
        c.port_type("TMDS_CLK_P", t);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CEC");
        c.port("CEC", {"U1.1"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = meta.bus("ddc", "HDMI_TX_DDC");
        t.speed_hz = 100000;
        t.expect = meta.expect_kw("DDC_SCL");
        c.port("DDC_SCL", {"U1.2"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = meta.bus("ddc", "HDMI_TX_DDC");
        t.speed_hz = 100000;
        t.expect = meta.expect_kw("DDC_SDA");
        c.port("DDC_SDA", {"U1.3"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("HPD");
        c.port("HPD", {"U1.4"}, t, false);
    }
    c.net("HDMI_TX_CON_CEC", {"U1.7", "J1.13"}, std::nullopt);
    c.net("HDMI_TX_CON_SCL", {"U1.8", "J1.15"}, std::nullopt);
    c.net("HDMI_TX_CON_SDA", {"U1.9", "J1.16"}, std::nullopt);
    c.net("HDMI_TX_CON_HPD", {"U1.10", "J1.19"}, std::nullopt);
    c.net("HDMI_TX_CON_5V0", {"U1.13", "J1.18"}, std::nullopt);
    c.part("C3", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("HDMI_TX_CON_5V0", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    c.part("C4", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("HDMI_TX_CON_5V0", {"C4.1"}, std::nullopt);
    c.net("GND", {"C4.2"}, std::nullopt);
    c.net("HDMI_TX_LS_OE", {"U1.5"}, std::nullopt);
    c.net("HDMI_TX_CT_HPD", {"U1.12"}, std::nullopt);
    c.pullup("U1.5", "10k", "+VDD_IO", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.pullup("U1.12", "10k", "+VDD_IO", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.net("GND", {"U1.6", "U1.14", "U1.19", "J1.2", "J1.5", "J1.8", "J1.11", "J1.17"}, std::nullopt);
    c.net("CHASSIS_GND", {"J1.20", "J1.21", "J1.22", "J1.23"}, std::nullopt);
    c.nc({"J1.14"});
    c.testpoint("+5V", std::nullopt);
    c.testpoint("DDC_SCL", std::nullopt);
    c.testpoint("DDC_SDA", std::nullopt);
    c.draws("+VDD_IO", 0.002, meta.note("draws_vcca", "TPD12S016 ICCA + LS_OE/CT_HPD straps"));
    c.draws("+5V", 0.055, meta.note("draws_5v", "HDMI source +5V to cable — TPD12S016 switch limit 55 mA (DS 7.3.10)"));
    c.waive("pull_waivers", "DDC_SCL", "DDC pull-ups integrated in TPD12S016 (DS 7.3.9/7.3.15)");
    c.waive("pull_waivers", "DDC_SDA", "DDC pull-ups integrated in TPD12S016 (DS 7.3.9/7.3.15)");
    c.field("C1", "LCSC", "C14663");
    c.field("C2", "LCSC", "C14663");
    c.field("R1", "LCSC", "C25804");
    c.field("R2", "LCSC", "C25804");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
