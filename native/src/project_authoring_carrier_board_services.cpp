#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/board_services/board_services.py.
CircuitSheetIr carrier_board_services(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("board_services", "Board services: ID-EEPROM, RTC, watchdog, QWIIC", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("24AA025E48T-I_OT", p);
    }
    c.net("+3V3_AUX", {"U1.VCC"}, std::nullopt);
    c.net("GND", {"U1.VSS"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_aux (PCA9306 isolated side of STM32_I2C2)";
        c.port("AUX_I2C_SCL", {"U1.SCL"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_aux (PCA9306 isolated side of STM32_I2C2)";
        c.port("AUX_I2C_SDA", {"U1.SDA"}, t, true);
    }
    c.net("+3V3_AUX", {"U1.A0"}, std::nullopt);
    c.net("GND", {"U1.A1"}, std::nullopt);
    c.decouple("U1.VCC", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("RV-3028-C7-32.768kHz-1ppm-TA-QC", p);
    }
    c.net("+3V3_AUX", {"U2.VDD"}, std::nullopt);
    c.net("GND", {"U2.VSS"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_aux (PCA9306 isolated side of STM32_I2C2)";
        c.port("AUX_I2C_SCL", {"U2.SCL"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_aux (PCA9306 isolated side of STM32_I2C2)";
        c.port("AUX_I2C_SDA", {"U2.SDA"}, t, true);
    }
    c.net("GND", {"U2.EVI"}, std::nullopt);
    c.nc({"U2.CLKOUT"});
    c.net("RTC_INT_N", {"U2.INT#"}, std::nullopt);
    c.pullup("U2.INT#", "10k", "+3V3_AUX", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.decouple("U2.VDD", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "BT1";
        c.use_part("KH-CR1220-2", p);
    }
    c.net("V_RTC_BAT", {"U2.VBACKUP", "BT1.1"}, std::nullopt);
    c.net("GND", {"BT1.2"}, std::nullopt);
    c.waive("decap_waivers", "V_RTC_BAT", "VBACKUP is the RV-3028 coin-cell backup input (a rechargeable ML1220, not a switching rail); the RTC regulates internally and a cap on the cell net is optional — no bypass fitted by design");
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        c.use_part("TPS3823-33DBVR", p);
    }
    c.net("+3V3_AUX", {"U3.VDD"}, std::nullopt);
    c.net("GND", {"U3.GND"}, std::nullopt);
    c.decouple("U3.VDD", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.nc({"U3.MR#"});
    c.auto_ref("R");
    c.part("R2", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    c.net("WDI_AUX", {"U3.WDI", "R2.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (PL bank-33 +3V3/LVCMOS33 — watchdog kick/event, xdc.py live)";
        c.port("WATCHDOG_KICK", {"R2.1"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (PL bank-33 +3V3/LVCMOS33 — watchdog kick/event, xdc.py live)";
        c.port("WATCHDOG_RST_N", {"U3.RESET#"}, t, true);
    }
    c.waive("reset_waivers", "WATCHDOG_RST_N", "TPS3823 RESET# is a push-pull supervisor OUTPUT driving a PL bank-33 input as a firmware-mediated event (not a POR line): no pull needed (push-pull; PL internal pull holds it when +3V3_AUX is OFF), no cap by design (logic-event edge)");
    c.draws("+3V3_AUX", 0.005, "ID-EEPROM ~1mA + RV-3028 <0.1mA + TPS3823 15uA + INT# 10k pull");
    c.field("C1", "LCSC", "C14663");
    c.field("R1", "LCSC", "C25804");
    c.field("C2", "LCSC", "C14663");
    c.field("C3", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
