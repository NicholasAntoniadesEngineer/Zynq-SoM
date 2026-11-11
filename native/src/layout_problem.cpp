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
