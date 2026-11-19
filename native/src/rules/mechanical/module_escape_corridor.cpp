#include "schgen/placement_integrity.hpp"

#include "schgen/pcb_escape.hpp"

#include <algorithm>
#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "module-escape-corridor", "mechanical",
    "No rear part and no drilled part sits inside the escape corridor of a module connector.",
    "The corridor is where the module connector's pins break out on the rear copper; a part or a drill there blocks the breakout.",
    "owner decision, 2026-11-11 (module escape corridors reserved against rear and through-hole parts)",
    "owner decision", Enforcement::gate, Stage::placement};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, {}, {}};
    const auto& parts = context.parts();
    std::vector<std::pair<std::string, Box4>> corridors;
    for (std::size_t part = 0; part < parts.size(); ++part) {
        if (!context.module_connector(part)) continue;
        if (!context.placed(part)) {
            result.findings.push_back({parts[part].ref, "module connector has no footprint, its escape corridor is unknown"});
            continue;
        }
        corridors.emplace_back(parts[part].ref, pcb_escape_corridor_board(*parts[part].mod, parts[part].x, parts[part].y,
                                                                         parts[part].rotation));
    }
    for (std::size_t part = 0; part < parts.size(); ++part) {
        if (context.module_connector(part)) continue;
        if (!context.placed(part)) {
            result.findings.push_back({parts[part].ref, "has no footprint, corridor clearance cannot be judged"});
            continue;
        }
        const bool through = drilled_part(parts[part]);
        if (!context.rear(part) && !through) continue;
        const Box4 body = context.body(part);
        for (const auto& [owner, corridor] : corridors) {
            ++result.checked;
            const double depth =
                std::min({body.x1 - corridor.x0, corridor.x1 - body.x0, body.y1 - corridor.y0, corridor.y1 - body.y0});
            if (depth <= constants::judging_resolution.value) continue;
            std::ostringstream detail;
            detail << (through ? "through-hole" : "rear") << " part reaches " << depth
                   << " mm into the escape corridor of " << owner;
            result.findings.push_back({context.label(part), detail.str()});
        }
    }
    return result;
}

}

extern const RuleEntry module_escape_corridor{rule, check};

}
