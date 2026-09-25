#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/hdmi_rx_term/hdmi_rx_term.py.
CircuitSheetIr carrier_hdmi_rx_term(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("hdmi_rx_term", "HDMI-RX TMDS sink termination (8x49.9R to AVCC=+3V3)", context);
    c.part("R1", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_D2_P", {"R1.1"}, t, true);
    }
    c.net("+3V3", {"R1.2"}, std::nullopt);
    c.part("R2", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_D2_N", {"R2.1"}, t, true);
    }
    c.net("+3V3", {"R2.2"}, std::nullopt);
    c.part("R3", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_D1_P", {"R3.1"}, t, true);
    }
    c.net("+3V3", {"R3.2"}, std::nullopt);
    c.part("R4", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_D1_N", {"R4.1"}, t, true);
    }
    c.net("+3V3", {"R4.2"}, std::nullopt);
    c.part("R5", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_D0_P", {"R5.1"}, t, true);
    }
    c.net("+3V3", {"R5.2"}, std::nullopt);
    c.part("R6", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_D0_N", {"R6.1"}, t, true);
    }
    c.net("+3V3", {"R6.2"}, std::nullopt);
    c.part("R7", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_CLK_P", {"R7.1"}, t, true);
    }
    c.net("+3V3", {"R7.2"}, std::nullopt);
    c.part("R8", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}});
    {
        AuthoringPort t;
        t.expect = "som_j2_j3_connector (FPGA bank 33 — TMDS RX receiver end)";
        c.port("HDMI_RX_CLK_N", {"R8.1"}, t, true);
    }
    c.net("+3V3", {"R8.2"}, std::nullopt);
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("C2", "Device:C", "1u", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C15849"}});
    c.net("+3V3", {"C1.1", "C2.1"}, std::nullopt);
    c.net("GND", {"C1.2", "C2.2"}, std::nullopt);
    c.draws("+3V3", 0.064, "8x TMDS sink termination 49.9R to AVCC (~8 mA/line driven low)");
    return meta.finish(c);
}
} // namespace schgen::project_builders
