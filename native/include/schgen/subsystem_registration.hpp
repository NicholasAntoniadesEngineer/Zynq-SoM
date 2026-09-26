#pragma once

#include "schgen/subsystem_authoring.hpp"

namespace schgen {
// Immutable, explicit registration; no static constructors, dlopen, filesystem
// discovery, interpreter, or reference IR. Duplicate names never shadow a
// built-in. Invalid/missing live factories and interfaces fail closed.
std::vector<SubsystemDefinition> merge_subsystem_definitions(
    std::vector<SubsystemDefinition> builtins,
    const std::vector<SubsystemDefinition>& extensions);

// Called once by subsystem_definitions() around its built-in initializer.
// SubsystemPackages.cmake supplies the configured header only when packages
// were explicitly selected. The default build returns the unchanged builtins.
std::vector<SubsystemDefinition> append_configured_subsystem_definitions(
    std::vector<SubsystemDefinition> builtins);
} // namespace schgen
