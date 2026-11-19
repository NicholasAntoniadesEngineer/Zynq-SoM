#include "schgen/layout_geometry.hpp"
#include "schgen/placement_integrity.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "module-clearance", "mechanical",
    "Every top-face part keeps its courtyard and pads at least the module clearance away from the module body, and a part taller than the module's underside keeps the larger tall-part clearance.",
    "The module outline and its mating tolerance need room, and fingers or a tool need room to seat and lift it.",
    "owner decision, 2026-11-19 (parts were touching the module outline; tall parts stood 1 mm from it)", "owner decision", Enforcement::gate, Stage::layout};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, {}, {}};
    if (!context.model().som_keepout) return result;
    const Box4& module = *context.model().som_keepout;
    for (std::size_t part = 0; part < context.parts().size(); ++part) {
        const auto& instance = context.parts()[part];
        if (context.rear(part) || context.module_connector(part) || module_clearance_exempt(instance)) continue;
        if (!context.placed(part)) {
            result.findings.push_back({context.label(part), "has no footprint, its module clearance cannot be judged"});
            continue;
        }
        if (!instance.height) {
            result.findings.push_back({context.label(part), "has no height, its module clearance cannot be judged"});
            continue;
        }
        ++result.checked;
        const double required = layout::module_gap_needed(
            instance.height->mm, layout::constants::module_stack_height.value, layout::constants::module_clearance.value,
            layout::constants::tall_module_clearance.value);
        const Box4 body = context.body(part);
        const double apart = std::sqrt(layout::squared_box_gap(body, module));
        if (apart >= required - constants::judging_resolution.value) continue;
        std::ostringstream detail;
        detail << "is " << apart << " mm from the module body; " << required << " mm is required";
        result.findings.push_back({context.label(part), detail.str()});
    }
    return result;
}

}

extern const RuleEntry module_clearance{rule, check};

}
