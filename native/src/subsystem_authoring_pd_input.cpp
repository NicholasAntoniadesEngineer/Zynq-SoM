#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/pd_input/pd_input.py.
CircuitSheetIr pd_input(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("pd_input", "Power inlet: USB-C PD 20V/3A + TPS26631 eFuse", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("TYPE-C-31-M-12", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("TPS26631PWPR", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U2";
        c.use_part("USBLC6-2SC6", p);
    }
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}});
    c.part("D1", "Device:D_Zener", "SMBJ22A", "Diode_SMD:D_SMB", {{"LCSC", "C10214"}});
    c.net("+VBUS_CONN", {"J1.VBUS", "C1.1", "D1.1", "U1.IN", "U1.IN_SYS", "U1.UVLO"}, std::nullopt);
    c.net("GND", {"J1.GND", "C1.2", "D1.2"}, std::nullopt);
    c.nc({"U1.B_GATE", "U1.DRV"});
    c.part("R3", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    c.part("R4", "Device:R", "5.49k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C188263"}});
    c.net("PD_OVP_SET", {"U1.OVP", "R3.2", "R4.1"}, std::nullopt);
    c.net("+VBUS_CONN", {"R3.1"}, std::nullopt);
    c.part("R5", "Device:R", "5.1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23186"}});
    c.net("PD_ILIM_SET", {"U1.ILIM", "R5.1"}, std::nullopt);
    c.part("C3", "Device:C", "47n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C1622"}});
    c.net("PD_DVDT", {"U1.dVdT", "C3.1"}, std::nullopt);
    c.net("GND", {"U1.GND", "U1.EP", "U1.MODE", "U1.PGTH", "R4.2", "R5.2", "C3.2"}, std::nullopt);
    c.nc({"U1.SHDN#", "U1.IMON", "U1.PGOOD"});
    c.part("R6", "Device:R", "100k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C25803"}});
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("FLT_N");
        c.port("FLT_N", {"U1.FLT#", "R6.2"}, t, false);
    }
    c.net("+VDD_LOGIC", {"R6.1"}, std::nullopt);
    c.part("C2", "Device:C", "10u", "Capacitor_SMD:C_1210_3225Metric", {{"LCSC", "C596319"}});
    c.net("+VBUS_OUT", {"U1.OUT", "C2.1"}, std::nullopt);
    c.net("GND", {"C2.2"}, std::nullopt);
    {
        AuthoringPort t;
        c.port("CC1", {"J1.CC1"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("CC2", {"J1.CC2"}, t, false);
    }
    c.net("PD_USB_DP_CONN", {"J1.DP1", "J1.DP2", "U2.1"}, std::nullopt);
    c.net("PD_USB_DN_CONN", {"J1.DN1", "J1.DN2", "U2.3"}, std::nullopt);
    {
        AuthoringPort t;
        c.port("USB_D_P", {"U2.6"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("USB_D_N", {"U2.4"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "usb_hs_pair";
        t.pair_with = "USB_D_N";
        c.port_type("USB_D_P", t);
    }
    c.net("+VDD_LOGIC", {"U2.5"}, std::nullopt);
    c.net("GND", {"U2.2"}, std::nullopt);
    c.nc({"J1.SBU1", "J1.SBU2"});
    c.net("CHASSIS_GND", {"J1.EH"}, std::nullopt);
    c.testpoint("+VBUS_CONN", std::nullopt);
    c.testpoint("+VBUS_OUT", std::nullopt);
    c.waive("tp_waivers", "CHASSIS_GND", "chassis island is probeable at every connector shell tab (USB-C/HDMI/magjack); no pad needed");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
