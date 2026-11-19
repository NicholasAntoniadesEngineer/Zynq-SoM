#include "schgen/placement_integrity.hpp"

#include "schgen/seat.hpp"

#include <algorithm>
#include <sstream>

namespace schgen::rules {
namespace {

inline constexpr NamedConstant module_stack_height{"module_stack_height", 1.5, "mm", "physical",
    "board-to-board distance of the mated Hirose DF40C-100DS-0.4V(51) receptacle and DF40C-100DP-0.4V(51) header; "
    "Hirose DF40 Series catalog 2013.11, pages 3 and 4: a receptacle with no stacking-height code stacks at 1.5 mm"};

constexpr Rule rule{
    "tall-part-beside-module", "mechanical",
    "Every top-face part taller than the gap between the carrier and the underside of the mated module is reported "
    "with its height and its distance to the module body, nearest first; no margin is judged.",
    "A part taller than the gap under the module stands beside the module's edge, where it limits how far the module "
    "may overhang and the room for fingers or a tool; the owner decides the margin from the list.",
    "Hirose Electric, DF40 Series catalog (0.4 mm Pitch, 1.5 to 4.0 mm Height, Board-to-Board and Board-to-FPC "
    "Connectors), 2013.11, pages 3 and 4: a receptacle with no stacking-height code stacks at 1.5 mm and "
    "DF40C-100DS-0.4V(51) is listed under Receptacle (Stacking height 1.5 mm), "
    "https://www.hirose.com/product/series/DF40; part heights come from each part's 3D model or parts/part_facts.json",
    "primary vendor document", Enforcement::measured};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, {}, {}};
    if (!context.model().som_keepout) return result;
    const Box4& module = *context.model().som_keepout;
    const double gap = module_stack_height.value;
    struct Row {
        double distance = 0, height = 0;
        std::size_t part = 0;
    };
    std::vector<Row> rows;
    for (std::size_t part = 0; part < context.parts().size(); ++part) {
        const auto& instance = context.parts()[part];
        if (context.rear(part) || context.module_connector(part)) continue;
        if (!context.placed(part)) {
            result.findings.push_back({context.label(part), "has no footprint, its distance to the module cannot be measured"});
            continue;
        }
        if (!instance.height) {
            result.findings.push_back({context.label(part), "carries no height, so it cannot be compared with the module"});
            continue;
        }
        ++result.checked;
        if (instance.height->mm <= gap + constants::judging_resolution.value) continue;
        rows.push_back({box_gap(context.body(part), module), instance.height->mm, part});
    }
    std::stable_sort(rows.begin(), rows.end(), [](const Row& first, const Row& second) { return first.distance < second.distance; });
    for (const Row& row : rows) {
        std::ostringstream text;
        text << context.label(row.part) << " " << context.parts()[row.part].value << " is " << row.height << " mm tall, "
             << row.height - gap << " mm above the module underside at " << gap << " mm, and " << row.distance
             << " mm from the module body (" << part_class_name(context.part_class(row.part)) << "; "
             << context.parts()[row.part].height->source << ")";
        result.measurements.push_back(text.str());
    }
    return result;
}

}

extern const RuleEntry tall_part_beside_module{rule, check};

}
