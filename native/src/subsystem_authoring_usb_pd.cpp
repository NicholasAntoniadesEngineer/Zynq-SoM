#include "schgen/subsystem_authoring.hpp"

namespace schgen::subsystem_builders {
// Migrated construction operations from subsystems/usb_pd/usb_pd.py.
CircuitSheetIr usb_pd(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("usb_pd", "USB-PD: FUSB302B Type-C controller", context);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        p.lib_id = "Interface_USB:FUSB302BMPX";
        p.footprint = "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm";
        c.use_part("FUSB302BMPX", p);
    }
    c.net("+VDD_LOGIC", {"U1.3", "U1.4"}, std::nullopt);
    c.net("+VBUS_SENSE", {"U1.2"}, std::nullopt);
    c.net("GND", {"U1.8", "U1.9", "U1.15"}, std::nullopt);
    c.decouple("U1.3", {"100n", "10u"}, std::nullopt, "GND", "Device:C", "");
    c.decouple("U1.2", {"100n"}, std::nullopt, "GND", "Device:C", "");
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CC1");
        c.port("CC1", {"U1.10", "U1.11"}, t, false);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("CC2");
        c.port("CC2", {"U1.1", "U1.14"}, t, false);
    }
    c.auto_ref("C");
    c.part("C4", "Device:C", "200p", "", {{"LCSC", "C113796"}});
    c.net("CC1", {"C4.1"}, std::nullopt);
    c.net("GND", {"C4.2"}, std::nullopt);
    c.auto_ref("C");
    c.part("C5", "Device:C", "200p", "", {{"LCSC", "C113796"}});
    c.net("CC2", {"C5.1"}, std::nullopt);
    c.net("GND", {"C5.2"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = meta.bus("i2c", "USB_PD_I2C");
        t.speed_hz = 400000;
        t.expect = meta.expect_kw("I2C_SDA");
        c.port("I2C_SDA", {"U1.7"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = meta.bus("i2c", "USB_PD_I2C");
        t.speed_hz = 400000;
        t.expect = meta.expect_kw("I2C_SCL");
        c.port("I2C_SCL", {"U1.6"}, t, true);
    }
    {
        AuthoringPort t;
        t.expect = meta.expect_kw("INT_N");
        c.port("INT_N", {"U1.5"}, t, false);
    }
    c.nc({"U1.12", "U1.13"});
    c.draws("+VDD_LOGIC", 0.002, meta.note("draws", "FUSB302B VDD (<1 mA); INT_N/I2C pull-ups are shared and live off-subsystem"));
    c.field("C1", "LCSC", "C14663");
    c.field("C2", "LCSC", "C15850");
    c.field("C3", "LCSC", "C14663");
    return meta.finish(c);
}
} // namespace schgen::subsystem_builders
