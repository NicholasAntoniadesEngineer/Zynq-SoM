#include "schgen/layout_construct.hpp"

#include "schgen/layout_sink.hpp"

#include <algorithm>
#include <deque>
#include <functional>
#include <map>
#include <optional>

namespace schgen::layout {

namespace {

inline constexpr std::size_t cause_rows = 4;

struct Candidate {
    Pose pose;
    Nm gap = 0;
    std::size_t rank = 0;
};

const PadGap* owner_rule(const Problem& problem, std::size_t part) {
    for (const auto& rule : problem.constraints.soft_gaps)
        if (rule.member == part && problem.ownership[part].owner && rule.anchor == *problem.ownership[part].owner) return &rule;
    return nullptr;
}

bool eligible(const Kernel& kernel, std::size_t part) {
    const Problem& problem = kernel.problem();
    const Part& item = problem.parts[part];
    if (item.fixed || item.connector || item.module || item.corner || item.edge) return false;
    if (!kernel.movable_alone(part)) return false;
    if (problem.ownership.empty() || !problem.ownership[part].owner) return false;
    return owner_rule(problem, part) != nullptr;
}

std::size_t depth_of(const Problem& problem, const std::vector<char>& taken, std::size_t part) {
    std::size_t depth = 0;
    std::size_t at = part;
    while (problem.ownership[at].owner && taken[*problem.ownership[at].owner] && depth < problem.parts.size()) {
        at = *problem.ownership[at].owner;
        ++depth;
    }
    return depth;
}

}

ConstructReport construct_owned(Kernel& kernel, Nm pitch, Nm reach) {
    const Problem& problem = kernel.problem();
    ConstructReport report;
    report.length_before = kernel.routed_length();
    const std::size_t count = problem.parts.size();
    std::vector<char> taken(count, 0);
    for (std::size_t part = 0; part < count; ++part) taken[part] = eligible(kernel, part) ? 1 : 0;
    std::vector<std::size_t> order;
    for (std::size_t part = 0; part < count; ++part)
        if (taken[part]) order.push_back(part);
    std::vector<std::size_t> depth(count, 0);
    for (const std::size_t part : order) depth[part] = depth_of(problem, taken, part);
    std::vector<std::vector<const PadGap*>> ties(count);
    for (const auto& rule : problem.constraints.pad_gaps) {
        if (rule.sense != Sense::at_most || rule.anchor == rule.member) continue;
        ties[rule.anchor].push_back(&rule);
        ties[rule.member].push_back(&rule);
    }
    std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
        if (depth[a] != depth[b]) return depth[a] < depth[b];
        const bool faced_a = owner_rule(problem, a)->same_face, faced_b = owner_rule(problem, b)->same_face;
        if (faced_a != faced_b) return faced_a;
        if (ties[a].size() != ties[b].size()) return ties[a].size() > ties[b].size();
        const Nm limit_a = owner_rule(problem, a)->limit, limit_b = owner_rule(problem, b)->limit;
        if (limit_a != limit_b) return limit_a < limit_b;
        return a < b;
    });
    const Placement original = kernel.placement();
    for (const std::size_t part : order) kernel.park(part);
    report.taken = order.size();
    const std::vector<Point> ring = seat_ring(pitch, reach, Point{0, 0});
    std::deque<std::size_t> queue(order.begin(), order.end());
    std::vector<std::size_t> evictions(count, 0);
    std::vector<char> by_rule(count, 0);
    const auto evict_budget = static_cast<std::size_t>(constants::construct_evictions.value);
    const auto evict_window = static_cast<std::size_t>(constants::construct_window.value);
    const auto seats_of = [&](std::size_t part) {
        const PadGap& rule = *owner_rule(problem, part);
        const Pose owner = kernel.placement()[rule.anchor];
        const Part& item = problem.parts[part];
        const bool flips = problem.footprints[item.footprint].flippable && !item.top_only;
        Placement trial = kernel.placement();
        std::vector<const PadGap*> bound;
        const bool led = !kernel.parked(rule.anchor);
        std::vector<Point> centres;
        if (led) centres.push_back(owner.at);
        for (const PadGap* tie : ties[part]) {
            const std::size_t peer = tie->anchor == part ? tie->member : tie->anchor;
            if (kernel.parked(peer)) continue;
            bound.push_back(tie);
            const Point at = kernel.placement()[peer].at;
            if (std::find(centres.begin(), centres.end(), at) == centres.end()) centres.push_back(at);
        }
        std::vector<Candidate> candidates;
        candidates.reserve(ring.size());
        for (const Point centre : centres)
            for (std::size_t rank = 0; rank < ring.size(); ++rank)
                for (int turn = 0; turn < turn_count; ++turn)
                    for (const Face face : {owner.face, owner.face == Face::top ? Face::bottom : Face::top}) {
                        if (face != original[part].face && !flips) continue;
                        const Pose pose{shifted(centre, ring[rank]), static_cast<Turn>(turn), face};
                        if (led && rule.same_face && !pair_faced(problem, kernel.board(), rule.anchor, owner, part, pose, rule.or_under)) continue;
                        trial[part] = pose;
                        Nm gap = led ? pad_gap_length(problem, rule, trial) : 0;
                        bool within = true;
                        for (std::size_t index = 0; within && index < bound.size(); ++index) {
                            const Nm length = pad_gap_length(problem, *bound[index], trial);
                            within = length <= bound[index]->limit;
                            gap += length;
                        }
                        if (within) candidates.push_back({pose, gap, rank});
                    }
        trial[part] = original[part];
        if (led && (!rule.same_face || pair_faced(problem, kernel.board(), rule.anchor, owner, part, original[part], rule.or_under)) &&
            std::none_of(candidates.begin(), candidates.end(), [&](const Candidate& seat) { return seat.pose == original[part]; }))
            candidates.push_back({original[part], pad_gap_length(problem, rule, trial), ring.size()});
        std::stable_sort(candidates.begin(), candidates.end(), [&](const Candidate& a, const Candidate& b) {
            if (a.gap != b.gap) return a.gap < b.gap;
            const bool away_a = a.pose.face != owner.face, away_b = b.pose.face != owner.face;
            if (away_a != away_b) return !away_a;
            return a.rank < b.rank;
        });
        return candidates;
    };
    const auto drain = [&] {
    while (!queue.empty()) {
        const std::size_t part = queue.front();
        queue.pop_front();
        const PadGap& rule = *owner_rule(problem, part);
        const Part& item = problem.parts[part];
        const std::vector<Candidate> candidates = seats_of(part);
        bool seated = false;
        for (const Candidate& candidate : candidates) {
            if (candidate.pose.face == Face::bottom && crowds_escape(problem, kernel.placement(), part, candidate.pose)) continue;
            if (!kernel.seat(part, candidate.pose)) continue;
            seated = true;
            break;
        }
        std::size_t tried = 0;
        for (std::size_t index = 0; !seated && index < candidates.size() && tried < evict_window; ++index) {
            const Pose& pose = candidates[index].pose;
            std::vector<std::pair<std::size_t, Pose>> lifted;
            bool open = false;
            while (true) {
                const auto refusal = kernel.seat_rejection(part, pose);
                if (!refusal) {
                    open = true;
                    break;
                }
                const std::size_t blocker = refusal->other;
                if (blocker == part || !taken[blocker] || kernel.parked(blocker) || !by_rule[blocker]) break;
                if (evictions[part] + lifted.size() >= evict_budget) break;
                lifted.emplace_back(blocker, kernel.placement()[blocker]);
                kernel.park(blocker);
            }
            if (!lifted.empty()) ++tried;
            if (open && !lifted.empty() && kernel.seat(part, pose)) {
                evictions[part] += lifted.size();
                for (const auto& [blocker, held] : lifted) {
                    by_rule[blocker] = 0;
                    --report.seated;
                    queue.push_back(blocker);
                }
                seated = true;
                break;
            }
            for (auto entry = lifted.rbegin(); entry != lifted.rend(); ++entry)
                if (!kernel.seat(entry->first, entry->second))
                    throw LayoutError("layout: the constructor could not put " + problem.parts[entry->first].reference + " back on its seat");
        }
        if (seated) {
            ++report.seated;
            by_rule[part] = 1;
            continue;
        }
        if (!seated) {
            const auto tied = [&](std::size_t other) {
                return std::any_of(ties[part].begin(), ties[part].end(),
                                   [&](const PadGap* tie) { return tie->anchor == other || tie->member == other; });
            };
            const auto area = [&](std::size_t member) {
                const Box gate = problem.footprints[problem.parts[member].footprint].top.gate_box;
                return static_cast<double>(gate.x1 - gate.x0) * static_cast<double>(gate.y1 - gate.y0);
            };
            const auto node_budget = static_cast<std::size_t>(constants::construct_nodes.value);
            const auto branches = static_cast<std::size_t>(constants::construct_branches.value);
            const auto spacing = static_cast<Nm>(constants::construct_spacing.value);
            bool arranged = false;
            for (const bool wide : {false, true}) {
                std::vector<std::size_t> cluster{part};
                for (const std::size_t other : order)
                    if (other != part && by_rule[other] && !kernel.parked(other) &&
                        (owner_rule(problem, other)->anchor == rule.anchor || (wide && tied(other))))
                        cluster.push_back(other);
                std::map<std::size_t, Pose> held_at;
                for (const std::size_t member : cluster) {
                    held_at.emplace(member, kernel.placement()[member]);
                    if (member != part) kernel.park(member);
                }
                std::size_t nodes = 0;
                const std::function<bool(std::size_t)> place_all = [&](std::size_t index) {
                    if (index == cluster.size()) return true;
                    if (nodes++ >= node_budget) return false;
                    const std::size_t member = cluster[index];
                    std::vector<Pose> used;
                    for (const Candidate& seat : seats_of(member)) {
                        if (used.size() >= branches) break;
                        if (std::any_of(used.begin(), used.end(), [&](const Pose& tried) {
                                return tried.face == seat.pose.face &&
                                       squared(tried.at.x - seat.pose.at.x) + squared(tried.at.y - seat.pose.at.y) < squared(spacing);
                            }))
                            continue;
                        if (seat.pose.face == Face::bottom && crowds_escape(problem, kernel.placement(), member, seat.pose)) continue;
                        if (!kernel.seat(member, seat.pose)) continue;
                        used.push_back(seat.pose);
                        if (place_all(index + 1)) return true;
                        kernel.park(member);
                    }
                    return false;
                };
                const std::vector<std::size_t> listed = cluster;
                for (const bool largest_first : {false, true}) {
                    cluster = listed;
                    std::stable_sort(cluster.begin(), cluster.end(), [&](std::size_t a, std::size_t b) {
                        if (largest_first && area(a) != area(b)) return area(a) > area(b);
                        return owner_rule(problem, a)->limit < owner_rule(problem, b)->limit;
                    });
                    nodes = 0;
                    if (place_all(0)) {
                        arranged = true;
                        break;
                    }
                }
                if (arranged) break;
                for (const std::size_t member : listed)
                    if (member != part && !kernel.seat(member, held_at.at(member)))
                        throw LayoutError("layout: the constructor could not put " + problem.parts[member].reference + " back on its seat");
            }
            if (arranged) {
                ++report.seated;
                ++report.searched;
                by_rule[part] = 1;
                continue;
            }
        }
        if (kernel.seat(part, original[part])) {
            ++report.returned;
            continue;
        }
        report.unseated.push_back(item.reference);
        std::map<std::string, std::size_t> tally;
        for (const Candidate& candidate : candidates)
            if (const auto refusal = kernel.seat_rejection(part, candidate.pose))
                ++tally[std::string(breach_name(refusal->kind)) + " against " + problem.parts[refusal->other].reference +
                        (refusal->other == part ? "" : !taken[refusal->other] ? " (kept from the first stage)" : by_rule[refusal->other] ? " (seated by rule)" : " (returned to its first seat)")];
        std::vector<std::pair<std::size_t, std::string>> ranked;
        for (const auto& [cause, seen] : tally) ranked.emplace_back(seen, cause);
        std::sort(ranked.rbegin(), ranked.rend());
        std::string line = item.reference + " (owner " + problem.parts[rule.anchor].reference + ", " +
                           std::to_string(candidates.size()) + " seats within its tie):";
        for (std::size_t index = 0; index < ranked.size() && index < cause_rows; ++index)
            line += " " + std::to_string(ranked[index].first) + " x " + ranked[index].second + ";";
        if (const auto refusal = kernel.seat_rejection(part, original[part]))
            line += " first seat refused by " + std::string(breach_name(refusal->kind)) + " against " + problem.parts[refusal->other].reference;
        report.causes.push_back(std::move(line));
    }
    };
    drain();
    for (std::size_t round = 0; round < static_cast<std::size_t>(constants::construct_rounds.value); ++round) {
        for (const std::size_t part : order) {
            if (!by_rule[part] || kernel.parked(part)) continue;
            const PadGap& rule = *owner_rule(problem, part);
            if (!rule.same_face || pair_faced(problem, kernel.board(), rule.anchor, kernel.placement()[rule.anchor], part,
                                              kernel.placement()[part], rule.or_under))
                continue;
            kernel.park(part);
            by_rule[part] = 0;
            --report.seated;
            queue.push_back(part);
        }
        if (queue.empty()) break;
        drain();
    }
    report.length_after = kernel.routed_length();
    return report;
}

std::string construct_summary(const ConstructReport& report) {
    std::string out = "constructor: took " + std::to_string(report.taken) + " owned parts off the board, seated " +
                      std::to_string(report.seated) + " by rule, returned " + std::to_string(report.returned) +
                      " to their first seats, could not seat " + std::to_string(report.unseated.size()) + "; " +
                      std::to_string(report.searched) + " needed their owner's parts arranged together\n";
    out += "  wire length " + std::to_string(report.length_before) + " nm before, " + std::to_string(report.length_after) + " nm after\n";
    for (const auto& name : report.unseated) out += "  unseated: " + name + "\n";
    for (const auto& cause : report.causes) out += "  " + cause + "\n";
    return out;
}

}
