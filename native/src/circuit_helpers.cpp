#include "schgen/circuit_helpers.hpp"
#include "authoring_values.hpp"

namespace schgen {
void validate_mounting_hole_net(const CircuitSheetIr& c, const std::string& name) {
    const auto net = std::find_if(c.nets.begin(), c.nets.end(), [&](const auto& n) { return n.name == name; });
    const auto prefix = "mounting_hole(" + authoring_values::repr(name) + "): ";
    if (net == c.nets.end()) throw CircuitAuthoringError(prefix + "not a declared net");
    if (net->net_class != "ground") throw CircuitAuthoringError(prefix +
        "only GROUND nets — a mounting hole is a chassis/earth bond, never a signal/rail (" + net->net_class + ")");
}
CircuitPartIr add_mounting_hole(CircuitSheetIr& c, const std::string& name, const std::optional<std::string>& ref) {
    validate_mounting_hole_net(c, name);
    auto has = [&](const std::string& r) { return std::any_of(c.parts.begin(), c.parts.end(), [&](const auto& p) { return p.ref == r; }); };
    std::string r = ref.value_or("H1");
    if (!ref) for (std::size_t n = 1; has(r);) r = "H" + std::to_string(++n);
    if (has(r)) throw CircuitAuthoringError("duplicate reference " + authoring_values::repr(r));
    CircuitPartIr part{r, "Mechanical:MountingHole_Pad", "MountingHole_M3",
        "MountingHole:MountingHole_3.2mm_M3_Pad", {{"BOM", "exclude"}}, {}, {}};
    c.parts.push_back(part);
    for (auto& n : c.nets) if (n.name == name) { n.pins.push_back({r, "1"}); break; }
    return part;
}
} // namespace schgen
