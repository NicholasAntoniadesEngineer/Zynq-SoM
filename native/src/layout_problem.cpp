#include "schgen/layout_problem.hpp"

#include "schgen/pcb_emit.hpp"

#include <limits>
#include <cmath>
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
    case Tie::authored: return "authored";
    case Tie::released: return "released";
    case Tie::signal: return "signal";
    case Tie::rail: return "rail";
    case Tie::shared: return "shared";
    case Tie::bridge: return "bridge";
    case Tie::unattached: return "unattached";
    case Tie::none: break;
    }
    return "none";
}

Nm squared_pad_gap(const Problem& problem, const PadGap& rule, const Pose& anchor, const Pose& member) {
    const auto boxes = [&](std::size_t part, const Pose& pose, const std::vector<std::size_t>& names) {
        const Variant& variant = problem.footprints[problem.parts[part].footprint].on(pose.face);
        std::vector<Box> out;
        if (names.empty())
            for (const auto& box : variant.name_boxes) out.push_back(placed(box, pose.at, pose.turn));
        else
            for (const std::size_t name : names) out.push_back(placed(variant.name_boxes[name], pose.at, pose.turn));
        return out;
    };
    Nm best = std::numeric_limits<Nm>::max();
    for (const auto& first : boxes(rule.anchor, anchor, rule.anchor_names))
        for (const auto& second : boxes(rule.member, member, {})) best = std::min(best, squared_gap(first, second));
    return best;
}

Nm pad_gap_length(const Problem& problem, const PadGap& rule, const Placement& placement) {
    const Nm squared_length = squared_pad_gap(problem, rule, placement[rule.anchor], placement[rule.member]);
    if (squared_length == std::numeric_limits<Nm>::max()) return squared_length;
    return static_cast<Nm>(std::ceil(std::sqrt(static_cast<double>(squared_length)))) + 1;
}

void derive_ownership(Problem& problem, const Placement& placement, const HoldPolicy& policy, const Intent& intent) {
    const std::size_t count = problem.parts.size();
    problem.ownership.assign(count, {});
    problem.constraints.soft_gaps.clear();
    auto& gaps = problem.constraints.pad_gaps;
    gaps.erase(std::remove_if(gaps.begin(), gaps.end(), [](const PadGap& rule) { return rule.derived; }), gaps.end());
    std::vector<std::optional<std::size_t>> contracted(count);
    for (const auto& rule : gaps)
        if (rule.sense == Sense::at_most && !contracted[rule.member]) contracted[rule.member] = rule.anchor;
    for (const auto& rule : problem.constraints.nearest_gaps)
        for (const std::size_t member : rule.members)
            if (!contracted[member]) contracted[member] = rule.anchor;
    std::vector<const Claim*> claimed(count, nullptr);
    for (const auto& claim : intent.claims) {
        if (claim.part >= count || claim.owner >= count) throw LayoutError("layout: an ownership claim names a part outside the problem");
        if (claimed[claim.part]) throw LayoutError("layout: " + problem.parts[claim.part].reference + " is claimed twice");
        claimed[claim.part] = &claim;
    }
    std::vector<bool> released(count, false);
    for (const std::size_t part : intent.released) {
        if (part >= count) throw LayoutError("layout: a released part lies outside the problem");
        released[part] = true;
    }
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
    const auto shared_names = [&](std::size_t owner, int net) {
        const Footprint& footprint = problem.footprints[problem.parts[owner].footprint];
        std::vector<std::size_t> names;
        for (std::size_t pad = 0; pad < footprint.top.pads.size(); ++pad) {
            if (problem.parts[owner].pad_nets[pad] != net) continue;
            const auto name = std::find(footprint.top.names.begin(), footprint.top.names.end(), footprint.top.pads[pad].name);
            const auto slot = static_cast<std::size_t>(name - footprint.top.names.begin());
            if (std::find(names.begin(), names.end(), slot) == names.end()) names.push_back(slot);
        }
        return names;
    };
    std::vector<PadGap> holds;
    const auto own = [&](std::size_t part, std::size_t owner, std::vector<std::size_t> names, Nm reach,
                         bool same_face = false, bool or_under = false, bool first = false) {
        PadGap rule{owner, part, std::move(names), reach, Sense::at_most, "owner of " + problem.parts[part].reference,
                    true, false, reach, same_face, or_under, first};
        problem.constraints.soft_gaps.push_back(rule);
        rule.source = "hold of " + problem.parts[part].reference;
        rule.derived = true;
        rule.limit = std::max(reach, pad_gap_length(problem, rule, placement)) + policy.hold_slack;
        holds.push_back(std::move(rule));
    };
    for (std::size_t part = 0; part < count; ++part) {
        if (problem.parts[part].fixed || problem.parts[part].connector) continue;
        Ownership& entry = problem.ownership[part];
        if (claimed[part]) {
            entry = {Tie::authored, claimed[part]->owner};
            own(part, claimed[part]->owner, claimed[part]->names, claimed[part]->reach, claimed[part]->same_face,
                claimed[part]->or_under, claimed[part]->first);
            continue;
        }
        if (!small(part)) continue;
        if (contracted[part]) {
            entry = {Tie::contract, contracted[part]};
            continue;
        }
        if (released[part]) {
            entry.tie = Tie::released;
            continue;
        }
        const auto signal = peers(part, Category::signal, false);
        if (signal.size() == 1) {
            entry = {Tie::signal, signal.front().first};
            own(part, signal.front().first, shared_names(signal.front().first, signal.front().second), policy.owner_reach);
            continue;
        }
        if (signal.size() > 1) {
            entry.tie = Tie::bridge;
            for (const auto& [peer, net] : signal) {
                PadGap rule{peer, part, shared_names(peer, net), policy.owner_reach, Sense::at_most,
                            "tether of " + problem.parts[part].reference, false, true, policy.owner_reach};
                rule.limit = std::max(policy.owner_reach, pad_gap_length(problem, rule, placement)) + policy.tether_slack;
                holds.push_back(std::move(rule));
            }
            continue;
        }
        const auto rail = peers(part, Category::power, true);
        if (rail.empty()) {
            entry.tie = Tie::unattached;
            continue;
        }
        std::size_t nearest = 0;
        Nm best = std::numeric_limits<Nm>::max();
        for (std::size_t index = 0; index < rail.size(); ++index) {
            const PadGap probe{rail[index].first, part, shared_names(rail[index].first, rail[index].second),
                               policy.owner_reach, Sense::at_most, {}, true, true, policy.owner_reach};
            const Nm gap = pad_gap_length(problem, probe, placement);
            if (gap < best) {
                best = gap;
                nearest = index;
            }
        }
        entry = {rail.size() == 1 ? Tie::rail : Tie::shared, rail[nearest].first};
        own(part, rail[nearest].first, shared_names(rail[nearest].first, rail[nearest].second), policy.owner_reach);
    }
    gaps.insert(gaps.end(), holds.begin(), holds.end());
}
void tighten_holds(Problem& problem, const Placement& placement, const HoldPolicy& policy) {
    for (auto& rule : problem.constraints.pad_gaps) {
        if (!rule.derived || !rule.rigid) continue;
        rule.limit = std::min(rule.limit, std::max(rule.reach, pad_gap_length(problem, rule, placement)) + policy.hold_slack);
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

Box hull_at(const Problem& problem, const Placement& placement, const std::vector<std::size_t>& parts) {
    Box hull = gate_at(problem, parts.front(), placement[parts.front()]);
    for (const std::size_t part : parts) hull = united(hull, gate_at(problem, part, placement[part]));
    return hull;
}

Box pour_box(const PourRule& rule, const Pose& owner, const Board& board) {
    const Box4 plane = ground_plane_box(to_mm(board.origin.x), to_mm(board.origin.y), to_mm(board.width),
                                        to_mm(board.height), rule.edge_back);
    const Box4 extent = thermal_pour_extent({rule.local[0], rule.local[1], rule.local[2], rule.local[3]}, rule.mirror,
                                            degrees_of(owner.turn), to_mm(owner.at.x), to_mm(owner.at.y), plane);
    return {nearest_nm(extent.x0), nearest_nm(extent.y0), nearest_nm(extent.x1), nearest_nm(extent.y1)};
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
