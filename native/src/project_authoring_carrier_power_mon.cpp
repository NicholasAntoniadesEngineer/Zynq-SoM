#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/power_mon/power_mon.py.
CircuitSheetIr carrier_power_mon(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("power_mon", "Rail telemetry: 2x INA3221 + shunts (I2C 0x40/41)", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("INA3221AIRGVR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("INA3221AIRGVR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "RS1";
        p.value = "10mR";
        c.use_part("RLM12FTCMR010", p);
    }
    c.net("+VIN", {"RS1.1", "U1.IN+1"}, std::nullopt);
    c.net("+VIN_SYS", {"RS1.2", "U1.IN-1"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "RS2";
        p.value = "10mR";
        c.use_part("RLM12FTCMR010", p);
    }
    c.net("+5V_REG", {"RS2.1", "U1.IN+2"}, std::nullopt);
    c.net("+5V", {"RS2.2", "U1.IN-2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "RS3";
        p.value = "10mR";
        c.use_part("RLM12FTCMR010", p);
    }
    c.net("+3V3_REG", {"RS3.1", "U1.IN+3"}, std::nullopt);
    c.net("+3V3", {"RS3.2", "U1.IN-3"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "RS4";
        p.value = "20mR";
        c.use_part("RLM12FTCMR020", p);
    }
    c.net("+1V8_REG", {"RS4.1", "U2.IN+1"}, std::nullopt);
    c.net("+1V8", {"RS4.2", "U2.IN-1"}, std::nullopt);
    c.net("GND", {"U2.IN+2", "U2.IN-2", "U2.IN+3", "U2.IN-3"}, std::nullopt);
    c.net("+3V3_SC", {"U1.VS", "U1.VPU", "U2.VS", "U2.VPU"}, std::nullopt);
    c.net("GND", {"U1.GND", "U1.PAD", "U2.GND", "U2.PAD"}, std::nullopt);
    c.net("GND", {"U1.A0"}, std::nullopt);
    c.net("+3V3_SC", {"U2.A0"}, std::nullopt);
    c.decouple("U1.VS", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.decouple("U2.VS", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.part("C3", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+3V3_SC", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j1_connector";
        c.port("STM32_I2C2_SDA", {"U1.SDA", "U2.SDA"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j1_connector";
        c.port("STM32_I2C2_SCL", {"U1.SCL", "U2.SCL"}, t, true);
    }
    c.part("R1", "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25804"}});
    {
        AuthoringPort t;
        t.expect = "bringup (TCA9535 spare port P11)";
        c.port("PMON_ALERT_N", {"U1.CRITICAL", "U2.CRITICAL", "R1.2"}, t, true);
    }
    c.net("+3V3_SC", {"R1.1"}, std::nullopt);
    c.nc({"U1.WARNING", "U1.PV", "U1.TC", "U2.WARNING", "U2.PV", "U2.TC"});
    c.draws("+3V3_SC", 0.002, "2x INA3221 ~0.7 mA + ALERT pull-up");
    c.waive("tp_waivers", "+VIN_SYS", "reg-side of RS1 — probe across the shunt (the +VIN @ pd_input TP is the post-shunt/load side)");
    c.waive("tp_waivers", "+5V_REG", "reg-side of RS2 — probe across the shunt (the +5V TP is the post-shunt/load side)");
    c.waive("tp_waivers", "+3V3_REG", "reg-side of RS3 — probe across the shunt (the +3V3 TP is the post-shunt/load side)");
    c.waive("tp_waivers", "+1V8_REG", "reg-side of RS4 — probe across the shunt (the +1V8 TP is the post-shunt/load side)");
    c.field("C1", "LCSC", "C14663");
    c.field("C2", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
