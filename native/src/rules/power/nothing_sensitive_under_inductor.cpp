#include "schgen/placement_integrity.hpp"

#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "nothing-sensitive-under-inductor", "power",
    "No sense, timing or feedback part sits on the opposite face under the courtyard of a switching inductor.",
    "The inductor's stray magnetic field and its switching-node end couple into high-impedance and small-signal nodes directly beneath it.",
    "Analog Devices RAQ 164, Guidelines for Placing the Inductor on a Switch Mode Power Supply PCB, "
    "https://www.analog.com/en/resources/analog-dialogue/raqs/raq-issue-164.html; "
    "TI SNVA021 (AN-1149), Layout Guidelines for Switching Power Supplies, https://www.ti.com/lit/an/snva021c/snva021c.pdf",
    "primary vendor document", Enforcement::gate};

std::vector<std::string_view> sensitive_and_loop_roles() {
    std::vector<std::string_view> roles = roles_with(&RoleRule::marks_regulator);
    for (const std::string_view role : roles_with(&RoleRule::field_sensitive)) roles.push_back(role);
    return roles;
}

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(sensitive_and_loop_roles()), {}};
    for (const Regulator& regulator : context.regulators()) {
        for (const std::size_t inductor : regulator.inductors) {
            for (const Service* service : context.serving(roles_with(&RoleRule::field_sensitive))) {
                ++result.checked;
                const double depth = context.overlap(inductor, service->part);
                if (context.rear(service->part) == context.rear(inductor) || depth <= constants::judging_resolution.value)
                    continue;
                std::ostringstream detail;
                detail << "has the role " << service->role << " and sits on the " << context.face(service->part)
                       << " face under inductor " << context.label(inductor) << ", courtyards overlapping by " << depth << " mm";
                result.findings.push_back({context.label(service->part), detail.str()});
            }
            std::optional<std::size_t> nearest;
            for (const Service* service : context.serving(roles_with(&RoleRule::field_reported)))
                if (!nearest || context.centre_distance(inductor, service->part) < context.centre_distance(inductor, *nearest))
                    nearest = service->part;
            std::ostringstream row;
            row << "inductor " << context.label(inductor) << ": ";
            if (nearest)
                row << "nearest sense or timing part is " << context.label(*nearest) << ", " << context.centre_distance(inductor, *nearest)
                    << " mm centre to centre";
            else
                row << "the board has no sense or timing part";
            result.measurements.push_back(row.str());
        }
    }
    return result;
}

}

extern const RuleEntry nothing_sensitive_under_inductor{rule, check};

}
