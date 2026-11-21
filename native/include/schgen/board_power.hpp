#pragma once

#include "schgen/power_checks.hpp"
#include "schgen/sheet_roles.hpp"

#include <map>
#include <string>
#include <vector>

namespace schgen {

PowerPolicy explicit_power_policy(const BoardPower& power, const ModuleDefinition& module);
PowerPolicy board_power_policy(const BoardPower& power, const ModuleDefinition& module,
    const std::map<std::string, std::string>& rebound_module_rails, const std::vector<std::string>& module_sheets,
    const std::vector<ProjectCircuit>& sheets, const PartFacts& facts);
PowerPolicy load_board_power_policy(const ProjectPaths& paths, const std::vector<ProjectCircuit>& sheets,
    const SheetRoles& roles);

}
