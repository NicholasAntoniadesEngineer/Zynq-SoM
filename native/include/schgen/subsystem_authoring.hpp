#pragma once
#include "schgen/authoring.hpp"

namespace schgen {
struct SubsystemDefinition {
    std::string name;
    std::vector<std::string> interface;
    std::function<CircuitSheetIr(const SubsystemMeta&, const AuthoringContext&)> circuit;
};
// Native, parameterized implementations of all reusable library circuits.
// Building always executes the authoring operations and live catalog lookups.
// There is no dependency on a saved circuit.json or Python source at runtime.
const std::vector<SubsystemDefinition>& subsystem_definitions();
const SubsystemDefinition& subsystem_definition(const std::string& name);
CircuitSheetIr author_subsystem(const std::string& name, const SubsystemMeta& meta = SubsystemMeta{},
                               const AuthoringContext& context = {});
} // namespace schgen
