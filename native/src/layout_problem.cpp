#include "schgen/layout_problem.hpp"

namespace schgen::layout {

void validate(const Problem& problem, const Placement& placement) {
    if (placement.size() != problem.parts.size())
        throw LayoutError("layout: placement size differs from the part count");
    if (problem.board.width <= 0 || problem.board.height <= 0)
        throw LayoutError("layout: board has no area");
    for (const auto& part : problem.parts) {
        if (part.footprint >= problem.footprints.size())
            throw LayoutError("layout: part " + part.reference + " names no footprint");
        const Footprint& footprint = problem.footprints[part.footprint];
        if (part.pad_nets.size() != footprint.top.pads.size() ||
            part.pad_nets.size() != footprint.bottom.pads.size())
            throw LayoutError("layout: pad count of " + part.reference + " differs between variants");
        for (const int net : part.pad_nets)
            if (net != no_net && (net < 0 || static_cast<std::size_t>(net) >= problem.nets.size()))
                throw LayoutError("layout: part " + part.reference + " names no net");
    }
    for (const auto& net : problem.nets)
        for (const auto& pin : net.pins)
            if (pin.part >= problem.parts.size() ||
                pin.pad >= problem.parts[pin.part].pad_nets.size())
                throw LayoutError("layout: net " + net.name + " names no pad");
}

}
