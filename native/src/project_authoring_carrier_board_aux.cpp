#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/board_aux/board_aux.py.
CircuitSheetIr carrier_board_aux(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("board_aux", "Board services: gated +3V3_AUX rail + PCA9306 I2C isolator", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("SY6280AAC", p);
    }
    c.net("+3V3", {"U1.IN"}, std::nullopt);
    c.net("+3V3_AUX", {"U1.OUT"}, std::nullopt);
    c.net("GND", {"U1.GND"}, std::nullopt);
    c.net("EN_AUX", {"U1.EN"}, std::nullopt);
    c.auto_ref("R");
    c.part("R1", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BS_ISET_AUX", {"U1.ISET", "R1.1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    c.decouple("U1.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U1.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("C");
    c.part("C3", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+3V3_AUX", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "SW1";
        c.use_part("DSHP04TSGER", p);
    }
    c.net("+3V3", {"SW1.1", "SW1.3", "SW1.5", "SW1.7"}, std::nullopt);
    c.net("EN_AUX", {"SW1.8"}, std::nullopt);
    c.auto_ref("R");
    c.part("R2", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("EN_AUX", {"R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.nc({"SW1.2", "SW1.4", "SW1.6"});
    c.auto_ref("D");
    c.part("D1", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R3", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+3V3_AUX", {"D1.2"}, std::nullopt);
    c.net("BS_PG_AUX", {"D1.1", "R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("PCA9306DCUR", p);
    }
    c.net("GND", {"U2.GND"}, std::nullopt);
    c.net("+3V3_SC", {"U2.VREF1"}, std::nullopt);
    c.decouple("U2.VREF1", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "STM32_I2C2 management bus (bringup_rails / usb_pd / power_mon)";
        c.port("STM32_I2C2_SCL", {"U2.SCL1"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "STM32_I2C2 management bus (bringup_rails / usb_pd / power_mon)";
        c.port("STM32_I2C2_SDA", {"U2.SDA1"}, t, true);
    }
    c.net("+3V3_AUX", {"U2.VREF2"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_services (the gated peripherals on the isolated AUX bus)";
        c.port("AUX_I2C_SCL", {"U2.SCL2"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_services (the gated peripherals on the isolated AUX bus)";
        c.port("AUX_I2C_SDA", {"U2.SDA2"}, t, true);
    }
    c.net("AUX_ISO_EN", {"U2.EN"}, std::nullopt);
    c.pullup("U2.EN", "100k", "+3V3_AUX", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.pullup("U2.SCL2", "4k7", "+3V3_AUX", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.pullup("U2.SDA2", "4k7", "+3V3_AUX", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.decouple("U2.VREF2", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.draws("+3V3_AUX", 0.006, "status LED 3.9mA + 2x4k7 AUX-bus pull-ups");
    c.testpoint("+3V3_AUX", std::nullopt);
    c.testpoint("AUX_I2C_SCL", std::nullopt);
    c.testpoint("AUX_I2C_SDA", std::nullopt);
    c.field("C1", "LCSC", "C14663");
    c.field("C2", "LCSC", "C14663");
    c.field("C4", "LCSC", "C14663");
    c.field("R4", "LCSC", "C25803");
    c.field("R5", "LCSC", "C23162");
    c.field("R6", "LCSC", "C23162");
    c.field("C5", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
