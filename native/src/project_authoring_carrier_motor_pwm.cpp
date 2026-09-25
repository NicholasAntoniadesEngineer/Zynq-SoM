#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/motor_pwm/motor_pwm.py.
CircuitSheetIr carrier_motor_pwm(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("motor_pwm", "8-ch PWM/ESC output buffer (5V, PL-isolating)", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("SN74HCT245PWR", p);
    }
    c.net("+5V", {"U1.VCC", "U1.DIR"}, std::nullopt);
    c.net("GND", {"U1.GND"}, std::nullopt);
    c.decouple("U1.VCC", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPort t;
        t.expect = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)";
        c.port("ESC_BUF_OE_N", {"U1.#OE"}, t, true);
    }
    c.pullup("U1.#OE", "10k", "+5V", "Device:R", "Resistor_SMD:R_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "RN1";
        c.use_part("4D03WGJ0330T5E", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "RN2";
        c.use_part("4D03WGJ0330T5E", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("HX_PZ2.54-3x8P_ZZ", p);
    }
    {
        AuthoringPort t;
        t.expect = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)";
        c.port("ESC_PWM_IN0", {"U1.A1"}, t, true);
    }
    c.net("ESC_SIG0", {"U1.B1", "RN1.1"}, std::nullopt);
    c.net("ESC_OUT0", {"RN1.8", "J1.1"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)";
        c.port("ESC_PWM_IN1", {"U1.A2"}, t, true);
    }
    c.net("ESC_SIG1", {"U1.B2", "RN1.2"}, std::nullopt);
    c.net("ESC_OUT1", {"RN1.7", "J1.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)";
        c.port("ESC_PWM_IN2", {"U1.A3"}, t, true);
    }
    c.net("ESC_SIG2", {"U1.B3", "RN1.3"}, std::nullopt);
    c.net("ESC_OUT2", {"RN1.6", "J1.3"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j2_connector (bank 33/13 PL — ESC PWM 0-3 + OE)";
        c.port("ESC_PWM_IN3", {"U1.A4"}, t, true);
    }
    c.net("ESC_SIG3", {"U1.B4", "RN1.4"}, std::nullopt);
    c.net("ESC_OUT3", {"RN1.5", "J1.4"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (bank 33 PL — ESC PWM 4-7)";
        c.port("ESC_PWM_IN4", {"U1.A5"}, t, true);
    }
    c.net("ESC_SIG4", {"U1.B5", "RN2.1"}, std::nullopt);
    c.net("ESC_OUT4", {"RN2.8", "J1.5"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (bank 33 PL — ESC PWM 4-7)";
        c.port("ESC_PWM_IN5", {"U1.A6"}, t, true);
    }
    c.net("ESC_SIG5", {"U1.B6", "RN2.2"}, std::nullopt);
    c.net("ESC_OUT5", {"RN2.7", "J1.6"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (bank 33 PL — ESC PWM 4-7)";
        c.port("ESC_PWM_IN6", {"U1.A7"}, t, true);
    }
    c.net("ESC_SIG6", {"U1.B7", "RN2.3"}, std::nullopt);
    c.net("ESC_OUT6", {"RN2.6", "J1.7"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = "som_j3_connector (bank 33 PL — ESC PWM 4-7)";
        c.port("ESC_PWM_IN7", {"U1.A8"}, t, true);
    }
    c.net("ESC_SIG7", {"U1.B8", "RN2.4"}, std::nullopt);
    c.net("ESC_OUT7", {"RN2.5", "J1.8"}, std::nullopt);
    c.net("+5V_MOTOR_IO", {"J1.9", "J1.10", "J1.11", "J1.12", "J1.13", "J1.14", "J1.15", "J1.16"}, std::nullopt);
    c.net("GND", {"J1.17", "J1.18", "J1.19", "J1.20", "J1.21", "J1.22", "J1.23", "J1.24"}, std::nullopt);
    c.auto_ref("D");
    c.part("D1", "Power_Protection:SRV05-4", "SRV05-4", "Package_TO_SOT_SMD:SOT-23-6", {{"LCSC", "C2836319"}});
    c.net("ESC_OUT0", {"D1.1"}, std::nullopt);
    c.net("ESC_OUT1", {"D1.3"}, std::nullopt);
    c.net("ESC_OUT2", {"D1.4"}, std::nullopt);
    c.net("ESC_OUT3", {"D1.6"}, std::nullopt);
    c.net("+5V", {"D1.5"}, std::nullopt);
    c.net("GND", {"D1.2"}, std::nullopt);
    c.auto_ref("D");
    c.part("D2", "Power_Protection:SRV05-4", "SRV05-4", "Package_TO_SOT_SMD:SOT-23-6", {{"LCSC", "C2836319"}});
    c.net("ESC_OUT4", {"D2.1"}, std::nullopt);
    c.net("ESC_OUT5", {"D2.3"}, std::nullopt);
    c.net("ESC_OUT6", {"D2.4"}, std::nullopt);
    c.net("ESC_OUT7", {"D2.6"}, std::nullopt);
    c.net("+5V", {"D2.5"}, std::nullopt);
    c.net("GND", {"D2.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        c.use_part("SY6280AAC", p);
    }
    c.net("+5V", {"U3.IN", "U3.EN"}, std::nullopt);
    c.net("+5V_MOTOR_IO", {"U3.OUT"}, std::nullopt);
    c.net("GND", {"U3.GND"}, std::nullopt);
    c.auto_ref("R");
    c.part("R2", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("MIO_ISET", {"U3.ISET", "R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.decouple("U3.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("C");
    c.part("C3", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+5V_MOTOR_IO", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    c.draws("+5V", 0.08, "HCT245 buffer + light servo allowance (ILIM 523mA)");
    c.testpoint("+5V_MOTOR_IO", std::nullopt);
    c.field("C1", "LCSC", "C14663");
    c.field("R1", "LCSC", "C25804");
    c.field("C2", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::project_builders
