#include "schgen/placement_integrity.hpp"

#include <algorithm>
#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "sense-distance-report", "sensing",
    "The distance from every sense part to the pin it serves is reported, farthest first; no source gives a limit, so none is judged.",
    "Sense lines carry small differential voltages; length adds series resistance and pickup, so the distances are worth seeing.",
    "TI INA226 datasheet, section 8.4 Layout, https://www.ti.com/lit/ds/symlink/ina226.pdf",
    "primary vendor document", Enforcement::measured, Stage::placement};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(roles_with(&RoleRule::senses)), {}};
    std::vector<std::pair<double, const Service*>> rows;
    for (const Service* service : context.serving(roles_with(&RoleRule::senses)))
        rows.emplace_back(*context.pad_gap(service->owner, service->pads, service->part), service);
    std::stable_sort(rows.begin(), rows.end(), [](const auto& first, const auto& second) { return first.first > second.first; });
    for (const auto& [gap, service] : rows) {
        ++result.checked;
        std::ostringstream row;
        row << context.label(service->part) << " is " << gap << " mm from " << service->pin << " ("
            << (context.rear(service->part) == context.rear(service->owner) ? "same face" : "opposite face") << ")";
        result.measurements.push_back(row.str());
    }
    return result;
}

}

extern const RuleEntry sense_distance_report{rule, check};

}
