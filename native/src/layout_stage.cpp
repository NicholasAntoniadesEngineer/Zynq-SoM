#include "schgen/layout_stage.hpp"

#include "schgen/placement_integrity.hpp"

#include <functional>
#include <cmath>
#include <algorithm>
#include <map>
#include <set>
#include <sstream>
#include <tuple>

namespace schgen::layout {
namespace {

inline constexpr double percent = 100;
inline constexpr std::size_t straggler_rows = 12;
inline constexpr std::size_t stuck_rows = 4;

std::vector<Box> ordered(std::vector<Box> boxes) {
    std::sort(boxes.begin(), boxes.end(), [](const Box& a, const Box& b) {
        return std::tie(a.x0, a.y0, a.x1, a.y1) < std::tie(b.x0, b.y0, b.x1, b.y1);
    });
    return boxes;
}

std::size_t unmet_count(const Kernel& kernel) {
    const Problem& problem = kernel.problem();
    std::size_t count = 0;
    for (const PadGap& rule : problem.constraints.soft_gaps)
        if (rule.same_face && !pair_faced(problem, kernel.board(), rule.anchor, kernel.placement()[rule.anchor],
                                          rule.member, kernel.placement()[rule.member], rule.or_under))
            ++count;
    for (const NetOrder& rule : net_orders_of(problem))
        if (!net_order_met(problem, rule, kernel.placement(), rule.lead, nullptr)) ++count;
    return count;
}

bool adds_breach(const std::vector<Violation>& before, const std::vector<Violation>& after) {
    const auto key = [](const Violation& violation) {
        return std::make_tuple(static_cast<int>(violation.kind), std::min(violation.part, violation.other),
                               std::max(violation.part, violation.other));
    };
    std::set<std::tuple<int, std::size_t, std::size_t>> known;
    for (const Violation& violation : before) known.insert(key(violation));
    return std::any_of(after.begin(), after.end(), [&](const Violation& violation) { return !known.count(key(violation)); });
}

std::string added_breach(const Kernel& kernel, const std::vector<Violation>& before, const std::vector<Violation>& after) {
    const auto key = [](const Violation& violation) {
        return std::make_tuple(static_cast<int>(violation.kind), std::min(violation.part, violation.other),
                               std::max(violation.part, violation.other));
    };
    std::set<std::tuple<int, std::size_t, std::size_t>> known;
    for (const Violation& violation : before) known.insert(key(violation));
    const auto& parts = kernel.problem().parts;
    for (const Violation& violation : after)
        if (!known.count(key(violation)))
            return std::string(breach_name(violation.kind)) + " " + parts[violation.part].reference +
                   (violation.other != violation.part && violation.other < parts.size() ? " / " + parts[violation.other].reference : "");
    return {};
}

bool flip_set(Kernel& kernel, std::size_t anchor) {
    const Problem& problem = kernel.problem();
    const Face to = kernel.placement()[anchor].face == Face::top ? Face::bottom : Face::top;
    std::vector<std::size_t> set{anchor};
    for (const PadGap& rule : problem.constraints.soft_gaps)
        if (rule.same_face && rule.anchor == anchor &&
            std::find(set.begin(), set.end(), rule.member) == set.end())
            set.push_back(rule.member);
    std::vector<Move> moves;
    for (const std::size_t part : set) {
        const Part& item = problem.parts[part];
        if (item.fixed || item.top_only || !problem.footprints[item.footprint].flippable || item.edge) return false;
        Pose pose = kernel.placement()[part];
        pose.face = to;
        moves.push_back({part, pose});
    }
    const Snapshot before = kernel.snapshot();
    if (!kernel.force(moves)) return false;
    if (std::any_of(set.begin(), set.end(), [&](std::size_t part) { return kernel.breach(part).has_value(); })) {
        kernel.restore(before);
        return false;
    }
    return true;
}

bool reface(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius, std::size_t& aside) {
    const Problem& problem = kernel.problem();
    const std::size_t anchor = rule.anchor;
    const Part& item = problem.parts[anchor];
    const Pose from = kernel.placement()[anchor];
    const Face to = kernel.placement()[rule.member].face;
    if (to == from.face || item.fixed || item.edge || !problem.footprints[item.footprint].flippable ||
        (item.top_only && to == Face::bottom))
        return false;
    for (const Point by : seat_ring(pitch, radius, {0, 0})) {
        Pose pose = from;
        pose.at = shifted(from.at, by);
        pose.face = to;
        if (kernel.rejection(anchor, pose)) continue;
        const Snapshot before = kernel.snapshot();
        if (!kernel.move(anchor, pose)) continue;
        if (seat_faced(kernel, rule, pitch, radius, true, aside)) return true;
        kernel.restore(before);
    }
    return false;
}

std::vector<RepairRow> repair_inherited(Kernel& kernel, const SqueezeOptions& settings, const Bundles& clusters,
                                        std::size_t& inherited) {
    const Problem& problem = kernel.problem();
    std::vector<RepairRow> rows;
    inherited = unmet_count(kernel);
    const Nm near = static_cast<Nm>(constants::ring_limit.value);
    const Nm wide = static_cast<Nm>(constants::wide_reach.value);
    const Nm coarse = static_cast<Nm>(constants::far_pitch.value);
    const auto attempt = [&](RepairRow row, const auto& step) {
        row.before = unmet_count(kernel);
        const std::vector<Violation> known = kernel.violations();
        const Snapshot snap = kernel.snapshot();
        const bool done = step();
        row.after = unmet_count(kernel);
        const std::string added = done ? added_breach(kernel, known, kernel.violations()) : std::string();
        row.kept = done && row.after < row.before && added.empty();
        if (done && !added.empty()) row.action += "; refused: it adds " + added;
        if (!row.kept) {
            kernel.restore(snap);
            row.after = row.before;
        }
        rows.push_back(row);
        return row.kept;
    };
    std::vector<const PadGap*> tightest;
    for (const PadGap& rule : problem.constraints.soft_gaps) tightest.push_back(&rule);
    std::stable_sort(tightest.begin(), tightest.end(), [](const PadGap* a, const PadGap* b) { return a->reach < b->reach; });
    for (const PadGap* next : tightest) {
        const PadGap& rule = *next;
        const auto faced = [&] {
            return pair_faced(problem, kernel.board(), rule.anchor, kernel.placement()[rule.anchor], rule.member,
                              kernel.placement()[rule.member], rule.or_under);
        };
        if (!rule.same_face || faced()) continue;
        const std::string subject = problem.parts[rule.member].reference + " -> " + problem.parts[rule.anchor].reference;
        std::size_t aside = 0;
        const auto seat = [&](Nm pitch, Nm radius, bool evict) {
            return [&, pitch, radius, evict] { return seat_faced(kernel, rule, pitch, radius, evict, aside); };
        };
        if (attempt({"0", rule.source, subject, "reseat at the pin on its face"}, seat(settings.pitch, near, false))) continue;
        if (attempt({"1", rule.source, subject, "reseat after moving small parts aside"}, seat(settings.pitch, near, true))) continue;
        if (attempt({"1", rule.source, subject, "reseat in the wide ring"}, seat(coarse, wide, true))) continue;
        if (attempt({"1", rule.source, subject, "reseat together with the parts tied to it"},
                    [&] { return seat_faced_together(kernel, rule, coarse, wide); }))
            continue;
        if (attempt({"1", rule.source, subject, "take the seat at the pin and reseat the parts in it by their own rules"},
                    [&] { return seat_faced_chain(kernel, rule, settings.pitch, near, aside); }))
            continue;
        if (attempt({"2", rule.source, subject, "move " + problem.parts[rule.anchor].reference + " and its face-tied set to the other face"},
                    [&] { return flip_set(kernel, rule.anchor); }))
            continue;
        if (attempt({"2", rule.source, subject, "move " + problem.parts[rule.anchor].reference + " to the face of " +
                                                     problem.parts[rule.member].reference + " at the nearest free seat and reseat"},
                    [&] { return reface(kernel, rule, coarse, wide, aside); }))
            continue;
        if (attempt({"3", rule.source, subject, "re-home the cluster of " + problem.parts[rule.anchor].reference + " and reseat"}, [&] {
                return rehome(kernel, clusters.units[clusters.unit_of[rule.anchor]]) &&
                       seat_faced(kernel, rule, coarse, wide, true, aside);
            }))
            continue;
        attempt({"4", rule.source, subject, "widen every side one step at a time and reseat"}, [&] {
            for (std::size_t step = 0; step < static_cast<std::size_t>(constants::widen_steps.value); ++step) {
                for (const Side side : {Side::north, Side::south, Side::west, Side::east})
                    widen(kernel, settings, side, settings.first_step);
                if (seat_faced(kernel, rule, coarse, wide, true, aside)) return true;
            }
            return false;
        });
    }
    for (const NetOrder& rule : net_orders_of(problem)) {
        if (net_order_met(problem, rule, kernel.placement(), rule.lead, nullptr)) continue;
        const std::string subject = problem.parts[rule.lead].reference + " -> " + problem.parts[rule.anchor].reference;
        if (attempt({"1", "protection order", subject, "seat the protection part first and move the parts nearer than it back"},
                    [&] { return seat_first(kernel, rule, settings.pitch); }))
            continue;
        attempt({"4", "protection order", subject, "widen every side one step at a time and reorder"}, [&] {
            for (std::size_t step = 0; step < static_cast<std::size_t>(constants::widen_steps.value); ++step) {
                for (const Side side : {Side::north, Side::south, Side::west, Side::east})
                    widen(kernel, settings, side, settings.first_step);
                lead_first(kernel, settings.pitch);
                if (net_order_met(problem, rule, kernel.placement(), rule.lead, nullptr)) return true;
            }
            return false;
        });
    }
    return rows;
}

std::size_t gap_count(const Kernel& kernel) {
    const auto found = kernel.violations();
    return static_cast<std::size_t>(std::count_if(found.begin(), found.end(),
        [](const Violation& violation) { return violation.kind == Breach::connector_gap; }));
}

Nm clearing_reach(const Problem& problem, std::size_t first, std::size_t second) {
    const auto need = [&](std::size_t part) {
        const Part& item = problem.parts[part];
        return item.access.value_or(0) + item.access_front.value_or(0) + item.plug_width.value_or(0);
    };
    return static_cast<Nm>(constants::wide_reach.value) + std::max(need(first), need(second));
}

bool slide(Kernel& kernel, std::size_t part, Nm pitch, Nm reach, std::map<std::string, std::size_t>& blocked) {
    const Part& item = kernel.problem().parts[part];
    const Pose from = kernel.placement()[part];
    const bool along_x = !item.edge || item.edge->mouth.y != 0;
    const bool along_y = !item.edge || item.edge->mouth.x != 0;
    const std::size_t gaps = gap_count(kernel);
    for (Nm distance = pitch; distance <= reach; distance += pitch)
        for (const Nm sign : {Nm{1}, Nm{-1}})
            for (const bool x : {true, false}) {
                if ((x && !along_x) || (!x && !along_y)) continue;
                Pose pose = from;
                pose.at = shifted(from.at, x ? Point{sign * distance, 0} : Point{0, sign * distance});
                if (const auto found = kernel.rejection(part, pose)) {
                    const std::size_t other = found->part == part ? found->other : found->part;
                    ++blocked[std::string(breach_name(found->kind)) + " " +
                              (other < kernel.problem().parts.size() && other != part ? kernel.problem().parts[other].reference : "board")];
                    continue;
                }
                const Snapshot before = kernel.snapshot();
                if (!kernel.move(part, pose)) {
                    ++blocked["move refused"];
                    continue;
                }
                if (gap_count(kernel) < gaps) return true;
                ++blocked["gap not cleared"];
                kernel.restore(before);
            }
    return false;
}

bool slide_together(Kernel& kernel, std::size_t part, std::size_t other, Nm pitch, Nm reach,
                    std::map<std::string, std::size_t>& blocked) {
    const Problem& problem = kernel.problem();
    const Part& item = problem.parts[part];
    std::vector<std::size_t> set{part};
    for (std::size_t index = 0; index < set.size(); ++index) {
        const auto follow = [&](const PadGap& tie) {
            if (tie.anchor == set[index] && tie.member != other && !problem.parts[tie.member].fixed &&
                !problem.parts[tie.member].connector && std::find(set.begin(), set.end(), tie.member) == set.end())
                set.push_back(tie.member);
        };
        for (const PadGap& tie : problem.constraints.pad_gaps) follow(tie);
        for (const PadGap& tie : problem.constraints.soft_gaps) follow(tie);
    }
    if (set.size() == 1) return false;
    const bool along_x = !item.edge || item.edge->mouth.y != 0;
    const bool along_y = !item.edge || item.edge->mouth.x != 0;
    const std::size_t gaps = gap_count(kernel);
    for (Nm distance = pitch; distance <= reach; distance += pitch)
        for (const Nm sign : {Nm{1}, Nm{-1}})
            for (const bool x : {true, false}) {
                if ((x && !along_x) || (!x && !along_y)) continue;
                const Point by = x ? Point{sign * distance, 0} : Point{0, sign * distance};
                std::vector<Move> moves;
                for (const std::size_t member : set) {
                    Pose pose = kernel.placement()[member];
                    pose.at = shifted(pose.at, by);
                    moves.push_back({member, pose});
                }
                const Snapshot before = kernel.snapshot();
                if (!kernel.force(moves)) {
                    ++blocked["move refused"];
                    continue;
                }
                const auto stuck = std::find_if(set.begin(), set.end(), [&](std::size_t member) { return kernel.breach(member).has_value(); });
                if (stuck == set.end() && gap_count(kernel) < gaps) return true;
                if (stuck != set.end()) {
                    const Violation found = *kernel.breach(*stuck);
                    const std::size_t peer = found.part == *stuck ? found.other : found.part;
                    ++blocked[std::string(breach_name(found.kind)) + " " + problem.parts[*stuck].reference + "/" +
                              (peer != *stuck && peer < problem.parts.size() ? problem.parts[peer].reference : "board")];
                } else {
                    ++blocked["gap not cleared"];
                }
                kernel.restore(before);
            }
    return false;
}

bool open_gap(Kernel& kernel, const SqueezeOptions& settings, const Bundles& clusters, std::size_t first, std::size_t second,
              std::map<std::string, std::size_t>& blocked) {
    const Problem& problem = kernel.problem();
    const Box a = gate_at(problem, first, kernel.placement()[first]);
    const Box b = gate_at(problem, second, kernel.placement()[second]);
    const Nm dx = (b.x0 + b.x1) - (a.x0 + a.x1), dy = (b.y0 + b.y1) - (a.y0 + a.y1);
    const bool along_x = (dx < 0 ? -dx : dx) >= (dy < 0 ? -dy : dy);
    const Box& low = (along_x ? dx : dy) >= 0 ? a : b;
    const Box& high = (along_x ? dx : dy) >= 0 ? b : a;
    const Nm split = along_x ? (low.x1 + high.x0) / 2 : (low.y1 + high.y0) / 2;
    const Nm reach = clearing_reach(problem, first, second);
    std::vector<char> anchored(clusters.units.size(), 0);
    for (std::size_t unit = 0; unit < clusters.units.size(); ++unit)
        anchored[unit] = std::any_of(clusters.units[unit].begin(), clusters.units[unit].end(),
                                     [&](std::size_t part) { return problem.parts[part].fixed; });
    for (bool grown = true; grown;) {
        grown = false;
        for (const PadGap& tie : problem.constraints.pad_gaps) {
            const std::size_t one = clusters.unit_of[tie.anchor], two = clusters.unit_of[tie.member];
            if (anchored[one] == anchored[two]) continue;
            anchored[one] = anchored[two] = 1;
            grown = true;
        }
    }
    for (const bool move_high : {true, false}) {
        std::vector<char> moving(problem.parts.size(), 0);
        bool held = false, any = false;
        const std::size_t low_unit = clusters.unit_of[(along_x ? dx : dy) >= 0 ? first : second];
        const std::size_t high_unit = clusters.unit_of[(along_x ? dx : dy) >= 0 ? second : first];
        const std::size_t low_part = (along_x ? dx : dy) >= 0 ? first : second;
        const std::size_t high_part = (along_x ? dx : dy) >= 0 ? second : first;
        const auto tied_to = [&](std::size_t lead, std::size_t rival) {
            std::vector<char> tied(problem.parts.size(), 0);
            std::vector<std::size_t> set{lead};
            tied[lead] = 1;
            for (std::size_t index = 0; index < set.size(); ++index) {
                const auto follow = [&](const PadGap& tie) {
                    if (tie.anchor != set[index] || tie.member == rival || tied[tie.member]) return;
                    tied[tie.member] = 1;
                    set.push_back(tie.member);
                };
                for (const PadGap& tie : problem.constraints.pad_gaps) follow(tie);
                for (const PadGap& tie : problem.constraints.soft_gaps) follow(tie);
            }
            return tied;
        };
        const bool shared = low_unit == high_unit;
        const std::vector<char> with_low = shared ? tied_to(low_part, high_part) : std::vector<char>();
        const std::vector<char> with_high = shared ? tied_to(high_part, low_part) : std::vector<char>();
        for (std::size_t unit = 0; unit < clusters.units.size(); ++unit) {
            const Box hull = hull_at(problem, kernel.placement(), clusters.units[unit]);
            const Nm centre = along_x ? (hull.x0 + hull.x1) / 2 : (hull.y0 + hull.y1) / 2;
            const bool high = unit == high_unit || (unit != low_unit && centre >= split);
            if (anchored[unit]) continue;
            for (const std::size_t part : clusters.units[unit]) {
                bool above = high;
                if (shared && unit == high_unit) {
                    const Box box = gate_at(problem, part, kernel.placement()[part]);
                    const Nm middle = along_x ? (box.x0 + box.x1) / 2 : (box.y0 + box.y1) / 2;
                    above = with_high[part] != with_low[part] ? with_high[part] != 0 : middle >= split;
                }
                if (above != move_high) continue;
                if (problem.parts[part].corner) continue;
                held = held || problem.parts[part].fixed;
                moving[part] = 1;
                any = true;
            }
        }
        if (held || !any) {
            ++blocked[held ? "a fixed part is on the side to shift" : "nothing lies beyond the gap"];
            continue;
        }
        const Side side = along_x ? (move_high ? Side::east : Side::west) : (move_high ? Side::south : Side::north);
        const Nm sign = move_high ? 1 : -1;
        for (Nm by = settings.first_step; by <= reach; by += settings.first_step) {
            const Snapshot before = kernel.snapshot();
            const std::vector<Violation> known = kernel.violations();
            const std::size_t illegal = known.size();
            if (!open_side(kernel, settings, side, by)) {
                ++blocked["the board could not be widened"];
                continue;
            }
            std::vector<Move> moves;
            for (std::size_t part = 0; part < problem.parts.size(); ++part) {
                if (problem.parts[part].corner) continue;
                Pose pose = before.placement[part];
                if (moving[part]) pose.at = shifted(pose.at, along_x ? Point{sign * by, 0} : Point{0, sign * by});
                if (pose != kernel.placement()[part]) moves.push_back({part, pose});
            }
            if (!kernel.force(moves)) {
                ++blocked["the shift was refused"];
            } else if (kernel.violations().size() >= illegal || adds_breach(known, kernel.violations())) {
                const auto found = kernel.violations();
                std::map<std::string, std::size_t> kinds;
                std::string sample;
                for (const Violation& violation : found) {
                    if (++kinds[breach_name(violation.kind)] > 2) continue;
                    sample += " " + std::string(breach_name(violation.kind)) + ":" + problem.parts[violation.part].reference + "/" +
                              (violation.other < problem.parts.size() ? problem.parts[violation.other].reference : "board");
                }
                ++blocked["the shift by " + std::to_string(by / 1000000) + " mm " + (move_high ? "high" : "low") + " half left " +
                          std::to_string(found.size()) + " breaches of " + std::to_string(illegal) + ":" + sample];
            } else if (const auto a = kernel.rejection(first, kernel.placement()[first])) {
                ++blocked[std::string(breach_name(a->kind)) + " at " + problem.parts[first].reference];
            } else if (const auto b = kernel.rejection(second, kernel.placement()[second])) {
                ++blocked[std::string(breach_name(b->kind)) + " at " + problem.parts[second].reference];
            } else {
                return true;
            }
            kernel.restore(before);
        }
    }
    return false;
}

std::vector<RepairRow> separate_connectors(Kernel& kernel, const SqueezeOptions& settings, const Bundles& clusters) {
    const Problem& problem = kernel.problem();
    std::vector<RepairRow> rows;
    std::set<std::pair<std::size_t, std::size_t>> seen;
    for (;;) {
        std::optional<Violation> next;
        for (const Violation& violation : kernel.violations())
            if (violation.kind == Breach::connector_gap &&
                seen.insert({std::min(violation.part, violation.other), std::max(violation.part, violation.other)}).second) {
                next = violation;
                break;
            }
        if (!next) break;
        const std::string subject = problem.parts[next->part].reference + " / " + problem.parts[next->other].reference;
        const auto attempt = [&](RepairRow row, const auto& step) {
            row.before = gap_count(kernel);
            const std::vector<Violation> known = kernel.violations();
            const Snapshot snap = kernel.snapshot();
            const bool done = step();
            row.after = gap_count(kernel);
            const std::string added = done ? added_breach(kernel, known, kernel.violations()) : std::string();
            row.kept = done && row.after < row.before && added.empty();
            if (done && !added.empty()) row.action += "; refused: it adds " + added;
            if (!row.kept) {
                kernel.restore(snap);
                row.after = row.before;
            }
            rows.push_back(row);
            return row.kept;
        };
        bool done = false;
        for (const std::size_t mover : {next->other, next->part}) {
            if (problem.parts[mover].fixed) continue;
            std::map<std::string, std::size_t> blocked;
            done = attempt({"0", "connector access and envelope", subject, "slide " + problem.parts[mover].reference + " along its edge"},
                           [&] { return slide(kernel, mover, settings.pitch, clearing_reach(problem, next->part, next->other), blocked); });
            if (!done && !rows.empty()) {
                std::vector<std::pair<std::size_t, std::string>> ranked;
                for (const auto& [reason, count] : blocked) ranked.emplace_back(count, reason);
                std::sort(ranked.begin(), ranked.end(), [](const auto& a, const auto& b) {
                    return a.first != b.first ? a.first > b.first : a.second < b.second;
                });
                for (std::size_t index = 0; index < ranked.size() && index < stuck_rows; ++index)
                    rows.back().action += "; " + std::to_string(ranked[index].first) + " " + ranked[index].second;
            }
            if (done) break;
        }
        if (done) continue;
        for (const std::size_t mover : {next->other, next->part}) {
            if (problem.parts[mover].fixed) continue;
            std::map<std::string, std::size_t> blocked;
            const std::size_t peer = mover == next->other ? next->part : next->other;
            done = attempt({"1", "connector access and envelope", subject, "slide " + problem.parts[mover].reference + " with the parts tied to it"},
                           [&] { return slide_together(kernel, mover, peer, settings.pitch, clearing_reach(problem, next->part, next->other), blocked); });
            if (!done && !rows.empty()) {
                std::vector<std::pair<std::size_t, std::string>> ranked;
                for (const auto& [reason, count] : blocked) ranked.emplace_back(count, reason);
                std::sort(ranked.begin(), ranked.end(), [](const auto& a, const auto& b) {
                    return a.first != b.first ? a.first > b.first : a.second < b.second;
                });
                for (std::size_t index = 0; index < ranked.size() && index < stuck_rows; ++index)
                    rows.back().action += "; " + std::to_string(ranked[index].first) + " " + ranked[index].second;
            }
            if (done) break;
        }
        if (done) continue;
        for (const std::size_t mover : {next->other, next->part}) {
            if (problem.parts[mover].edge || problem.parts[mover].fixed) continue;
            const std::vector<std::size_t>& unit = clusters.units[clusters.unit_of[mover]];
            const std::string name = problem.parts[mover].reference;
            done = attempt({"3", "connector access and envelope", subject, "re-home the cluster of " + name},
                           [&] { return rehome(kernel, unit); }) ||
                   attempt({"4", "connector access and envelope", subject, "widen every side one step at a time and re-home the cluster of " + name}, [&] {
                       for (std::size_t step = 0; step < static_cast<std::size_t>(constants::widen_steps.value); ++step) {
                           for (const Side side : {Side::north, Side::south, Side::west, Side::east})
                               open_side(kernel, settings, side, settings.first_step);
                           if (rehome(kernel, unit)) return true;
                       }
                       return false;
                   });
            if (done) break;
        }
        if (done) continue;
        std::map<std::string, std::size_t> blocked;
        const bool opened = attempt({"4", "connector access and envelope", subject, "open the board between them and shift everything beyond the gap"},
                                    [&] { return open_gap(kernel, settings, clusters, next->part, next->other, blocked); });
        if (!opened && !rows.empty())
            for (const auto& [reason, count] : blocked) rows.back().action += "; " + std::to_string(count) + " " + reason;
    }
    return rows;
}

std::size_t shut_count(const Kernel& kernel) {
    const auto found = kernel.violations();
    return static_cast<std::size_t>(std::count_if(found.begin(), found.end(),
        [](const Violation& violation) { return violation.kind == Breach::plug_path; }));
}

bool turn_in_place(Kernel& kernel, std::size_t part) {
    const Pose from = kernel.placement()[part];
    const std::size_t shut = shut_count(kernel);
    for (int quarter = 1; quarter < turn_count; ++quarter) {
        Pose pose = from;
        pose.turn = combined(from.turn, static_cast<Turn>(quarter));
        if (kernel.rejection(part, pose)) continue;
        const Snapshot before = kernel.snapshot();
        if (!kernel.move(part, pose)) continue;
        if (shut_count(kernel) < shut) return true;
        kernel.restore(before);
    }
    return false;
}

bool shift_tied(Kernel& kernel, std::size_t part, std::size_t rival, const std::vector<Point>& offsets) {
    const Problem& problem = kernel.problem();
    std::vector<std::size_t> set{part};
    for (std::size_t index = 0; index < set.size(); ++index) {
        const auto follow = [&](const PadGap& tie) {
            if (tie.anchor == set[index] && tie.member != rival && !problem.parts[tie.member].fixed &&
                std::find(set.begin(), set.end(), tie.member) == set.end())
                set.push_back(tie.member);
        };
        for (const PadGap& tie : problem.constraints.pad_gaps) follow(tie);
        for (const PadGap& tie : problem.constraints.soft_gaps) follow(tie);
    }
    if (set.size() == 1) return false;
    const std::size_t shut = shut_count(kernel);
    for (const Point by : offsets) {
        if (by.x == 0 && by.y == 0) continue;
        std::vector<Move> moves;
        for (const std::size_t member : set) {
            Pose pose = kernel.placement()[member];
            pose.at = shifted(pose.at, by);
            moves.push_back({member, pose});
        }
        const Snapshot before = kernel.snapshot();
        if (!kernel.force(moves)) continue;
        const bool sound = std::none_of(set.begin(), set.end(), [&](std::size_t member) { return kernel.breach(member).has_value(); });
        if (sound && shut_count(kernel) < shut) return true;
        kernel.restore(before);
    }
    return false;
}

std::vector<RepairRow> clear_plug_paths(Kernel& kernel, const SqueezeOptions& settings, const Bundles& clusters) {
    const Problem& problem = kernel.problem();
    std::vector<RepairRow> rows;
    std::set<std::pair<std::size_t, std::size_t>> seen;
    const std::vector<Point> near = seat_ring(settings.pitch, static_cast<Nm>(constants::aside_reach.value), {0, 0});
    const std::vector<Point> wide = seat_ring(static_cast<Nm>(constants::far_pitch.value), static_cast<Nm>(constants::wide_reach.value), {0, 0});
    const char* const rule = "plug path";
    for (;;) {
        std::optional<Violation> next;
        for (const Violation& violation : kernel.violations())
            if (violation.kind == Breach::plug_path && seen.insert({violation.part, violation.other}).second) {
                next = violation;
                break;
            }
        if (!next) break;
        const std::size_t owner = next->part, blocker = next->other;
        const std::string subject = problem.parts[owner].reference +
            (blocker != owner ? " / " + problem.parts[blocker].reference : std::string());
        const auto attempt = [&](RepairRow row, const auto& step) {
            row.before = shut_count(kernel);
            const std::vector<Violation> known = kernel.violations();
            const Snapshot snap = kernel.snapshot();
            const bool done = step();
            row.after = shut_count(kernel);
            const std::string added = done ? added_breach(kernel, known, kernel.violations()) : std::string();
            row.kept = done && row.after < row.before && added.empty();
            if (done && !added.empty()) row.action += "; refused: it adds " + added;
            if (!row.kept) {
                kernel.restore(snap);
                row.after = row.before;
            }
            rows.push_back(row);
            return row.kept;
        };
        std::vector<std::size_t> movers;
        for (const std::size_t mover : {owner, blocker})
            if (std::find(movers.begin(), movers.end(), mover) == movers.end() && !problem.parts[mover].fixed &&
                !problem.parts[mover].corner)
                movers.push_back(mover);
        if (!problem.parts[owner].fixed && !problem.parts[owner].edge &&
            attempt({"0", rule, subject, "turn " + problem.parts[owner].reference + " where it stands"}, [&] { return turn_in_place(kernel, owner); }))
            continue;
        bool done = false;
        for (const std::size_t mover : movers) {
            if (problem.parts[mover].edge) continue;
            done = attempt({"2", rule, subject, "move " + problem.parts[mover].reference + " to the nearest legal seat"},
                           [&] { return steps_aside(kernel, mover, near) || steps_aside(kernel, mover, wide); });
            if (done) break;
        }
        if (done) continue;
        for (const std::size_t mover : movers) {
            if (problem.parts[mover].edge) continue;
            const std::size_t rival = mover == owner ? blocker : owner;
            done = attempt({"2", rule, subject, "move " + problem.parts[mover].reference + " with the parts tied to it"},
                           [&] { return shift_tied(kernel, mover, rival, near) || shift_tied(kernel, mover, rival, wide); });
            if (done) break;
        }
        if (done) continue;
        for (const std::size_t mover : movers) {
            if (problem.parts[mover].edge) continue;
            const std::vector<std::size_t>& unit = clusters.units[clusters.unit_of[mover]];
            const std::string name = problem.parts[mover].reference;
            done = attempt({"3", rule, subject, "re-home the cluster of " + name}, [&] { return rehome(kernel, unit); }) ||
                   attempt({"4", rule, subject, "widen every side one step at a time and re-home the cluster of " + name}, [&] {
                       for (std::size_t step = 0; step < static_cast<std::size_t>(constants::widen_steps.value); ++step) {
                           for (const Side side : {Side::north, Side::south, Side::west, Side::east})
                               open_side(kernel, settings, side, settings.first_step);
                           if (rehome(kernel, unit)) return true;
                       }
                       return false;
                   });
            if (done) break;
        }
    }
    return rows;
}

std::string convergence_text(const StageResult& result, std::size_t left) {
    std::ostringstream text;
    std::size_t kept = 0;
    for (const RepairRow& row : result.repairs) kept += row.kept ? 1 : 0;
    text << "CONVERGENCE: " << result.inherited << " breaches of staged rules (connector spacing, plug paths, face pairs, protection orders) handed over by the placer; "
         << kept << " repair steps kept of " << result.repairs.size() << " tried; " << left << " left\n"
         << "level | rule | subject | action | breaches before>after | kept\n";
    for (const RepairRow& row : result.repairs)
        text << row.level << " | " << row.rule << " | " << row.subject << " | " << row.action << " | " << row.before << ">"
             << row.after << " | " << (row.kept ? "yes" : "no") << "\n";
    return text.str();
}

}

std::string squeeze_summary(const SqueezeReport& report) {
    std::size_t kept = 0, relocated = 0, pushed = 0, sunk = 0, freed = 0, ejected = 0, rehomed = 0;
    std::map<std::string, std::string> stops;
    for (const auto& attempt : report.attempts) {
        if (attempt.kept) {
            ++kept;
            relocated += attempt.relocated;
            pushed += attempt.pushed;
            sunk += attempt.sunk;
            freed += attempt.freed;
            ejected += attempt.ejected;
            rehomed += attempt.rehomed;
        } else {
            stops[attempt.scaled ? (attempt.along_x ? "width" : "height") : side_name(attempt.side)] = attempt.blocker;
        }
    }
    const double before = to_mm(report.before.width) * to_mm(report.before.height);
    const double after = to_mm(report.after.width) * to_mm(report.after.height);
    std::ostringstream text;
    text << "LAYOUT SQUEEZE: " << to_mm(report.before.width) << " x " << to_mm(report.before.height) << " mm to "
         << to_mm(report.after.width) << " x " << to_mm(report.after.height) << " mm, area " << before << " to "
         << after << " mm2 (" << percent * (after - before) / before << "%)\n"
         << "  routed airwire " << to_mm(report.routed_before) << " to " << to_mm(report.routed_after) << " mm\n"
         << "  " << kept << " of " << report.attempts.size() << " edge steps kept, " << relocated
         << " relocations, " << pushed << " pushes, " << sunk << " parts sunk to the rear, " << freed << " jams freed (" << ejected
         << " by moving neighbours aside in a chain, " << rehomed
         << " by re-seating the cluster elsewhere on the board)\n";
    for (const auto& [side, blocker] : stops) text << "  " << side << " stopped by " << blocker << "\n";
    text << "  " << report.fallen << " cluster steps taken toward the module before the edges moved\n";
    if (!report.tried.empty()) {
        text << "  best of " << report.tried.size() << " edge orders, areas mm2:";
        for (const double area : report.tried) text << " " << area;
        text << "\n";
    }
    return text.str();
}

std::vector<RepairRow> legalise_rest(Kernel& kernel, const SqueezeOptions& settings) {
    const Problem& problem = kernel.problem();
    std::vector<RepairRow> rows;
    std::set<std::tuple<int, std::size_t, std::size_t>> seen;
    const std::vector<Point> near = seat_ring(settings.pitch, static_cast<Nm>(constants::aside_reach.value), {0, 0});
    const std::vector<Point> wide = seat_ring(static_cast<Nm>(constants::far_pitch.value), static_cast<Nm>(constants::wide_reach.value), {0, 0});
    for (;;) {
        std::optional<Violation> next;
        for (const Violation& violation : kernel.violations())
            if (violation.kind != Breach::connector_gap && violation.kind != Breach::plug_path &&
                seen.insert({static_cast<int>(violation.kind), std::min(violation.part, violation.other),
                             std::max(violation.part, violation.other)}).second) {
                next = violation;
                break;
            }
        if (!next) break;
        std::vector<std::size_t> movers{next->part};
        if (next->other != next->part && next->other < problem.parts.size()) movers.push_back(next->other);
        std::stable_sort(movers.begin(), movers.end(), [&](std::size_t a, std::size_t b) {
            return problem.parts[a].fanout_pins < problem.parts[b].fanout_pins;
        });
        const std::string subject = problem.parts[next->part].reference +
            (movers.size() > 1 ? " / " + problem.parts[next->other].reference : std::string());
        for (const std::size_t mover : movers) {
            if (problem.parts[mover].fixed || problem.parts[mover].corner || problem.parts[mover].edge) continue;
            RepairRow row{"2", std::string(breach_name(next->kind)), subject,
                          "move " + problem.parts[mover].reference + " to the nearest legal seat"};
            row.before = kernel.violations().size();
            const std::vector<Violation> known = kernel.violations();
            const Snapshot snap = kernel.snapshot();
            const bool done = steps_aside(kernel, mover, near) || steps_aside(kernel, mover, wide);
            row.after = kernel.violations().size();
            const std::string added = done ? added_breach(kernel, known, kernel.violations()) : std::string();
            row.kept = done && row.after < row.before && added.empty();
            if (done && !added.empty()) row.action += "; refused: it adds " + added;
            if (!row.kept) {
                kernel.restore(snap);
                row.after = row.before;
            }
            rows.push_back(row);
            if (row.kept) break;
        }
    }
    return rows;
}

void open_spacing(Kernel& kernel, const SqueezeOptions& settings, SpreadReport& report) {
    const auto closed = [&] {
        const auto found = kernel.violations();
        return static_cast<std::size_t>(std::count_if(found.begin(), found.end(),
            [](const Violation& violation) { return violation.kind == Breach::spacing; }));
    };
    for (const Part& part : kernel.problem().parts) report.widest = std::max(report.widest, part.spacing);
    report.before = report.after = kernel.board();
    report.closed_before = report.closed_after = closed();
    if (report.widest == 0) return;
    std::string blocker;
    for (;;) {
        for (std::size_t moved = separate(kernel, settings, Breach::spacing); moved > 0; moved = separate(kernel, settings, Breach::spacing))
            report.moved += moved;
        if (closed() > 0) legalise(kernel, settings, blocker);
        report.closed_after = closed();
        if (report.closed_after == 0 || report.rounds == static_cast<std::size_t>(constants::spread_rounds.value)) break;
        for (const Side side : {Side::north, Side::south, Side::west, Side::east}) open_side(kernel, settings, side, report.widest);
        ++report.rounds;
    }
    report.after = kernel.board();
    if (report.closed_after == 0) return;
    std::string left;
    std::size_t shown = 0;
    for (const Violation& violation : kernel.violations()) {
        if (violation.kind != Breach::spacing || ++shown > straggler_rows) continue;
        left += " " + kernel.problem().parts[violation.part].reference + "/" + kernel.problem().parts[violation.other].reference;
    }
    throw LayoutError("layout: " + std::to_string(report.closed_after) + " courtyard gaps asked for by the density setting are still closed after the outline was opened " +
                      std::to_string(report.rounds) + " times:" + left + "; first obstacle: " + blocker);
}

void repair_start(Kernel& kernel, const SqueezeOptions& settings, StageResult& result, const std::function<void(bool)>& mark) {
    const std::size_t gaps_inherited = gap_count(kernel) + shut_count(kernel);
    mark(false);
    result.repairs = separate_connectors(kernel, settings, bundle(kernel.problem()));
    mark(true);
    result.attract = attract(kernel, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
    result.order = lead_first(kernel, settings.pitch);
    std::vector<RepairRow> more = repair_inherited(kernel, settings, bundle(kernel.problem()), result.inherited);
    result.repairs.insert(result.repairs.end(), more.begin(), more.end());
    std::vector<RepairRow> rest = legalise_rest(kernel, settings);
    result.repairs.insert(result.repairs.end(), rest.begin(), rest.end());
    std::vector<RepairRow> paths = clear_plug_paths(kernel, settings, bundle(kernel.problem()));
    result.repairs.insert(result.repairs.end(), paths.begin(), paths.end());
    result.inherited += gaps_inherited;
}

StageResult squeeze_stage(const PcbPlacementInput& inputs, const PcbModel& model, const PcbEmitPolicy& policy,
                          const AdapterOptions& options, const SearchChoice& choice) {
    const PcbPlacementGatePolicy gates = pcb_placement_gate_policy(inputs);
    const ModelBinding binding = bind_model(model, policy, &gates, options);
    const Problem dense = without_density(binding.problem);
    Kernel attracted(dense, binding.placement);
    const auto rear = [](const Placement& placement) {
        return static_cast<std::size_t>(std::count_if(placement.begin(), placement.end(),
            [](const Pose& pose) { return pose.face == Face::bottom; }));
    };
    StageResult result;
    result.rear_before = rear(attracted.placement());
    SqueezeOptions settings = default_squeeze();
    settings.order = choice.order;
    settings.plan_skip = choice.plan_skip;
    const auto listed = [&](const char* when) {
        std::string text = std::string("ILLEGAL ") + when + ":";
        const Problem& entry = attracted.problem();
        std::size_t shown = 0;
        for (const Violation& violation : attracted.violations()) {
            if (++shown > straggler_rows) break;
            text += " " + std::string(breach_name(violation.kind)) + ":" + entry.parts[violation.part].reference + "/" +
                    (violation.other < entry.parts.size() ? entry.parts[violation.other].reference : "board");
        }
        return text + " (" + std::to_string(attracted.violations().size()) + ")\n";
    };
    std::string illegal_entry, illegal_separated;
    if (inputs.floorplan.project.construct) {
        result.construct = construct_owned(attracted, settings.pitch, static_cast<Nm>(constants::construct_reach.value), true);
        if (!result.construct->unseated.empty())
            throw LayoutError("layout: no seat by rule for some owned parts\n" + construct_summary(*result.construct));
    }
    repair_start(attracted, settings, result, [&](bool separated) { (separated ? illegal_separated : illegal_entry) = listed(separated ? "after connector separation" : "handed over"); });
    {
        const std::size_t left = unmet_count(attracted) + gap_count(attracted) + shut_count(attracted);
        result.convergence = (result.construct ? construct_summary(*result.construct) : std::string()) + convergence_text(result, left) + illegal_entry + illegal_separated + listed("after repair");
        const Problem& entry = attracted.problem();
        for (const PadGap& rule : entry.constraints.soft_gaps)
            if (rule.same_face && !pair_faced(entry, attracted.board(), rule.anchor, attracted.placement()[rule.anchor], rule.member,
                                              attracted.placement()[rule.member], rule.or_under))
                result.convergence += "LEFT " + entry.parts[rule.member].reference + " -> " + entry.parts[rule.anchor].reference +
                                      " (" + rule.source + ") on the other face: " + seat_obstacles(attracted, rule, settings.pitch) + "\n";
        for (const NetOrder& rule : net_orders_of(entry)) {
            if (net_order_met(entry, rule, attracted.placement(), rule.lead, nullptr)) continue;
            const auto at = [&](std::size_t part) {
                const Pose& pose = attracted.placement()[part];
                std::ostringstream out;
                out << entry.parts[part].reference << " at " << to_mm(pose.at.x) << "," << to_mm(pose.at.y)
                    << (pose.face == Face::top ? " top" : " rear") << ", "
                    << std::sqrt(static_cast<double>(squared_net_gap(entry, rule.anchor, attracted.placement()[rule.anchor], rule.anchor_names,
                                                                     part, pose, rule.net))) / static_cast<double>(to_nm(1.0))
                    << " mm from the pin";
                return out.str();
            };
            std::string text = "LEFT protection order: " + at(rule.lead) + "; nearer:";
            const Nm lead = squared_net_gap(entry, rule.anchor, attracted.placement()[rule.anchor], rule.anchor_names, rule.lead,
                                            attracted.placement()[rule.lead], rule.net);
            for (const std::size_t rival : rule.rivals)
                if (squared_net_gap(entry, rule.anchor, attracted.placement()[rule.anchor], rule.anchor_names, rival,
                                    attracted.placement()[rival], rule.net) < lead)
                    text += " " + at(rival) + (entry.parts[rival].fixed ? " (fixed)" : "") + ";";
            result.convergence += text + "\n";
        }
        for (const Violation& violation : attracted.violations())
            if (violation.kind == Breach::connector_gap)
                result.convergence += "LEFT connector spacing " + entry.parts[violation.part].reference + " / " +
                                      entry.parts[violation.other].reference + "\n";
        std::string shut;
        for (const Violation& violation : attracted.violations()) {
            if (violation.kind != Breach::plug_path) continue;
            const std::string line = entry.parts[violation.part].reference + " is entered through a path that " +
                                     (violation.other == violation.part ? std::string("leaves the board or runs into the module")
                                                                        : entry.parts[violation.other].reference + " stands in");
            result.convergence += "LEFT plug path: " + line + "\n";
            shut += "\n  " + line;
        }
        if (!shut.empty())
            throw LayoutError("layout: a plug path was handed over blocked and no turn, seat or cluster move clears it:" + shut + "\n" +
                              result.convergence);
        if (left > 0)
            throw LayoutError("layout: " + std::to_string(left) +
                              " face pairs or protection orders could not be repaired within the stated budget\n" + result.convergence);
    }
    Problem held = binding.problem;
    for (NetOrder& rule : net_orders_of(binding.problem))
        if (net_order_met(binding.problem, rule, attracted.placement(), rule.lead, nullptr))
            held.constraints.net_orders.push_back(std::move(rule));
    for (const PadGap& rule : binding.problem.constraints.soft_gaps)
        if (rule.same_face && pair_faced(binding.problem, attracted.board(), rule.anchor,
                                          attracted.placement()[rule.anchor], rule.member,
                                          attracted.placement()[rule.member], rule.or_under)) {
            held.constraints.face_pairs.push_back({rule.anchor, rule.member, "face of " + rule.source, rule.or_under});
            ++result.faced;
        } else if (rule.same_face) {
            ++result.unfaced;
        }
    tighten_holds(held, attracted.placement(), hold_policy());
    held.rules.tall_module_clearance = to_nm(constants::tall_module_clearance.value);
    Kernel kernel(held, attracted.placement());
    kernel.set_board(attracted.board());
    open_spacing(kernel, settings, result.spread);
    const Bundles clusters = bundle(held);
    for (const Violation& crowding : kernel.violations()) {
        if (crowding.kind != Breach::module_core) continue;
        if (!kernel.breach(crowding.part)) continue;
        if (!rehome(kernel, clusters.units[clusters.unit_of[crowding.part]]))
            throw LayoutError("layout: " + held.parts[crowding.part].reference +
                              " is taller than the module's underside and no place clears the module by the tall-part margin");
        ++result.cleared;
    }
    const auto area = [](const SqueezeReport& report) {
        return to_mm(report.after.width) * to_mm(report.after.height);
    };
    if (inputs.floorplan.project.arrange) result.arrange = arrange(kernel, settings);
    const Snapshot seated = kernel.snapshot();
    SqueezeReport plain = squeeze_best(kernel, settings);
    const Snapshot plain_state = kernel.snapshot();
    const Nm sink_reach = static_cast<Nm>(constants::sink_reach.value);
    const auto smaller = [&](const SqueezeReport& one, const SqueezeReport& other) {
        return area(one) < area(other) || (area(one) == area(other) && one.routed_after < other.routed_after);
    };
    std::optional<SqueezeReport> balanced;
    std::optional<Snapshot> balanced_state;
    std::vector<Placement> starts;
    for (const BalanceScope scope : {BalanceScope::mirrored, BalanceScope::anywhere}) {
        kernel.restore(seated);
        BalanceTrial trial{scope, balance_faces(kernel, settings.pitch, sink_reach, scope)};
        const bool repeats = std::find(starts.begin(), starts.end(), kernel.placement()) != starts.end();
        if (trial.balance.flipped != 0 && !repeats) {
            starts.push_back(kernel.placement());
            SqueezeReport squeezed = squeeze_best(kernel, settings);
            trial.area = area(squeezed);
            trial.squeezed = true;
            if (!balanced || smaller(squeezed, *balanced)) {
                balanced = std::move(squeezed);
                balanced_state = kernel.snapshot();
                for (BalanceTrial& earlier : result.trials) earlier.kept = false;
                trial.kept = true;
            }
        }
        result.trials.push_back(std::move(trial));
    }
    result.plain_area = area(plain);
    result.balanced_area = balanced ? area(*balanced) : result.plain_area;
    result.balanced = balanced && smaller(*balanced, plain);
    if (!result.balanced)
        for (BalanceTrial& trial : result.trials) trial.kept = false;
    kernel.restore(result.balanced ? *balanced_state : plain_state);
    result.squeeze = result.balanced ? std::move(*balanced) : std::move(plain);
    for (const BalanceTrial& trial : result.trials) {
        if (trial.kept || (!result.balanced && trial.scope == BalanceScope::anywhere)) result.balance = trial.balance;
        if (trial.scope == BalanceScope::anywhere) result.left_on_top = trial.balance.kept_on_top;
    }
    for (bool improved = true; improved;) {
        improved = false;
        std::optional<Placement> tried;
        for (const BalanceScope scope : {BalanceScope::anywhere, BalanceScope::mirrored}) {
            const Snapshot squeezed = kernel.snapshot();
            const BalanceReport again = balance_faces(kernel, settings.pitch, sink_reach, scope);
            if (scope == BalanceScope::anywhere) result.left_on_top = again.kept_on_top;
            if (again.flipped == 0) continue;
            if (tried && *tried == kernel.placement()) {
                kernel.restore(squeezed);
                continue;
            }
            tried = kernel.placement();
            SqueezeReport next = squeeze_best(kernel, settings);
            Rebalance pass{again, area(result.squeeze), area(next), area(next) < area(result.squeeze), scope};
            result.rebalances.push_back(pass);
            if (!pass.kept) {
                kernel.restore(squeezed);
                continue;
            }
            result.squeeze.after = next.after;
            result.squeeze.routed_after = next.routed_after;
            result.squeeze.fallen += next.fallen;
            result.squeeze.attempts.insert(result.squeeze.attempts.end(), next.attempts.begin(), next.attempts.end());
            improved = true;
            break;
        }
    }
    result.reseat = attract(kernel, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
    result.rear_after = rear(kernel.placement());
    kernel.verify();
    if (!kernel.violations().empty() || !kernel.outline_holds())
        throw LayoutError("layout: the squeeze left an illegal placement");
    result.model = model_with(model, binding, kernel.placement(), kernel.board());
    std::vector<Box> fields;
    for (const auto& reserve : bind_model(result.model, policy, nullptr, options).problem.reserves)
        fields.push_back(reserve.box);
    if (ordered(fields) != ordered(kernel.reserves()))
        throw LayoutError("layout: thermal fields did not follow their parts");
    std::size_t holds = 0;
    Nm held_before = 0, held_after = 0;
    for (const auto& rule : held.constraints.pad_gaps) {
        if (!rule.derived || !rule.rigid) continue;
        ++holds;
        held_before = std::max(held_before, pad_gap_length(held, rule, binding.placement));
        held_after = std::max(held_after, pad_gap_length(held, rule, kernel.placement()));
    }
    std::map<std::string, std::size_t> ties;
    for (const auto& entry : binding.problem.ownership)
        if (entry.tie != Tie::none) ++ties[tie_name(entry.tie)];
    std::size_t reached_before = 0, reached_after = 0;
    for (const auto& rule : binding.problem.constraints.soft_gaps) {
        if (pad_gap_length(binding.problem, rule, binding.placement) <= rule.reach) ++reached_before;
        if (pad_gap_length(binding.problem, rule, kernel.placement()) <= rule.reach) ++reached_after;
    }
    std::vector<std::pair<Nm, std::size_t>> stragglers;
    for (std::size_t index = 0; index < binding.problem.constraints.soft_gaps.size(); ++index) {
        const auto& rule = binding.problem.constraints.soft_gaps[index];
        const Nm gap = pad_gap_length(binding.problem, rule, kernel.placement());
        if (gap > rule.reach) stragglers.emplace_back(gap, index);
    }
    std::sort(stragglers.begin(), stragglers.end(), [](const auto& a, const auto& b) {
        return a.first != b.first ? a.first > b.first : a.second < b.second;
    });
    std::ostringstream text;
    text << "SAME FACE: " << result.faced << " parts held on the face of the pin they serve (regulator loops, timing parts); "
         << result.unfaced << " could not be brought to that face\n";
    text << "PROTECTION ORDER: " << result.order.met_after << " of " << result.order.wanted
         << " protection parts are the first part on their net after the connector pin and are held so; "
         << result.order.reseated << " were moved nearer to become so, and "
         << result.order.moved_back << " parts ahead of one were moved back\n";
    text << "TALL PARTS: " << result.cleared << " clusters moved to give parts taller than the module's underside "
         << constants::tall_module_clearance.value << " mm from the module\n";
    text << "CLUSTER ARRANGEMENT: " << result.arrange.clusters << " tied clusters; parts and module span "
         << to_mm(result.arrange.before.width()) << " x " << to_mm(result.arrange.before.height())
         << " mm as placed; squeezes to " << result.arrange.unarranged << " mm2 without rearranging\n";
    for (std::size_t index = 0; index < result.arrange.plans.size(); ++index) {
        const ArrangePlan& plan = result.arrange.plans[index];
        text << (index + 1 == result.arrange.chosen ? "  TAKEN " : "        ") << "keep " << plan.kept_sides << ": span "
             << to_mm(plan.span.width()) << " x " << to_mm(plan.span.height()) << " mm, " << plan.moved
             << " clusters moved after opening " << to_mm(plan.widened) << " mm on the kept sides, " << plan.tightened
             << " tightening moves";
        if (plan.squeezed > 0) text << ", squeezes to " << plan.squeezed << " mm2";
        text << ", " << plan.stuck.size() << " could not leave";
        for (std::size_t stuck = 0; stuck < plan.stuck.size() && stuck < stuck_rows; ++stuck)
            text << (stuck ? ", " : ": ") << plan.stuck[stuck];
        text << "\n";
    }
    text << "  span of the taken arrangement is held by: " << result.arrange.holders << "\n"
         << "  sides that cannot be cleared because a fixed or edge-bound cluster sits there: "
         << (result.arrange.anchored_sides.empty() ? "none" : result.arrange.anchored_sides) << "\n"
         << "  arranging took " << result.arrange.plan_seconds << " s for " << result.arrange.plans.size()
         << " plans and " << result.arrange.squeeze_seconds << " s to squeeze the finalists\n";
    text << "OWNERSHIP:";
    for (const auto& [tie, parts] : ties) text << " " << parts << " " << tie;
    text << "; " << binding.unresolved.size() << " off-sheet owners not found\n"
         << "  parts within reach of the pin they serve: " << reached_before << " to " << reached_after << " of "
         << binding.problem.constraints.soft_gaps.size() << "\n";
    for (std::size_t index = 0; index < stragglers.size() && index < straggler_rows; ++index) {
        const auto& rule = binding.problem.constraints.soft_gaps[stragglers[index].second];
        text << "    " << binding.problem.parts[rule.member].reference << " is " << to_mm(stragglers[index].first)
             << " mm from " << binding.problem.parts[rule.anchor].reference << " (reach " << to_mm(rule.reach) << " mm): "
             << seat_obstacles(kernel, rule, settings.pitch) << "\n";
    }
    text << "OWNER HOLDS: " << holds << " small parts held to the pin they serve; farthest " << to_mm(held_before)
         << " mm before, " << to_mm(held_after) << " mm after\n";
    text << "OWNER ATTRACTION: " << result.attract.wanted << " parts wanted a seat at the pin they serve, "
         << result.attract.seated << " seated (" << result.attract.to_rear << " to the rear, "
         << result.attract.moved_aside << " blockers moved aside, " << result.attract.together
         << " seated together with the parts they are tied to, " << result.attract.far_seated
         << " took the nearest room beyond the first search); preferences met "
         << result.attract.met_before << " to " << result.attract.met_after << " of "
         << binding.problem.constraints.soft_gaps.size() << "\n"
         << "  routed airwire " << to_mm(result.attract.routed_before) << " to "
         << to_mm(result.attract.routed_after) << " mm\n";
    const auto scope_name = [](BalanceScope scope) {
        return scope == BalanceScope::mirrored ? "mirrored in place only" : "with seats away from the mirrored place, exchanges and releases";
    };
    text << "FACE BALANCE: " << result.balance.flipped << " of " << result.balance.sets
         << " movable clusters mirrored to the rear (" << result.balance.parts << " parts); courtyard area top "
         << result.balance.top_before << " to " << result.balance.top_after << " mm2, rear "
         << result.balance.rear_before << " to " << result.balance.rear_after << " mm2\n"
         << "  " << result.balance.shifted << " clusters took a rear seat away from their mirrored place, "
         << result.balance.exchanged << " changed faces together with the parts in their way, " << result.balance.risen
         << " parts came up to the top in exchange, " << result.balance.released
         << " face-bound parts were released from a copper field that went to the rear\n";
    for (const BalanceTrial& trial : result.trials) {
        text << "  tried " << scope_name(trial.scope) << ": " << trial.balance.flipped << " clusters (" << trial.balance.parts
             << " parts down, " << trial.balance.risen << " up)";
        if (trial.squeezed) text << ", squeezes to " << trial.area << " mm2";
        else text << (trial.balance.flipped == 0 ? ", nothing moved" : ", the same placement as the trial before it");
        text << (trial.kept ? "; KEPT" : "") << "\n";
    }
    text << "  squeezed area with mirroring " << result.balanced_area << " mm2, without " << result.plain_area
         << " mm2; kept the " << (result.balanced ? "mirrored" : "unmirrored") << " board\n";
    for (const Rebalance& pass : result.rebalances)
        text << "  on the squeezed board, " << scope_name(pass.scope) << ": " << pass.balance.flipped << " of " << pass.balance.sets
             << " movable clusters mirrored to the rear (" << pass.balance.parts << " parts, " << pass.balance.shifted
             << " away from their mirrored place, " << pass.balance.exchanged << " exchanged, " << pass.balance.risen
             << " parts up, " << pass.balance.released << " released); squeezed again "
             << pass.before << " to " << pass.after << " mm2; " << (pass.kept ? "kept" : "discarded") << "\n";
    {
        std::vector<std::pair<double, std::string>> left = result.left_on_top;
        std::stable_sort(left.begin(), left.end(), [](const auto& a, const auto& b) { return a.first > b.first; });
        text << "  rear-capable courtyard left on top when last examined, largest clusters:\n";
        for (std::size_t index = 0; index < left.size() && index < straggler_rows; ++index)
            text << "    " << left[index].first << " mm2 " << left[index].second << "\n";
    }
    text << squeeze_summary(result.squeeze) << "RESEAT AFTER SQUEEZE: " << result.reseat.wanted
         << " parts had drifted from the pin they serve, " << result.reseat.seated << " reseated ("
         << result.reseat.to_rear << " to the rear, " << result.reseat.far_seated
         << " to the nearest room beyond the first search); preferences met " << result.reseat.met_before << " to "
         << result.reseat.met_after << "\n"
         << "FACES: top "
         << binding.placement.size() - result.rear_before << " to " << binding.placement.size() - result.rear_after
         << ", rear " << result.rear_before << " to " << result.rear_after << "\n";
    for (const Side side : {Side::north, Side::south, Side::west, Side::east}) {
        const bool along_x = side == Side::north || side == Side::south;
        std::vector<std::pair<Nm, std::size_t>> row;
        Nm bodies = 0;
        for (std::size_t part = 0; part < held.parts.size(); ++part) {
            const Part& item = held.parts[part];
            if (!item.edge || facing(item, kernel.placement()[part]) != side) continue;
            const Box gate = gate_at(held, part, kernel.placement()[part]);
            row.emplace_back(along_x ? gate.x0 : gate.y0, part);
            bodies += along_x ? gate.width() : gate.height();
        }
        std::sort(row.begin(), row.end());
        const Nm length = along_x ? kernel.board().width : kernel.board().height;
        text << "EDGE " << side_name(side) << ": " << to_mm(length) << " mm long, connector bodies " << to_mm(bodies)
             << " mm (" << percent * static_cast<double>(bodies) / static_cast<double>(length) << "%):";
        for (const auto& [at, part] : row) text << " " << held.parts[part].reference;
        text << "\n";
    }
    {
        const std::size_t count = held.parts.size();
        std::vector<std::size_t> lead(count);
        for (std::size_t part = 0; part < count; ++part) lead[part] = part;
        const auto root = [&](std::size_t part) {
            while (lead[part] != part) part = lead[part] = lead[lead[part]];
            return part;
        };
        for (const auto& pair : held.constraints.face_pairs) lead[root(pair.first)] = root(pair.second);
        std::vector<char> pinned(count, 0);
        for (std::size_t part = 0; part < count; ++part) {
            const Part& item = held.parts[part];
            if (item.fixed || item.top_only || !held.footprints[item.footprint].flippable) pinned[root(part)] = 1;
        }
        const auto kind_of = [](const Part& item) -> const char* {
            if (!item.part_class) throw LayoutError("layout: " + item.reference + " carries no part class");
            switch (*item.part_class) {
            case PartClass::test_point: return "top-only test points";
            case PartClass::led: return "top-only LEDs";
            case PartClass::control_switch: return "top-only switches";
            case PartClass::connector:
            case PartClass::header:
            case PartClass::module_connector: return "top-only connectors and headers";
            case PartClass::battery_holder: return "top-only battery holder";
            case PartClass::resistor:
            case PartClass::capacitor:
            case PartClass::inductor:
            case PartClass::ferrite:
            case PartClass::transformer:
            case PartClass::diode:
            case PartClass::transistor:
            case PartClass::integrated_circuit:
            case PartClass::crystal:
            case PartClass::mounting_hole:
            case PartClass::fiducial: return "top-only parts on controlled nets or with through holes";
            }
            throw LayoutError("layout: " + item.reference + " has a part class with no face reason");
        };
        std::map<std::string, double> top;
        double rear = 0;
        for (std::size_t part = 0; part < count; ++part) {
            const Part& item = held.parts[part];
            const Box gate = gate_at(held, part, kernel.placement()[part]);
            const double area = to_mm(gate.width()) * to_mm(gate.height());
            if (kernel.placement()[part].face == Face::bottom) {
                rear += area;
                continue;
            }
            const char* why = item.edge ? "edge connectors"
                              : item.fixed ? "fixed parts"
                              : item.top_only ? kind_of(item)
                              : !held.footprints[item.footprint].flippable ? "parts that cannot be mirrored"
                              : pinned[root(part)] ? "parts tied to the face of a top-bound part"
                              : "parts free to go to the rear";
            top[why] += area;
        }
        text << "TOP FACE courtyard area by reason (rear holds " << rear << " mm2):\n";
        for (const auto& [why, area] : top) text << "    " << area << " mm2 " << why << "\n";
    }
    const PlacementIntegrityResult final_rules = check_placement_integrity(PcbCheckInput(result.model), result.model, options.intent);
    text << final_rules.summary(rules::Stage::layout);
    if (!final_rules.ok_at(rules::Stage::layout))
        throw LayoutError("layout: the final state breaches staged rules; not emitted\n" + result.convergence +
                          final_rules.summary(rules::Stage::layout));
    const std::vector<std::string> provenance =
        breach_provenance(check_placement_integrity(PcbCheckInput(model), model, options.intent), final_rules,
                          "the placer", "the layout stage");
    if (!provenance.empty()) {
        text << "BREACH PROVENANCE (gate rules breached after the last step):\n";
        for (const std::string& line : provenance) text << "    " << line << "\n";
    }
    result.report = text.str();
    std::ostringstream density;
    density << density_report(held, kernel.placement(), options.density);
    if (result.spread.widest > 0)
        density << "OPENING: " << result.spread.closed_before << " gaps were closed in the placement handed over; " << result.spread.moved
                << " cluster moves opened them, and the outline was opened " << result.spread.rounds << " times by "
                << to_mm(result.spread.widest) << " mm a side, from "
                << to_mm(result.spread.before.width) << " x " << to_mm(result.spread.before.height) << " mm to "
                << to_mm(result.spread.after.width) << " x " << to_mm(result.spread.after.height) << " mm, before the squeeze closed it to "
                << to_mm(kernel.board().width) << " x " << to_mm(kernel.board().height) << " mm\n";
    result.density = density.str();
    return result;
}

}
