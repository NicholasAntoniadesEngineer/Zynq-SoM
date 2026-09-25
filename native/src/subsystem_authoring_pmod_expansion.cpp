#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/pmod_expansion/pmod_expansion.py.
CircuitSheetIr pmod_expansion(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("pmod_expansion", "Pmod expansion (2x6, bank 13, ESD, gated 3V3)", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("SY6280AAC", p);
    }
    c.net("+VDD_PMOD", {"U1.IN"}, std::nullopt);
    c.net("+VSW_PMOD", {"U1.OUT"}, std::nullopt);
    c.net("GND", {"U1.GND"}, std::nullopt);
    c.net("EN_PMODX", {"U1.EN"}, std::nullopt);
    c.auto_ref("R");
    c.part("R1", "Device:R", "13k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C22797"}});
    c.net("BS_ISET_PMODX", {"U1.ISET", "R1.1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    c.decouple("U1.IN", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    c.auto_ref("C");
    c.part("C2", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VDD_PMOD", {"C2.1"}, std::nullopt);
    c.net("GND", {"C2.2"}, std::nullopt);
    c.decouple("U1.OUT", {"100n"}, std::nullopt, "GND", "Device:C", "Capacitor_SMD:C_0603_1608Metric");
    {
        AuthoringPartSelection p;
        p.ref = "SW1";
        c.use_part("DSHP04TSGER", p);
    }
    c.net("+VDD_PMOD", {"SW1.1", "SW1.3", "SW1.5", "SW1.7"}, std::nullopt);
    c.net("EN_PMODX", {"SW1.8"}, std::nullopt);
    c.auto_ref("R");
    c.part("R2", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.net("EN_PMODX", {"R2.1"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.nc({"SW1.2", "SW1.4", "SW1.6"});
    c.auto_ref("D");
    c.part("D1", "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", {{"LCSC", "C2286"}});
    c.auto_ref("R");
    c.part("R3", "Device:R", "330R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23138"}});
    c.net("+VSW_PMOD", {"D1.2"}, std::nullopt);
    c.net("BS_PG_PMODX", {"D1.1", "R3.1"}, std::nullopt);
    c.net("GND", {"R3.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("DS1024-2x6R2", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        p.value = "TPD4E1U06";
        c.use_part("TPD4E1U06DBVR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U3";
        p.value = "TPD4E1U06";
        c.use_part("TPD4E1U06DBVR", p);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO1");
        c.port("PMOD_IO1", {"J1.1", "U2.1"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO2");
        c.port("PMOD_IO2", {"J1.3", "U2.3"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO3");
        c.port("PMOD_IO3", {"J1.5", "U2.6"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO4");
        c.port("PMOD_IO4", {"J1.7", "U2.4"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO5");
        c.port("PMOD_IO5", {"J1.2", "U3.1"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO6");
        c.port("PMOD_IO6", {"J1.4", "U3.3"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO7");
        c.port("PMOD_IO7", {"J1.6", "U3.6"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("PMOD_IO8");
        c.port("PMOD_IO8", {"J1.8", "U3.4"}, t, false);
    }
    c.net("GND", {"U2.2", "U3.2"}, std::nullopt);
    c.nc({"U2.5", "U3.5"});
    c.auto_ref("C");
    c.part("C4", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.auto_ref("C");
    c.part("C5", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VSW_PMOD", {"J1.11", "J1.12", "C4.1", "C5.1"}, std::nullopt);
    c.net("GND", {"J1.9", "J1.10", "C4.2", "C5.2"}, std::nullopt);
    c.testpoint("+VSW_PMOD", std::nullopt);
    c.draws("+VSW_PMOD", 0.104, meta.note("draws_pmod", "1x Pmod module budget ~100 mA (Digilent spec) + status LED"));
    c.field("C1", "LCSC", "C14663");
    c.field("C3", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
