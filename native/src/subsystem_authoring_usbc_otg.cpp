#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/usbc_otg/usbc_otg.py.
CircuitSheetIr usbc_otg(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("usbc_otg", "USB 2.0 HS OTG port (Type-C, host)", context);
    {
        AuthoringPartSelection p;
        p.ref = "J2";
        c.use_part("TYPE-C-31-M-12", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("TPS2051CDBVR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("USBLC6-2SC6", p);
    }
    c.net("+VBUS_SUPPLY", {"U1.IN"}, std::nullopt);
    {
        AuthoringPort t;
        c.port("VBUS", {"U1.OUT", "J2.VBUS"}, t, false);
    }
    c.part("R5", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("VBUS_EN");
        c.port("VBUS_EN", {"U1.EN(EN#)", "R5.1"}, t, false);
    }
    c.net("GND", {"U1.GND", "R5.2"}, std::nullopt);
    c.part("R3", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("FLT_N");
        c.port("FLT_N", {"U1.FLT#", "R3.2"}, t, false);
    }
    c.net("+VDD_LOGIC", {"R3.1"}, std::nullopt);
    c.decouple("U1.IN", {"100n"}, std::nullopt, "GND", "Device:C", "");
    c.part("C2", "Device:C", "22u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C45783"}});
    c.net("VBUS", {"C2.1"}, std::nullopt);
    c.net("GND", {"C2.2"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "C3";
        p.value = "100u";
        c.use_part("RVT1C101M0605_100UF_16V", p);
    }
    c.net("VBUS", {"C3.1"}, std::nullopt);
    c.net("GND", {"C3.2"}, std::nullopt);
    c.net("USBC_DP_CONN", {"J2.DP1", "J2.DP2", "U2.1"}, std::nullopt);
    c.net("USBC_DM_CONN", {"J2.DN1", "J2.DN2", "U2.3"}, std::nullopt);
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("USB_DP");
        c.port("USB_DP", {"U2.6"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("USB_DM");
        c.port("USB_DM", {"U2.4"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "usb_hs_pair";
        t.pair_with = "USB_DM";
        c.port_type("USB_DP", t);
    }
    c.net("VBUS", {"U2.5"}, std::nullopt);
    c.net("GND", {"U2.2"}, std::nullopt);
    c.part("R1", "Device:R", "56k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23206"}});
    c.net("VBUS", {"R1.1"}, std::nullopt);
    c.net("USBC_R1_CC", {"R1.2", "J2.CC1"}, std::nullopt);
    c.part("R2", "Device:R", "56k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23206"}});
    c.net("VBUS", {"R2.1"}, std::nullopt);
    c.net("USBC_R2_CC", {"R2.2", "J2.CC2"}, std::nullopt);
    c.part("R4", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C21190"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("USB_ID");
        c.port("USB_ID", {"R4.1"}, t, false);
    }
    c.net("GND", {"R4.2"}, std::nullopt);
    c.net("CHASSIS_GND", {"J2.EH"}, std::nullopt);
    c.net("GND", {"J2.GND"}, std::nullopt);
    c.nc({"J2.SBU1", "J2.SBU2"});
    c.testpoint("VBUS_EN", std::nullopt);
    c.draws("+VBUS_SUPPLY", 0.5, meta.note("draws_vbus", "downstream USB device budget, TPS2051C current-limited"));
    c.draws("+VDD_LOGIC", 0.0005, meta.note("draws_flt", "FLT# 100k pull-up on the logic rail"));
    c.field("C1", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
