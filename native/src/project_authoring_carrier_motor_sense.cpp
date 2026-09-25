#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/motor_sense/motor_sense.py.
CircuitSheetIr carrier_motor_sense(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("motor_sense", "ESC motor-rail telemetry: INA3221 + 10mR shunt (I2C 0x42)", context);
    {
        AuthoringPartSelection p;
        p.ref = "J2";
        c.use_part("XT60PW-M", p);
    }
    c.net("ESC_VRAIL_IN", {"J2.+"}, std::nullopt);
    c.net("GND", {"J2.-", "J2.3", "J2.4"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "D1";
        c.use_part("SMBJ28A", p);
    }
    c.net("ESC_VRAIL_IN", {"D1.K"}, std::nullopt);
    c.net("GND", {"D1.A"}, std::nullopt);
    c.auto_ref("C");
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.net("ESC_VRAIL_IN", {"C1.1"}, std::nullopt);
    c.net("GND", {"C1.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "RS1";
        p.value = "10mR";
        c.use_part("RLM12FTCMR010", p);
    }
    c.net("ESC_VRAIL_IN", {"RS1.1"}, std::nullopt);
    c.net("ESC_VRAIL", {"RS1.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "J3";
        c.use_part("XT60PW-M", p);
    }
    c.net("ESC_VRAIL", {"J3.+"}, std::nullopt);
    c.net("GND", {"J3.-", "J3.3", "J3.4"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("INA3221AIRGVR", p);
    }
    c.net("ESC_VRAIL_IN", {"U2.IN+1"}, std::nullopt);
    c.net("ESC_VRAIL", {"U2.IN-1"}, std::nullopt);
    c.net("GND", {"U2.IN+2", "U2.IN-2", "U2.IN+3", "U2.IN-3"}, std::nullopt);
    c.net("+3V3_SC", {"U2.VS", "U2.VPU"}, std::nullopt);
    c.net("GND", {"U2.GND", "U2.PAD"}, std::nullopt);
    c.decouple("U2.VS", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("C");
    c.part("C3", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+3V3_SC", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j1_connector (STM32_I2C2 SC management bus)";
        c.port("STM32_I2C2_SDA", {"U2.SDA", "U2.A0"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "STM32_I2C2";
        t.speed_hz = 400000;
        t.expect = "som_j1_connector (STM32_I2C2 SC management bus)";
        c.port("STM32_I2C2_SCL", {"U2.SCL"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = "som_j2_connector (bank 13 PL — ESC_FAULT_N)";
        c.port("ESC_FAULT_N", {"U2.CRITICAL"}, t, true);
    }
    c.pullup("U2.CRITICAL", "10k", "+3V3_SC", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    c.nc({"U2.WARNING", "U2.PV", "U2.TC"});
    c.auto_ref("C");
    c.part("C4", "Device:C_Polarized", "470uF/35V", "Capacitor_SMD:CP_Elec_10x10.5", {{"LCSC", "C976030"}});
    c.net("ESC_VRAIL", {"C4.1"}, std::nullopt);
    c.net("GND", {"C4.2"}, std::nullopt);
    c.draws("+3V3_SC", 0.002, "INA3221 ~0.35 mA + CRITICAL pull-up");
    c.field("C2", "LCSC", "C14663");
    c.field("R1", "LCSC", "C25804");
    return meta.finish(c);
}
} // namespace schgen::project_builders
