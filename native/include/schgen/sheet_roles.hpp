#pragma once

#include "schgen/authoring.hpp"
#include "schgen/board_definition.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/som_interface.hpp"
#include "schgen/subsystem_data.hpp"

#include <map>
#include <string>
#include <vector>

namespace schgen {

struct SheetRole {
    std::string module_connector;
    SheetRegion region = SheetRegion::board;
};

using SheetRoles = std::map<std::string, SheetRole>;

SheetRoles sheet_roles(const BoardDefinition& board, const AuthoringContext& context, const SomInterface& module,
                       const std::vector<CircuitSheetIr>& circuits, const PartFacts& facts);
const SheetRole& sheet_role(const SheetRoles& roles, const std::string& sheet);

}
