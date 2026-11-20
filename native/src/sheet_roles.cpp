#include "schgen/sheet_roles.hpp"

#include <algorithm>
#include <set>
#include <stdexcept>

namespace schgen {
namespace {

[[noreturn]] void fail(const BoardDefinition& board, const std::string& sheet, const std::string& what) {
    throw std::runtime_error("board " + board.name + " sheet " + sheet + ": " + what);
}

void check_connector_sheet(const BoardDefinition& board, const BoardSheet& sheet, const CircuitSheetIr& circuit, const PartFacts& facts) {
    if (circuit.parts.size() != 1)
        fail(board, sheet.name, "a module connector sheet holds exactly one part, this one holds " + std::to_string(circuit.parts.size()));
    const CircuitPartIr& part = circuit.parts.front();
    if (part.ref != sheet.module_connector)
        fail(board, sheet.name, "its part is " + part.ref + " but board.json states module_connector " + sheet.module_connector);
    const PartClass part_class = symbol_class(facts, part.lib_id, part.ref + " (" + sheet.name + ")");
    if (part_class != PartClass::module_connector)
        fail(board, sheet.name, "its part " + part.ref + " has class " + std::string(part_class_name(part_class)) + ", not " +
                                    std::string(part_class_name(PartClass::module_connector)));
}

}

SheetRoles sheet_roles(const BoardDefinition& board, const AuthoringContext& context, const SomInterface& module,
                       const std::vector<CircuitSheetIr>& circuits, const PartFacts& facts) {
    SheetRoles roles;
    std::map<std::string, std::string> carried_by;
    for (const BoardSheet& sheet : board.sheets) {
        SheetRole role;
        if (sheet.from_module()) {
            const auto circuit = std::find_if(circuits.begin(), circuits.end(), [&](const CircuitSheetIr& item) { return item.name == sheet.name; });
            if (circuit == circuits.end()) fail(board, sheet.name, "the module connector sheet has no circuit");
            check_connector_sheet(board, sheet, *circuit, facts);
            const auto taken = carried_by.emplace(sheet.module_connector, sheet.name);
            if (!taken.second)
                fail(board, sheet.name, "module connector " + sheet.module_connector + " is also carried by sheet " + taken.first->second);
            role.module_connector = sheet.module_connector;
        } else {
            role.region = load_subsystem_facts(context.library, sheet.name).placement.region;
        }
        roles.emplace(sheet.name, std::move(role));
    }
    std::set<std::string> interface;
    for (const auto& [reference, connector] : module.connectors) interface.insert(reference);
    for (const auto& [reference, sheet] : carried_by)
        if (!interface.count(reference))
            fail(board, sheet, "module connector " + reference + " is not a connector of the module interface " + module.source);
    for (const std::string& reference : interface)
        if (!carried_by.count(reference))
            throw std::runtime_error("board " + board.name + ": no sheet carries module connector " + reference + " of the module interface " +
                                     module.source);
    return roles;
}

const SheetRole& sheet_role(const SheetRoles& roles, const std::string& sheet) {
    const auto found = roles.find(sheet);
    if (found == roles.end()) throw std::runtime_error("sheet roles: no role for sheet " + sheet);
    return found->second;
}

}
