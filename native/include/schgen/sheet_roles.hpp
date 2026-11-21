#pragma once

#include "schgen/authoring.hpp"
#include "schgen/board_definition.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"
#include "schgen/som_interface.hpp"
#include "schgen/subsystem_data.hpp"

#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace schgen {

struct SheetRole {
    std::string module_connector;
    SheetRegion region = SheetRegion::board;
    std::optional<std::string> silk_label, escape_basis;
    std::optional<double> far_guard_mm;
    bool escape_escalates = false, reserves_edge = false;
    SubsystemChecks checks;
};

using SheetRoles = std::map<std::string, SheetRole>;

SheetRoles sheet_roles(const BoardDefinition& board, const AuthoringContext& context, const SomInterface& module,
                       const std::vector<CircuitSheetIr>& circuits, const PartFacts& facts);
const SheetRole& sheet_role(const SheetRoles& roles, const std::string& sheet);
bool module_connector_sheet(const SheetRoles& roles, const std::string& sheet);
std::map<std::string, std::string> sheet_module_connectors(const SheetRoles& roles);
bool under_module_sheet(const SheetRoles& roles, const std::string& sheet);
std::map<std::string, std::string> module_sheets_by_connector(const SheetRoles& roles);
std::vector<std::pair<std::string, double>> sheet_far_guards(const SheetRoles& roles);
std::set<std::string> sheets_reserving_edge(const SheetRoles& roles);
SheetRoles load_sheet_roles(const ProjectPaths& paths, const std::vector<ProjectCircuit>& circuits);

}
