#include "schgen/placement_integrity.hpp"

#include <algorithm>
#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "termination-distance-report", "high_speed",
    "The distance from every termination and series part to the pin it serves is reported, farthest first, and flagged when it exceeds the reach of its role, unless the part serves a module connector and sits on the rear under the module body.",
    "A termination away from the end of its line, or a series element away from its driver, leaves a stub that reflects.",
    "AMD/Xilinx UG471, 7 Series SelectIO Resources, https://docs.amd.com/go/en-US/ug471_7Series_SelectIO; "
    "Altera AN 958, Board Design Guidelines, https://docs.altera.com/r/docs/683073/current/an-958-board-design-guidelines",
    "primary vendor document", Enforcement::measured, Stage::layout};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(roles_with(&RoleRule::terminates_line)), {}};
    std::vector<std::pair<double, const Service*>> rows;
    for (const Service* service : context.serving(roles_with(&RoleRule::terminates_line)))
        rows.emplace_back(*context.pad_gap(service->owner, service->pads, service->part), service);
    std::stable_sort(rows.begin(), rows.end(), [](const auto& first, const auto& second) { return first.first > second.first; });
    for (const auto& [gap, service] : rows) {
        ++result.checked;
        const double reach = layout::role_reach(service->role);
        std::ostringstream row;
        row << "is " << gap << " mm from " << service->pin << "; the reach of a " << service->role << " part is " << reach
            << " mm";
        result.measurements.push_back(context.label(service->part) + " " + row.str());
        if (gap <= reach + constants::judging_resolution.value) continue;
        const bool beneath = context.module_connector(service->owner) && context.model().som_keepout &&
                             context.rear(service->part) &&
                             RuleContext::overlap(context.body(service->part), *context.model().som_keepout) >
                                 constants::judging_resolution.value;
        if (beneath) {
            result.measurements.push_back(context.label(service->part) +
                                          " is under the module body, the nearest place the module's via field leaves");
            continue;
        }
        result.findings.push_back({context.label(service->part), row.str()});
    }
    return result;
}

}

extern const RuleEntry termination_distance_report{rule, check};

}
