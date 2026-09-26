#pragma once

#include "schgen/design_rules.hpp"
#include "schgen/subsystem_authoring.hpp"

namespace schgen {
struct SubsystemLocalResult {
    std::vector<std::string> errors;
    DesignRuleResult design_rules;
    bool ok() const;
    std::string summary() const;
};

// Local electrical acceptance, not board-level link/ERC/power-tree checks.
// Checks live factory output, exact abstract interface, all symbol/pin
// resolution, nonempty implementation, decap/EP/strap, and both positive and
// unknown-name metadata binds. Resolver failures cannot silently skip checks.
// I2C/reset board-context findings retain their advisory policy here.
SubsystemLocalResult check_subsystem_local(const SubsystemDefinition& definition,
    const AuthoringContext& context, const DesignRuleSymbolResolver& resolve);
} // namespace schgen
