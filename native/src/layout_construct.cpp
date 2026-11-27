#include "schgen/layout_construct.hpp"

#include "schgen/layout_sink.hpp"

#include <algorithm>
#include <deque>
#include <sstream>
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
    if (!kernel.releasable(part)) return false;
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

bool free_root(const Kernel& kernel, std::size_t part) {
    const Part& item = kernel.problem().parts[part];
    if (item.fixed || item.connector || item.module || item.corner || item.edge) return false;
    return kernel.releasable(part);
}

}

std::vector<char> owned_under(const Problem& problem, std::size_t owner) {
    std::vector<char> under(problem.parts.size(), 0);
    if (problem.ownership.empty()) return under;
    for (std::size_t part = 0; part < problem.parts.size(); ++part) {
        std::size_t at = part;
        for (std::size_t depth = 0; problem.ownership[at].owner && depth < problem.parts.size(); ++depth) {
            at = *problem.ownership[at].owner;
            if (at == owner) {
                under[part] = 1;
                break;
            }
        }
    }
    return under;
}

ConstructReport construct_owned(Kernel& kernel, Nm pitch, Nm reach, bool arrange, const std::vector<char>* only) {
    const Problem& problem = kernel.problem();
    ConstructReport report;
    report.length_before = kernel.routed_length();
    const std::size_t count = problem.parts.size();
    std::vector<char> taken(count, 0);
    for (std::size_t part = 0; part < count; ++part) taken[part] = eligible(kernel, part) && (!only || (*only)[part]) ? 1 : 0;
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
    for (const std::size_t part : order) {
        if (!kernel.movable_alone(part) && !kernel.release(part))
            throw LayoutError("layout: " + problem.parts[part].reference + " could not be released from its reserved field");
        kernel.park(part);
    }
    report.taken = order.size();
    const std::vector<Point> ring = seat_ring(pitch, reach, Point{0, 0});
    std::deque<std::size_t> queue;
    std::vector<std::size_t> evictions(count, 0);
    std::vector<char> by_rule(count, 0);
    bool stuck = false;
    const std::vector<char>* scope = nullptr;
    const auto evict_budget = static_cast<std::size_t>(constants::construct_evictions.value);
    const auto evict_window = static_cast<std::size_t>(constants::construct_window.value);
    std::vector<char> leads_face(count, 0);
    for (const auto& rule : problem.constraints.soft_gaps)
        if (rule.same_face && !rule.or_under) leads_face[rule.anchor] = 1;
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
        std::optional<Box> hull;
        if (led) {
            hull = gate_at(problem, rule.anchor, owner);
            for (const std::size_t other : order)
                if (other != part && !kernel.parked(other) && owner_rule(problem, other)->anchor == rule.anchor)
                    hull = united(*hull, gate_at(problem, other, kernel.placement()[other]));
        }
        const auto spread = [&](const Pose& pose) {
            if (!hull) return Nm{0};
            const Box grown = united(*hull, gate_at(problem, part, pose));
            return (grown.x1 - grown.x0) + (grown.y1 - grown.y0) - (hull->x1 - hull->x0) - (hull->y1 - hull->y0);
        };
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
                        if (within) candidates.push_back({pose, gap + spread(pose), rank});
                    }
        trial[part] = original[part];
        if (led && (!rule.same_face || pair_faced(problem, kernel.board(), rule.anchor, owner, part, original[part], rule.or_under)) &&
            std::none_of(candidates.begin(), candidates.end(), [&](const Candidate& seat) { return seat.pose == original[part]; }))
            candidates.push_back({original[part], pad_gap_length(problem, rule, trial), ring.size()});
        const bool leads = leads_face[part] != 0;
        std::stable_sort(candidates.begin(), candidates.end(), [&](const Candidate& a, const Candidate& b) {
            const bool away_a = a.pose.face != owner.face, away_b = b.pose.face != owner.face;
            if (leads && away_a != away_b) return !away_a;
            if (a.gap != b.gap) return a.gap < b.gap;
            if (away_a != away_b) return !away_a;
            return a.rank < b.rank;
        });
        return candidates;
    };
    const auto drain = [&](bool firm, bool deep) {
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
                if (scope && !(*scope)[blocker]) break;
                if (evictions[part] + lifted.size() >= evict_budget) break;
                lifted.emplace_back(blocker, kernel.placement()[blocker]);
                kernel.park(blocker);
            }
            if (!lifted.empty()) ++tried;
            if (open && !lifted.empty() && kernel.seat(part, pose)) {
                evictions[part] += lifted.size();
                for (const auto& [blocker, held] : lifted) {
                    by_rule[blocker] = 0;
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
            by_rule[part] = 1;
            continue;
        }
        if (!seated && deep) {
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
                ++report.searched;
                by_rule[part] = 1;
                continue;
            }
        }
        if (!firm) {
            stuck = true;
            queue.clear();
            return;
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
    if (arrange) {
        std::vector<std::size_t> root_of(count, count);
        for (const std::size_t part : order) {
            std::size_t at = part;
            while (taken[at]) at = *problem.ownership[at].owner;
            root_of[part] = at;
        }
        std::vector<std::size_t> roots;
        for (std::size_t part = 0; part < count; ++part)
            if (!taken[part] && free_root(kernel, part)) roots.push_back(part);
        std::vector<std::vector<std::size_t>> members(count);
        std::vector<double> weight(count, 0);
        const auto area = [&](std::size_t member) {
            const Box gate = problem.footprints[problem.parts[member].footprint].top.gate_box;
            return static_cast<double>(gate.x1 - gate.x0) * static_cast<double>(gate.y1 - gate.y0);
        };
        for (const std::size_t root : roots) weight[root] = area(root);
        for (const std::size_t part : order) {
            members[root_of[part]].push_back(part);
            weight[root_of[part]] += area(part);
        }
        for (const std::size_t part : order)
            if (!free_root(kernel, root_of[part])) queue.push_back(part);
        drain(true, true);
        std::stable_sort(roots.begin(), roots.end(), [&](std::size_t a, std::size_t b) { return weight[a] > weight[b]; });
        for (const std::size_t root : roots) {
            if (!kernel.movable_alone(root) && !kernel.release(root))
                throw LayoutError("layout: " + problem.parts[root].reference + " could not be released from its reserved field");
            kernel.park(root);
        }
        report.roots = roots.size();
        const Nm span = problem.board.width + problem.board.height;
        const std::vector<Point> sweep = seat_ring(static_cast<Nm>(constants::construct_sweep.value), span, Point{0, 0});
        const Box outline = kernel.board().outline();
        for (const std::size_t root : roots) {
            std::vector<char> inside(count, 0);
            inside[root] = 1;
            for (const std::size_t member : members[root]) inside[member] = 1;
            double sum_x = 0, sum_y = 0, pulls = 0;
            for (const Net& net : problem.nets) {
                if (net.category == Category::plane) continue;
                if (std::none_of(net.pins.begin(), net.pins.end(), [&](const Pin& pin) { return inside[pin.part] != 0; })) continue;
                for (const Pin& pin : net.pins) {
                    if (inside[pin.part] || kernel.parked(pin.part)) continue;
                    sum_x += static_cast<double>(kernel.placement()[pin.part].at.x);
                    sum_y += static_cast<double>(kernel.placement()[pin.part].at.y);
                    pulls += 1;
                }
            }
            for (std::size_t mate = 0; mate < count; ++mate) {
                if (inside[mate] || kernel.parked(mate) || problem.parts[mate].group != problem.parts[root].group) continue;
                sum_x += static_cast<double>(kernel.placement()[mate].at.x);
                sum_y += static_cast<double>(kernel.placement()[mate].at.y);
                pulls += 1;
            }
            const Point target = pulls > 0 ? Point{static_cast<Nm>(sum_x / pulls), static_cast<Nm>(sum_y / pulls)}
                                           : Point{(outline.x0 + outline.x1) / 2, (outline.y0 + outline.y1) / 2};
            const Point snapped{target.x - target.x % pitch, target.y - target.y % pitch};
            const Part& item = problem.parts[root];
            const bool flips = problem.footprints[item.footprint].flippable && !item.top_only;
            bool built = false;
            scope = &inside;
            std::optional<Box> held;
            for (std::size_t mate = 0; mate < count; ++mate) {
                if (inside[mate] || kernel.parked(mate) || problem.parts[mate].group != item.group) continue;
                const Box box = gate_at(problem, mate, kernel.placement()[mate]);
                held = held ? united(*held, box) : box;
            }
            const auto attempt = [&](std::size_t budget, const std::optional<Box>& within) {
                std::size_t tried = 0;
                for (std::size_t rank = 0; tried < budget && rank < sweep.size(); ++rank) {
                    const Point at = shifted(snapped, sweep[rank]);
                    if (at.x < outline.x0 || at.x > outline.x1 || at.y < outline.y0 || at.y > outline.y1) continue;
                    bool legal = false;
                    for (const Face face : {original[root].face, original[root].face == Face::top ? Face::bottom : Face::top}) {
                        if (face != original[root].face && !flips) continue;
                        for (int turn = 0; turn < turn_count; ++turn) {
                            const Pose pose{at, static_cast<Turn>(turn), face};
                            if (within && !layout::inside(gate_at(problem, root, pose), *within)) continue;
                            if (face == Face::bottom && crowds_escape(problem, kernel.placement(), root, pose)) continue;
                            if (!kernel.seat(root, pose)) continue;
                            legal = true;
                            ++report.trials;
                            stuck = false;
                            queue.assign(members[root].begin(), members[root].end());
                            drain(false, false);
                            if (!stuck && !kernel.breach(root)) return true;
                            for (const std::size_t member : members[root]) {
                                if (!kernel.parked(member)) kernel.park(member);
                                by_rule[member] = 0;
                            }
                            kernel.park(root);
                        }
                    }
                    if (legal) ++tried;
                }
                return false;
            };
            built = (held && attempt(static_cast<std::size_t>(constants::construct_trials.value), held)) ||
                    attempt(static_cast<std::size_t>(constants::construct_trials.value), std::nullopt);
            scope = nullptr;
            if (built) {
                ++report.arranged;
                continue;
            }
            report.kept.push_back(item.reference + " (" + std::to_string(members[root].size()) + " owned parts)");
            bool back = kernel.seat(root, original[root]);
            for (std::size_t rank = 0; !back && rank < sweep.size(); ++rank)
                for (int turn = 0; !back && turn < turn_count; ++turn)
                    back = kernel.seat(root, Pose{shifted(original[root].at, sweep[rank]), static_cast<Turn>(turn), original[root].face});
            if (!back) {
                report.unseated.push_back(item.reference);
                const auto refused = kernel.seat_rejection(root, original[root]);
                report.causes.push_back(item.reference + " (unowned): its first seat is refused by " +
                                        (refused ? std::string(breach_name(refused->kind)) + " against " +
                                                       (refused->other < count ? problem.parts[refused->other].reference : std::string("the board"))
                                                 : std::string("nothing")) +
                                        "; no seat on the board at the sweep pitch");
                if (refused && refused->kind == Breach::dispersion) {
                    std::optional<Box> hull;
                    double total = 0;
                    std::array<std::size_t, edge_count> extreme{root, root, root, root};
                    for (std::size_t mate = 0; mate < count; ++mate) {
                        if (mate == root || kernel.parked(mate) || problem.parts[mate].group != item.group) continue;
                        const Box box = gate_at(problem, mate, kernel.placement()[mate]);
                        total += static_cast<double>(box.width()) * static_cast<double>(box.height());
                        if (!hull || box.y0 < hull->y0) extreme[0] = mate;
                        if (!hull || box.y1 > hull->y1) extreme[1] = mate;
                        if (!hull || box.x0 < hull->x0) extreme[2] = mate;
                        if (!hull || box.x1 > hull->x1) extreme[3] = mate;
                        hull = hull ? united(*hull, box) : box;
                    }
                    if (hull) {
                        std::ostringstream line;
                        line << item.reference << ": subsystem " << item.group << " already spans " << to_mm(hull->width()) << " x "
                             << to_mm(hull->height()) << " mm for " << total / (constants::nano_scale.value * constants::nano_scale.value)
                             << " mm2 of parts, limit " << problem.rules.dispersion_limit << " times that; outermost parts north "
                             << problem.parts[extreme[0]].reference << ", south " << problem.parts[extreme[1]].reference << ", west "
                             << problem.parts[extreme[2]].reference << ", east " << problem.parts[extreme[3]].reference;
                        report.causes.push_back(line.str());
                    }
                }
                continue;
            }
            queue.assign(members[root].begin(), members[root].end());
            drain(true, true);
        }
    } else {
        queue.assign(order.begin(), order.end());
        drain(true, true);
    }
    for (std::size_t round = 0; round < static_cast<std::size_t>(constants::construct_rounds.value); ++round) {
        for (const std::size_t part : order) {
            if (!by_rule[part] || kernel.parked(part)) continue;
            const PadGap& rule = *owner_rule(problem, part);
            if (!rule.same_face || pair_faced(problem, kernel.board(), rule.anchor, kernel.placement()[rule.anchor], part,
                                              kernel.placement()[part], rule.or_under))
                continue;
            kernel.park(part);
            by_rule[part] = 0;
            queue.push_back(part);
        }
        if (queue.empty()) break;
        drain(true, true);
    }
    report.seated = static_cast<std::size_t>(std::count(by_rule.begin(), by_rule.end(), 1));
    report.length_after = kernel.routed_length();
    return report;
}

std::string construct_summary(const ConstructReport& report) {
    std::string out = "constructor: took " + std::to_string(report.taken) + " owned parts off the board, seated " +
                      std::to_string(report.seated) + " by rule, returned " + std::to_string(report.returned) +
                      " to their first seats, could not seat " + std::to_string(report.unseated.size()) + "; " +
                      std::to_string(report.searched) + " needed their owner's parts arranged together\n";
    if (report.roots != 0)
        out += "  took " + std::to_string(report.roots) + " unowned parts off the board with their owned parts, placed " +
               std::to_string(report.arranged) + " of them afresh after " + std::to_string(report.trials) + " trial seats\n";
    out += "  wire length " + std::to_string(report.length_before) + " nm before, " + std::to_string(report.length_after) + " nm after\n";
    for (const auto& name : report.kept) out += "  no fresh place, kept beside its first seat: " + name + "\n";
    for (const auto& name : report.unseated) out += "  unseated: " + name + "\n";
    for (const auto& cause : report.causes) out += "  " + cause + "\n";
    return out;
}

}
