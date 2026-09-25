#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/hdmi_rx/hdmi_rx.py.
CircuitSheetIr hdmi_rx(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("hdmi_rx", "HDMI RX: HDMI-A sink + EDID EEPROM", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("HDMI-019S", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        p.lib_id = "Memory_EEPROM:M24C02-WMN";
        c.use_part("M24C02-WMN6TP", p);
    }
    c.part("R1", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.part("R2", "Device:R", "27k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22967"}});
    c.part("R3", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    c.part("R4", "Device:R", "15k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22809"}});
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("TPD4E02B04DQAR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        c.use_part("TPD4E02B04DQAR", p);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_D2_P", {"J1.1", "U2.IO1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_D2_N", {"J1.3", "U2.IO2"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_D1_P", {"J1.4", "U2.IO3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_D1_N", {"J1.6", "U2.IO4"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_D0_P", {"J1.7", "U3.IO1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_D0_N", {"J1.9", "U3.IO2"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_CLK_P", {"J1.10", "U3.IO3"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("TMDS_RX_CLK_N", {"J1.12", "U3.IO4"}, t, false);
    }
    c.net("GND", {"U2.GND", "U3.GND"}, std::nullopt);
    c.nc({"U2.NC", "U3.NC"});
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_RX_D2_N";
        t.expect = meta.expect_kw("TMDS_RX_D2_P");
        c.port_type("TMDS_RX_D2_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_RX_D1_N";
        t.expect = meta.expect_kw("TMDS_RX_D1_P");
        c.port_type("TMDS_RX_D1_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_RX_D0_N";
        t.expect = meta.expect_kw("TMDS_RX_D0_P");
        c.port_type("TMDS_RX_D0_P", t);
    }
    {
        AuthoringPort t;
        t.kind = "tmds_pair";
        t.pair_with = "TMDS_RX_CLK_N";
        t.expect = meta.expect_kw("TMDS_RX_CLK_P");
        c.port_type("TMDS_RX_CLK_P", t);
    }
    c.net("HDMI_RX_SDA", {"J1.16", "U1.5"}, std::nullopt);
    c.net("HDMI_RX_SCL", {"J1.15", "U1.6"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U4";
        c.use_part("TPD4E05U06DQAR", p);
    }
    c.net("HDMI_RX_SCL", {"U4.D1+"}, std::nullopt);
    c.net("HDMI_RX_SDA", {"U4.D1-"}, std::nullopt);
    c.net("GND", {"U4.GND"}, std::nullopt);
    c.nc({"U4.NC"});
    c.net("HDMI_RX_5V", {"J1.18", "U1.8", "U1.7", "C1.1", "R1.1", "R3.1"}, std::nullopt);
    c.net("GND", {"C1.2"}, std::nullopt);
    c.net("HDMI_RX_HPD", {"J1.19", "R1.2", "U4.D2-"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("HDMI_5V_DET");
        c.port("HDMI_5V_DET", {"R3.2", "R4.1"}, t, false);
    }
    c.net("GND", {"R4.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CEC");
        c.port("CEC", {"J1.13", "R2.2", "U4.D2+"}, t, false);
    }
    c.net("+VDD_LOGIC", {"R2.1"}, std::nullopt);
    c.net("GND", {"J1.2", "J1.5", "J1.8", "J1.11", "J1.17", "U1.1", "U1.2", "U1.3", "U1.4"}, std::nullopt);
    c.net("CHASSIS_GND", {"J1.20", "J1.21", "J1.22", "J1.23"}, std::nullopt);
    c.nc({"J1.14"});
    c.draws("+VDD_LOGIC", 0.001, meta.note("draws", "CEC 27k pull-up (EEPROM + EDID WC# are cable-5V-fed)"));
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
