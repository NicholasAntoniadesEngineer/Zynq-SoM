#include "schgen/roles.hpp"

#include <algorithm>
#include <stdexcept>

namespace schgen::rules {

const std::vector<RoleRule>& role_catalogue() {
    namespace reach = layout::constants;
    static const std::vector<RoleRule> catalogue = [] {
        std::vector<RoleRule> rows;
        const auto add = [&](std::string_view name, const NamedConstant& distance) -> RoleRule& {
            rows.push_back({name, &distance});
            return rows.back();
        };
        add("bypass", reach::bypass_reach).loop_capacitor = true;
        rows.back().bypasses_pin = true;
        add("reservoir", reach::reservoir_reach).loop_capacitor = true;
        add("pull", reach::pull_reach);
        add("series", reach::series_reach).terminates_line = true;
        add("terminate", reach::terminate_reach).terminates_line = true;
        add("limit", reach::limit_reach);
        add("filter", reach::filter_reach);
        add("feedback", reach::feedback_reach).loop_member = true;
        rows.back().field_sensitive = true;
        add("switching", reach::switching_reach).loop_member = true;
        rows.back().marks_regulator = true;
        add("timing", reach::timing_reach).owner_face = true;
        rows.back().field_sensitive = true;
        rows.back().field_reported = true;
        add("protect", reach::protect_reach).protects_connector = true;
        add("sense", reach::sense_reach).senses = true;
        rows.back().field_sensitive = true;
        rows.back().field_reported = true;
        add("indicate", reach::indicate_reach);
        add("set", reach::set_reach);
        return rows;
    }();
    return catalogue;
}

const RoleRule& role_rule(std::string_view name) {
    const auto& catalogue = role_catalogue();
    const auto found = std::find_if(catalogue.begin(), catalogue.end(),
                                    [&](const RoleRule& row) { return row.name == name; });
    if (found == catalogue.end()) throw std::runtime_error("role '" + std::string(name) + "' is not in the role catalogue");
    return *found;
}

std::vector<std::string_view> roles_with(bool RoleRule::*trait) {
    std::vector<std::string_view> names;
    for (const RoleRule& row : role_catalogue())
        if (row.*trait) names.push_back(row.name);
    return names;
}

bool keeps_owner_face(const RoleRule& role, bool owner_is_regulator, bool owner_is_loop_inductor) {
    if (role.owner_face) return true;
    if (role.loop_member) return owner_is_regulator;
    return role.loop_capacitor && (owner_is_regulator || owner_is_loop_inductor);
}

FaceDemand face_demand(const RoleRule& role, bool owner_is_regulator, bool owner_is_loop_inductor,
                       bool owner_is_module_connector) {
    if (keeps_owner_face(role, owner_is_regulator, owner_is_loop_inductor) || role.protects_connector) return {true, false};
    if (role.bypasses_pin || (role.terminates_line && owner_is_module_connector)) return {true, true};
    return {};
}

UnderRegion under_region(bool owner_is_module_connector) {
    return owner_is_module_connector ? UnderRegion::module_body : UnderRegion::owner_courtyard;
}

}
