// Test-only live implementation. This is never emitted by the scaffolder.
#include "widget.hpp"

namespace schgen::subsystem_packages {
CircuitSheetIr build_widget(const SubsystemMeta& meta, const AuthoringContext& context) {
    CircuitAuthor c("widget", "Local capacitor network", context);
    c.part("C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric");
    c.net("+VDD", {"C1.1"});
    c.net("GND", {"C1.2"});
    return meta.finish(c);
}
SubsystemDefinition define_widget() {
    auto interface = widget_rails;
    interface.insert(interface.end(), widget_ports.begin(), widget_ports.end());
    return {"widget", std::move(interface), build_widget};
}
} // namespace schgen::subsystem_packages
