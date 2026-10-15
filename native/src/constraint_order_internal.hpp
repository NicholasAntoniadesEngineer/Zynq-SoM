#pragma once
#include "schgen/floorplan.hpp"
#include <algorithm>
#include <map>
#include <vector>

namespace schgen::floorplan_detail {
inline std::map<std::string, std::size_t> hard_constraint_incidence(const FloorplanTermIndex& index) {
    std::map<std::string, std::size_t> counts;
    for (const auto& term : index.hard) if (term.enforced) {
        ++counts[term.subject];
        const auto target = term.target();
        if (target != term.subject) ++counts[target];
    }
    return counts;
}
inline void sort_constraint_first(std::vector<FloorplanBlock*>& blocks,
                                  const FloorplanTermIndex& index,
                                  const std::map<std::string, FloorplanPoint>& boxes) {
    const auto counts = hard_constraint_incidence(index);
    const auto count = [&](const std::string& name) {
        const auto found = counts.find(name);
        return found == counts.end() ? std::size_t{0} : found->second;
    };
    std::stable_sort(blocks.begin(), blocks.end(), [&](const auto* a, const auto* b) {
        if (count(a->name) != count(b->name)) return count(a->name) > count(b->name);
        const auto aw = boxes.at(a->name), bw = boxes.at(b->name);
        return aw.first * aw.second > bw.first * bw.second;
    });
}
} // namespace schgen::floorplan_detail
