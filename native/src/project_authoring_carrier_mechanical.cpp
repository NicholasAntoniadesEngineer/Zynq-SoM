#include "schgen/subsystem_authoring.hpp"

namespace schgen::project_builders {
// Migrated construction operations from carrier/subsystems/mechanical/mechanical.py.
CircuitSheetIr carrier_mechanical(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("mechanical", "Mechanical: M3 mounts + chassis-GND bond (fiducials are PCB-only, emitted by the placer)", context);
    c.net("CHASSIS_GND", {}, std::nullopt);
    c.mounting_hole("CHASSIS_GND", std::nullopt);
    c.mounting_hole("CHASSIS_GND", std::nullopt);
    c.mounting_hole("CHASSIS_GND", std::nullopt);
    c.mounting_hole("CHASSIS_GND", std::nullopt);
    return meta.finish(c);
}
} // namespace schgen::project_builders
