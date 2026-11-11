#include "schgen/layout_problem.hpp"

#include <algorithm>

namespace schgen::layout {

void index_names(Variant& variant) {
    variant.names.clear();
    variant.name_boxes.clear();
    for (const auto& pad : variant.pads) {
        std::size_t slot = 0;
        while (slot < variant.names.size() && variant.names[slot] != pad.name) ++slot;
        if (slot == variant.names.size()) {
            variant.names.push_back(pad.name);
            variant.name_boxes.push_back(pad.box);
        } else {
            variant.name_boxes[slot] = united(variant.name_boxes[slot], pad.box);
        }
    }
}

const char* tie_name(Tie tie) {
    switch (tie) {
    case Tie::contract: return "contract";
    case Tie::signal: return "signal";
    case Tie::rail: return "rail";
    case Tie::shared: return "shared";
    case Tie::bridge: return "bridge";
    case Tie::unattached: return "unattached";
    case Tie::none: break;
    }
    return "none";
}

void derive_ownership(Problem& problem, Nm owner_reach) {
    const std::size_t count = problem.parts.size();
    problem.ownership.assign(count, {});
    problem.constraints.soft_gaps.clear();
    std::vector<std::optional<std::size_t>> contracted(count);
    for (const auto& rule : problem.constraints.pad_gaps)
        if (rule.sense == Sense::at_most && !contracted[rule.member]) contracted[rule.member] = rule.anchor;
    for (const auto& rule : problem.constraints.nearest_gaps)
        for (const std::size_t member : rule.members)
            if (!contracted[member]) contracted[member] = rule.anchor;
    const auto small = [&](std::size_t part) { return problem.parts[part].fanout_pins <= 2; };
    const auto peers = [&](std::size_t part, Category category, bool same_group) {
        std::vector<std::pair<std::size_t, int>> found;
        for (const int net : problem.parts[part].pad_nets) {
            if (net == no_net || problem.nets[static_cast<std::size_t>(net)].category != category) continue;
            for (const auto& pin : problem.nets[static_cast<std::size_t>(net)].pins) {
                if (pin.part == part || small(pin.part)) continue;
                if (same_group && problem.parts[pin.part].group != problem.parts[part].group) continue;
                if (std::none_of(found.begin(), found.end(), [&](const auto& item) { return item.first == pin.part; }))
                    found.emplace_back(pin.part, net);
            }
        }
        return found;
    };
    const auto soften = [&](std::size_t part, std::size_t owner, int net) {
        const Footprint& footprint = problem.footprints[problem.parts[owner].footprint];
        std::vector<std::size_t> names;
        for (std::size_t pad = 0; pad < footprint.top.pads.size(); ++pad) {
            if (problem.parts[owner].pad_nets[pad] != net) continue;
            const auto name = std::find(footprint.top.names.begin(), footprint.top.names.end(), footprint.top.pads[pad].name);
            const auto slot = static_cast<std::size_t>(name - footprint.top.names.begin());
            if (std::find(names.begin(), names.end(), slot) == names.end()) names.push_back(slot);
        }
        problem.constraints.soft_gaps.push_back({owner, part, names, owner_reach, Sense::at_most,
                                                 std::string("owner of ") + problem.parts[part].reference});
    };
    for (std::size_t part = 0; part < count; ++part) {
        if (!small(part) || problem.parts[part].fixed || problem.parts[part].connector) continue;
        Ownership& entry = problem.ownership[part];
        if (contracted[part]) {
            entry = {Tie::contract, contracted[part]};
            continue;
        }
        const auto signal = peers(part, Category::signal, false);
        if (signal.size() == 1) {
            entry = {Tie::signal, signal.front().first};
            soften(part, signal.front().first, signal.front().second);
            continue;
        }
        if (signal.size() > 1) {
            entry.tie = Tie::bridge;
            continue;
        }
        const auto rail = peers(part, Category::power, true);
        if (rail.size() == 1) {
            entry = {Tie::rail, rail.front().first};
            soften(part, rail.front().first, rail.front().second);
        } else {
            entry.tie = rail.empty() ? Tie::unattached : Tie::shared;
        }
    }
}

std::optional<bool> mirrors_across_x(const Footprint& footprint) {
    const auto mirrored = [](Box box, bool across_x) {
        return across_x ? Box{-box.x1, box.y0, -box.x0, box.y1} : Box{box.x0, -box.y1, box.x1, -box.y0};
    };
    for (const bool across_x : {true, false}) {
        bool same = mirrored(footprint.top.gate_box, across_x) == footprint.bottom.gate_box &&
                    footprint.top.pads.size() == footprint.bottom.pads.size();
        for (std::size_t pad = 0; same && pad < footprint.top.pads.size(); ++pad)
            same = mirrored(footprint.top.pads[pad].box, across_x) == footprint.bottom.pads[pad].box;
        if (same) return across_x;
    }
    return std::nullopt;
}

Box gate_at(const Problem& problem, std::size_t part, const Pose& pose) {
    return placed(problem.footprints[problem.parts[part].footprint].on(pose.face).gate_box, pose.at, pose.turn);
}

Point corner_site(const Board& board, const CornerRule& rule) {
    const auto snapped = [&](Nm value) {
        if (rule.grid <= 0) return value;
        const Nm below = value / rule.grid - (value % rule.grid < 0 ? 1 : 0);
        const Nm rest = value - below * rule.grid;
        const bool up = 2 * rest > rule.grid || (2 * rest == rule.grid && below % 2 != 0);
        return (below + (up ? 1 : 0)) * rule.grid;
    };
    return {snapped((rule.east ? board.origin.x + board.width : board.origin.x) + rule.inset.x),
            snapped((rule.south ? board.origin.y + board.height : board.origin.y) + rule.inset.y)};
}

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
        if (part.corner && !part.fixed)
            throw LayoutError("layout: corner part " + part.reference + " is not fixed");
    }
    for (const auto& reserve : problem.reserves)
        for (const std::size_t member : reserve.members)
            if (member >= problem.parts.size())
                throw LayoutError("layout: reserved field names an unknown part: " + reserve.source);
    const auto part_known = [&](std::size_t part) { return part < problem.parts.size(); };
    const auto names_known = [&](std::size_t part, const std::vector<std::size_t>& names) {
        const auto& known = problem.footprints[problem.parts[part].footprint].top.names;
        for (const std::size_t name : names)
            if (name >= known.size()) return false;
        return true;
    };
    for (const auto& footprint : problem.footprints)
        if (footprint.top.names != footprint.bottom.names)
            throw LayoutError("layout: pad names of " + footprint.key + " differ between variants");
    for (const auto& rule : problem.constraints.pad_gaps)
        if (!part_known(rule.anchor) || !part_known(rule.member) || !names_known(rule.anchor, rule.anchor_names))
            throw LayoutError("layout: pad-gap rule names an unknown part or pad: " + rule.source);
    for (const auto& rule : problem.constraints.nearest_gaps) {
        if (!part_known(rule.anchor) || rule.members.empty() || !names_known(rule.anchor, rule.anchor_names))
            throw LayoutError("layout: nearest-gap rule names an unknown part or pad: " + rule.source);
        for (const std::size_t member : rule.members)
            if (!part_known(member)) throw LayoutError("layout: nearest-gap rule names an unknown member: " + rule.source);
    }
    for (const auto& rule : problem.constraints.face_pairs)
        if (!part_known(rule.first) || !part_known(rule.second))
            throw LayoutError("layout: face rule names an unknown part: " + rule.source);
    for (const auto& net : problem.nets)
        for (const auto& pin : net.pins)
            if (pin.part >= problem.parts.size() ||
                pin.pad >= problem.parts[pin.part].pad_nets.size())
                throw LayoutError("layout: net " + net.name + " names no pad");
}

}
