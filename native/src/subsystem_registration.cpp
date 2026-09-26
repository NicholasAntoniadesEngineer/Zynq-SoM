#include "schgen/subsystem_registration.hpp"

#include <set>
#include <utility>

#ifdef SCHGEN_CONFIGURED_SUBSYSTEMS
#include "schgen_configured_subsystems.hpp"
#endif

namespace schgen {
std::vector<SubsystemDefinition> merge_subsystem_definitions(
    std::vector<SubsystemDefinition> builtins,
    const std::vector<SubsystemDefinition>& extensions) {
    std::set<std::string> names;
    for (const auto& entry : builtins) {
        if (!names.insert(entry.name).second)
            throw CircuitAuthoringError("duplicate subsystem registration: " + entry.name);
    }
    for (const auto& entry : extensions) {
        if (entry.name.empty() || !entry.circuit || entry.interface.empty())
            throw CircuitAuthoringError("incomplete subsystem registration: " + entry.name);
        if (!names.insert(entry.name).second)
            throw CircuitAuthoringError("duplicate subsystem registration: " + entry.name);
        std::set<std::string> interface;
        for (const auto& port : entry.interface) {
            if (port.empty() || !interface.insert(port).second)
                throw CircuitAuthoringError("invalid subsystem interface: " + entry.name);
        }
        builtins.push_back(entry);
    }
    return builtins;
}

std::vector<SubsystemDefinition> append_configured_subsystem_definitions(
    std::vector<SubsystemDefinition> builtins) {
#ifdef SCHGEN_CONFIGURED_SUBSYSTEMS
    return merge_subsystem_definitions(std::move(builtins), configured_subsystem_packages());
#else
    return merge_subsystem_definitions(std::move(builtins), {});
#endif
}
} // namespace schgen
