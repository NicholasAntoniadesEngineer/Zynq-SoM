#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/usb_jtag_connector/usb_jtag_connector.py.
CircuitSheetIr usb_jtag_connector(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("usb_jtag_connector", "USB-C UFP debug port -> CH347T (protected)", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("TYPE-C-31-M-12", p);
    }
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("USBLC6-2SC6", p);
    }
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0805_2012Metric", {{"LCSC", "C15850"}});
    c.net("+VBUS", {"J1.VBUS", "U1.5", "C1.1"}, std::nullopt);
    c.net("GND", {"C1.2"}, std::nullopt);
    c.net("DBG_USB_DP_CONN", {"J1.DP1", "J1.DP2", "U1.1"}, std::nullopt);
    c.net("DBG_USB_DM_CONN", {"J1.DN1", "J1.DN2", "U1.3"}, std::nullopt);
    {
        AuthoringPort t;
        c.port("USB_DP", {"U1.6"}, t, false);
    }
    {
        AuthoringPort t;
        c.port("USB_DM", {"U1.4"}, t, false);
    }
    {
        AuthoringPort t;
        t.kind = "usb_hs_pair";
        t.pair_with = "USB_DM";
        t.expect = meta.expect("USB_DP", "usb consumer (downstream device)");
        c.port_type("USB_DP", t);
    }
    c.net("GND", {"U1.2"}, std::nullopt);
    c.part("R1", "Device:R", "5.1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23186"}});
    c.net("DBG_R1_CC", {"R1.1", "J1.CC1"}, std::nullopt);
    c.net("GND", {"R1.2"}, std::nullopt);
    c.part("R2", "Device:R", "5.1k", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C23186"}});
    c.net("DBG_R2_CC", {"R2.1", "J1.CC2"}, std::nullopt);
    c.net("GND", {"R2.2"}, std::nullopt);
    c.net("CHASSIS_GND", {"J1.EH"}, std::nullopt);
    c.net("GND", {"J1.GND"}, std::nullopt);
    c.nc({"J1.SBU1", "J1.SBU2"});
    c.testpoint("+VBUS", std::nullopt);
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
