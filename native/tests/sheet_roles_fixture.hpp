#pragma once

#include "schgen/project.hpp"
#include "schgen/sheet_roles.hpp"

#include <string>
#include <vector>

inline schgen::SheetRoles explicit_sheet_roles(const std::vector<std::string>& names) {
    schgen::SheetRoles roles;
    for (const std::string& name : names) {
        schgen::SheetRole role;
        if (name.rfind("som_j", 0) == 0) role.module_connector = "J" + name.substr(5);
        if (name == "som_decoupling") role.region = schgen::SheetRegion::under_module;
        roles.emplace(name, role);
    }
    return roles;
}

inline schgen::SheetRoles explicit_sheet_roles(const std::vector<schgen::CircuitSheetIr>& sheets) {
    std::vector<std::string> names;
    for (const schgen::CircuitSheetIr& sheet : sheets) names.push_back(sheet.name);
    return explicit_sheet_roles(names);
}

inline schgen::SheetRoles explicit_sheet_roles(const std::vector<schgen::ProjectCircuit>& sheets) {
    std::vector<std::string> names;
    for (const schgen::ProjectCircuit& sheet : sheets) names.push_back(sheet.circuit.name);
    return explicit_sheet_roles(names);
}
