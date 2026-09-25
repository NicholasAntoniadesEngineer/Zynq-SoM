#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/board_qwiic/board_qwiic.py.
CircuitSheetIr carrier_board_qwiic(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("board_qwiic", "QWIIC / STEMMA-QT expansion connector + USBLC6 ESD array", context);
    {
        AuthoringPartSelection p;
        p.ref = "J1";
        c.use_part("ZX-SH1.0-4PWT", p);
    }
    c.net("GND", {"J1.1"}, std::nullopt);
    c.net("+3V3_AUX", {"J1.2"}, std::nullopt);
    c.net("GND", {"J1.5", "J1.6"}, std::nullopt);
    {
        AuthoringPartSelection p;
        p.ref = "U1";
        c.use_part("USBLC6-2SC6", p);
    }
    c.net("QWIIC_SDA", {"J1.3", "U1.1"}, std::nullopt);
    c.net("QWIIC_SCL", {"J1.4", "U1.3"}, std::nullopt);
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "sda";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_aux / board_services (the isolated AUX I2C bus)";
        c.port("AUX_I2C_SDA", {"U1.6"}, t, true);
    }
    {
        AuthoringPort t;
        t.kind = "i2c";
        t.role = "scl";
        t.bus = "AUX_I2C";
        t.speed_hz = 400000;
        t.expect = "board_aux / board_services (the isolated AUX I2C bus)";
        c.port("AUX_I2C_SCL", {"U1.4"}, t, true);
    }
    c.net("+3V3", {"U1.5"}, std::nullopt);
    c.net("GND", {"U1.2"}, std::nullopt);
    c.draws("+3V3_AUX", 0.2, "QWIIC external module budget (200 mA)");
    return meta.finish(c);
}
} // namespace schgen::project_builders
