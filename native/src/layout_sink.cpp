#include "schgen/layout_sink.hpp"
#include "schgen/layout_squeeze.hpp"

#include "schgen/roles.hpp"

#include <sstream>
#include <algorithm>
#include <limits>
#include <map>

namespace schgen::layout {
namespace {

std::vector<Box> named_boxes(const Problem& problem, std::size_t part, const Pose& pose,
                             const std::vector<std::size_t>& names) {
    const Variant& variant = problem.footprints[problem.parts[part].footprint].on(pose.face);
    std::vector<Box> boxes;
    if (names.empty())
        for (const auto& box : variant.name_boxes) boxes.push_back(placed(box, pose.at, pose.turn));
    else
        for (const std::size_t name : names) boxes.push_back(placed(variant.name_boxes[name], pose.at, pose.turn));
    return boxes;
}

}

std::vector<Point> seat_ring(Nm pitch, Nm reach, Point preferred) {
    std::vector<Point> offsets;
    const Nm count = reach / pitch;
    for (Nm column = -count; column <= count; ++column)
        for (Nm row = -count; row <= count; ++row)
            if (squared(column) + squared(row) <= squared(count)) offsets.push_back({column * pitch, row * pitch});
    std::sort(offsets.begin(), offsets.end(), [&](Point a, Point b) {
        const Nm far_a = squared(a.x) + squared(a.y), far_b = squared(b.x) + squared(b.y);
        if (far_a != far_b) return far_a < far_b;
        const Nm along_a = a.x * preferred.x + a.y * preferred.y, along_b = b.x * preferred.x + b.y * preferred.y;
        if (along_a != along_b) return along_a > along_b;
        return a.x != b.x ? a.x < b.x : a.y < b.y;
    });
    return offsets;
}

bool may_sink(const Problem& problem, const Placement& placement, std::size_t part) {
    const Part& item = problem.parts[part];
    const Footprint& footprint = problem.footprints[item.footprint];
    return !item.fixed && !item.top_only && footprint.flippable && placement[part].face == Face::top;
}

bool crowds_escape(const Problem& problem, const Placement& placement, std::size_t part, const Pose& pose) {
    const Box gate = gate_at(problem, part, pose);
    for (std::size_t other = 0; other < problem.parts.size(); ++other) {
        const Part& subject = problem.parts[other];
        if (other == part || !subject.fanout_subject || placement[other].face == pose.face) continue;
        if (!counts_as_crowder(problem.parts[part], subject)) continue;
        const Box body = gate_at(problem, other, placement[other]);
        if (!inside(gate, body) && !gap_at_least(gate, body, subject.fanout_need)) return true;
    }
    return false;
}

bool sink_part(Kernel& kernel, std::size_t part, const std::vector<Point>& offsets) {
    const Problem& problem = kernel.problem();
    if (!may_sink(problem, kernel.placement(), part)) return false;
    const Pose from = kernel.placement()[part];
    const bool mounted = problem.parts[part].edge.has_value();
    for (const Point by : offsets)
        for (const Turn turn : {from.turn, combined(from.turn, Turn::half)}) {
            if (turn != from.turn && !mounted) continue;
            const Pose pose{shifted(from.at, by), turn, Face::bottom};
            if (crowds_escape(problem, kernel.placement(), part, pose)) continue;
            if (kernel.move_many({{part, pose}})) return true;
        }
    return false;
}

namespace {

struct FaceTie {
    std::size_t first = 0, second = 0;
    std::string source;
};

const char* pinned_as(const Problem& problem, std::size_t part) {
    const Part& item = problem.parts[part];
    const Footprint& footprint = problem.footprints[item.footprint];
    if (item.fixed) return "fixed";
    if (item.top_only) return "top-only";
    if (!footprint.flippable) return "unmirrorable";
    if (!mirrors_across_x(footprint)) return "axis-less";
    return nullptr;
}

std::vector<FaceTie> face_ties(const Kernel& kernel, const std::vector<char>& leaves, bool wide) {
    const Problem& problem = kernel.problem();
    std::vector<FaceTie> ties;
    for (const auto& rule : problem.constraints.nearest_gaps)
        if (rule.same_face)
            for (const std::size_t member : rule.members) ties.push_back({rule.anchor, member, rule.source});
    for (const auto& rule : problem.constraints.face_pairs) {
        const bool held = pinned_as(problem, rule.first) || pinned_as(problem, rule.second);
        if (!wide || !rule.or_under || !held) ties.push_back({rule.first, rule.second, rule.source});
    }
    for (const auto& reserve : problem.reserves) {
        std::optional<std::size_t> hub;
        for (const std::size_t member : reserve.members) {
            if (kernel.movable_alone(member) || leaves[member]) continue;
            if (hub) ties.push_back({*hub, member, "copper field " + reserve.source});
            else hub = member;
        }
    }
    return ties;
}

std::string held_by(const Problem& problem, const Placement& placement, const std::vector<std::size_t>& members,
                    const std::vector<FaceTie>& ties) {
    const auto name = [&](std::size_t part) { return problem.parts[part].reference; };
    std::vector<std::size_t> waiting, pinned, sunk;
    for (const std::size_t part : members) {
        if (pinned_as(problem, part)) pinned.push_back(part);
        else if (placement[part].face == Face::bottom) sunk.push_back(part);
        else waiting.push_back(part);
    }
    if (waiting.empty()) return name(members.front()) + ": no part on top is free to change face";
    const std::vector<std::size_t>& holders = pinned.empty() ? sunk : pinned;
    const auto holds = [&](std::size_t part) { return std::find(holders.begin(), holders.end(), part) != holders.end(); };
    struct Step {
        std::size_t from = 0;
        const FaceTie* tie = nullptr;
    };
    std::map<std::size_t, Step> came;
    std::vector<std::size_t> queue{waiting.front()};
    came[waiting.front()] = {};
    std::optional<std::size_t> holder;
    for (std::size_t index = 0; !holder && index < queue.size(); ++index) {
        const std::size_t at = queue[index];
        if (holds(at)) {
            holder = at;
            break;
        }
        for (const FaceTie& tie : ties) {
            if (tie.first != at && tie.second != at) continue;
            const std::size_t next = tie.first == at ? tie.second : tie.first;
            if (came.count(next)) continue;
            came[next] = {at, &tie};
            queue.push_back(next);
        }
    }
    std::string text = name(waiting.front());
    if (waiting.size() > 1) text += " and " + std::to_string(waiting.size() - 1) + " more";
    if (!holder) return text + ": tied to no part that holds a face";
    text += pinned.empty() ? ": on top while " + name(*holder) : ": held on top by " + std::string(pinned_as(problem, *holder)) + " " + name(*holder);
    if (pinned.empty()) {
        if (sunk.size() > 1) text += " and " + std::to_string(sunk.size() - 1) + " more";
        text += " of the same cluster already on the rear";
    }
    std::vector<std::string> chain;
    for (std::size_t at = *holder; came[at].tie; at = came[at].from)
        chain.push_back(came[at].tie->source + " (" + name(came[at].from) + " to " + name(at) + ")");
    for (auto link = chain.rbegin(); link != chain.rend(); ++link)
        text += (link == chain.rbegin() ? "; tied through " : ", then ") + *link;
    return text;
}

}

BalanceReport balance_faces(Kernel& kernel, Nm pitch, Nm reach, BalanceScope scope) {
    const Problem& problem = kernel.problem();
    const bool wide = scope == BalanceScope::anywhere;
    const std::size_t count = problem.parts.size();
    std::vector<char> face_tied(count, 0), leaves(count, 0);
    for (const auto& rule : problem.constraints.nearest_gaps)
        if (rule.same_face) {
            face_tied[rule.anchor] = 1;
            for (const std::size_t member : rule.members) face_tied[member] = 1;
        }
    for (const auto& rule : problem.constraints.face_pairs) face_tied[rule.first] = face_tied[rule.second] = 1;
    for (std::size_t part = 0; part < count; ++part)
        leaves[part] = wide && pinned_as(problem, part) && !face_tied[part] && !kernel.movable_alone(part) &&
                       kernel.releasable(part);
    const std::vector<FaceTie> ties = face_ties(kernel, leaves, wide);
    const auto leavers_of = [&](const std::vector<std::size_t>& members) {
        std::vector<std::size_t> out;
        for (const auto& reserve : problem.reserves) {
            const bool shared = std::any_of(reserve.members.begin(), reserve.members.end(), [&](std::size_t member) {
                return !leaves[member] && !kernel.movable_alone(member) &&
                       std::find(members.begin(), members.end(), member) != members.end();
            });
            if (!shared) continue;
            for (const std::size_t member : reserve.members)
                if (leaves[member] && !kernel.movable_alone(member) && std::find(out.begin(), out.end(), member) == out.end())
                    out.push_back(member);
        }
        return out;
    };
    const auto released = [&](const std::vector<std::size_t>& members) {
        std::size_t freed = 0;
        for (const std::size_t part : leavers_of(members))
            if (kernel.release(part)) ++freed;
        return freed;
    };
    std::vector<std::size_t> parent(count);
    for (std::size_t part = 0; part < count; ++part) parent[part] = part;
    const auto root = [&](std::size_t part) {
        while (parent[part] != part) part = parent[part] = parent[parent[part]];
        return part;
    };
    for (const FaceTie& tie : ties) {
        const std::size_t a = root(tie.first), b = root(tie.second);
        if (a != b) parent[std::max(a, b)] = std::min(a, b);
    }
    std::vector<std::vector<std::size_t>> sets(count);
    for (std::size_t part = 0; part < count; ++part) sets[root(part)].push_back(part);
    BalanceReport report;
    const auto face_area = [&](Face face) {
        double total = 0;
        for (std::size_t part = 0; part < count; ++part)
            if (kernel.placement()[part].face == face) total += area_mm2(gate_at(problem, part, kernel.placement()[part]));
        return total;
    };
    report.top_before = face_area(Face::top);
    report.rear_before = face_area(Face::bottom);
    double top = report.top_before, rear = report.rear_before;
    const auto free_set = [&](const std::vector<std::size_t>& members) {
        return std::none_of(members.begin(), members.end(), [&](std::size_t part) { return pinned_as(problem, part) != nullptr; });
    };
    const auto gain_of = [&](const std::vector<std::size_t>& members) {
        double gain = 0;
        for (const std::size_t part : members) {
            const double area = area_mm2(gate_at(problem, part, kernel.placement()[part]));
            gain += kernel.placement()[part].face == Face::top ? area : -area;
        }
        return gain;
    };
    struct Candidate {
        std::size_t lead = 0;
        double area = 0;
    };
    std::vector<Candidate> candidates;
    for (std::size_t lead = 0; lead < count; ++lead) {
        const auto& members = sets[lead];
        if (members.empty()) continue;
        const bool straddles = std::any_of(members.begin(), members.end(), [&](std::size_t part) {
            return kernel.placement()[part].face == Face::bottom;
        });
        if (!free_set(members) || (!wide && straddles)) {
            double area = 0;
            for (const std::size_t part : members)
                if (kernel.placement()[part].face == Face::top && !pinned_as(problem, part))
                    area += area_mm2(gate_at(problem, part, kernel.placement()[part]));
            if (area > 0) report.kept_on_top.emplace_back(area, held_by(problem, kernel.placement(), members, ties));
            continue;
        }
        const double gain = gain_of(members);
        if (gain > 0) candidates.push_back({lead, gain});
    }
    std::stable_sort(candidates.begin(), candidates.end(),
                     [](const Candidate& a, const Candidate& b) { return a.area > b.area; });
    report.sets = candidates.size();
    const std::vector<Point> near = seat_ring(pitch, reach, {0, 0});
    const std::vector<Point> far = seat_ring(static_cast<Nm>(constants::far_pitch.value),
                                             static_cast<Nm>(constants::balance_reach.value), {0, 0});
    struct Frame {
        bool about_x = true;
        Turn turn = Turn::none;
    };
    const auto frames_of = [&](const std::vector<std::size_t>& members) {
        std::size_t along_x = 0, along_y = 0;
        for (const std::size_t part : members) {
            const Part& item = problem.parts[part];
            if (!item.edge) continue;
            const Pose& pose = kernel.placement()[part];
            (turned(item.edge->mouth_on(pose.face), pose.turn).x != 0 ? along_x : along_y) += 1;
        }
        std::vector<Frame> frames;
        if (along_x != 0 && along_y != 0) return frames;
        if (along_x != 0 || along_y != 0) {
            frames.push_back({along_x == 0, Turn::none});
            return frames;
        }
        for (const Turn turn : {Turn::none, Turn::quarter})
            for (const bool about_x : {true, false}) frames.push_back({about_x, turn});
        return frames;
    };
    const auto swapped = [&](const std::vector<std::size_t>& members, const Frame& frame) {
        const Box hull = hull_at(problem, kernel.placement(), members);
        const Nm pivot = frame.about_x ? hull.x0 + hull.x1 : hull.y0 + hull.y1;
        const Point centre{(hull.x0 + hull.x1) / 2, (hull.y0 + hull.y1) / 2};
        std::vector<Move> moves;
        for (const std::size_t part : members) {
            const Pose& from = kernel.placement()[part];
            const bool across_x = *mirrors_across_x(problem.footprints[problem.parts[part].footprint]);
            const int back = (turn_count - static_cast<int>(from.turn) + (across_x == frame.about_x ? 0 : 2)) % turn_count;
            const Point at = frame.about_x ? Point{pivot - from.at.x, from.at.y} : Point{from.at.x, pivot - from.at.y};
            const Point arm{at.x - centre.x, at.y - centre.y};
            moves.push_back({part, {shifted(centre, turned(arm, frame.turn)), combined(static_cast<Turn>(back), frame.turn),
                                    opposite(from.face)}});
        }
        return moves;
    };
    const auto crowding = [&](const std::vector<Move>& moves) {
        return std::any_of(moves.begin(), moves.end(), [&](const Move& move) {
            return crowds_escape(problem, kernel.placement(), move.part, move.pose);
        });
    };
    const auto in_place = [&](const std::vector<std::size_t>& members, const std::string& lead, std::string& why) {
        const std::vector<Frame> frames = frames_of(members);
        if (frames.empty()) {
            why = lead + ": edge parts face both axes";
            return false;
        }
        const std::vector<Move> mirror = swapped(members, frames.front());
        std::map<std::string, std::size_t> blocked;
        std::size_t sampled = 0;
        for (const Point by : near) {
            std::vector<Move> moves = mirror;
            for (auto& move : moves) move.pose.at = shifted(move.pose.at, by);
            if (crowding(moves)) {
                ++blocked["crowds an escape on the other face"];
                continue;
            }
            if (kernel.move_many(moves)) return true;
            if (sampled++ >= static_cast<std::size_t>(constants::balance_samples.value)) continue;
            const Snapshot before = kernel.snapshot();
            if (!kernel.force(moves)) {
                ++blocked["a copper field that cannot change face"];
            } else {
                for (const std::size_t part : members)
                    if (const auto found = kernel.breach(part)) {
                        const std::size_t other = found->part == part ? found->other : found->part;
                        const bool peer = other != part && other < count;
                        ++blocked[std::string(breach_name(found->kind)) + " " + problem.parts[part].reference + "/" +
                                  (!peer ? "board"
                                         : problem.parts[other].reference +
                                               (kernel.placement()[other].face == Face::bottom ? " on the rear" : " on top"))];
                        break;
                    }
            }
            kernel.restore(before);
        }
        std::vector<std::pair<std::size_t, std::string>> ranked;
        for (const auto& [reason, tally] : blocked) ranked.emplace_back(tally, reason);
        std::sort(ranked.begin(), ranked.end(), [](const auto& a, const auto& b) {
            return a.first != b.first ? a.first > b.first : a.second < b.second;
        });
        why = lead + ": no mirrored seat within reach";
        for (std::size_t index = 0; index < ranked.size() && index < static_cast<std::size_t>(constants::obstacle_rows.value); ++index)
            why += "; " + std::to_string(ranked[index].first) + " " + ranked[index].second;
        return false;
    };
    const auto elsewhere = [&](const std::vector<std::size_t>& members) {
        const std::vector<Frame> frames = frames_of(members);
        for (const std::vector<Point>* ring : {&near, &far})
            for (std::size_t index = 0; index < frames.size(); ++index) {
                if (ring == &near && index == 0) continue;
                const std::vector<Move> mirror = swapped(members, frames[index]);
                for (const Point by : *ring) {
                    std::vector<Move> moves = mirror;
                    for (auto& move : moves) move.pose.at = shifted(move.pose.at, by);
                    if (!crowding(moves) && kernel.move_many(moves)) return true;
                }
            }
        return false;
    };
    const auto with_sets = [&](std::vector<std::size_t> grown, std::vector<char>& taken, std::size_t partner) {
        for (const std::size_t part : sets[root(partner)])
            if (!taken[part]) {
                taken[part] = 1;
                grown.push_back(part);
            }
        return grown;
    };
    const auto contract_set = [&](const std::vector<std::size_t>& members) {
        std::vector<char> taken(count, 0);
        std::vector<std::size_t> grown = members;
        for (const std::size_t part : members) taken[part] = 1;
        for (std::size_t index = 0; index < grown.size(); ++index)
            for (const PadGap& tie : problem.constraints.pad_gaps) {
                if (tie.sense != Sense::at_most || (tie.anchor != grown[index] && tie.member != grown[index])) continue;
                const std::size_t partner = tie.anchor == grown[index] ? tie.member : tie.anchor;
                grown = with_sets(std::move(grown), taken, partner);
            }
        return grown;
    };
    const auto exchange_set = [&](const std::vector<std::size_t>& members, std::string& why) {
        std::vector<std::size_t> grown = members;
        for (std::size_t round = 0; round < static_cast<std::size_t>(constants::exchange_rounds.value); ++round) {
            const std::vector<Frame> frames = frames_of(grown);
            if (frames.empty() || !free_set(grown)) return members;
            std::vector<char> taken(count, 0);
            for (const std::size_t part : grown) taken[part] = 1;
            std::vector<std::size_t> met;
            const Snapshot before = kernel.snapshot();
            if (!kernel.force(swapped(grown, frames.front()))) {
                kernel.restore(before);
                return members;
            }
            for (const std::size_t part : grown)
                if (const auto found = kernel.breach(part)) {
                    const std::size_t other = found->part == part ? found->other : found->part;
                    if (other == part || other >= count) {
                        why = problem.parts[part].reference + " meets " + breach_name(found->kind) + " against the board";
                        kernel.restore(before);
                        return members;
                    }
                    if (!taken[other]) met.push_back(other);
                }
            kernel.restore(before);
            if (met.empty()) return grown;
            for (const std::size_t other : met) {
                if (!free_set(sets[root(other)])) {
                    why = problem.parts[other].reference + " is in the way and its cluster cannot change face";
                    return members;
                }
                grown = with_sets(std::move(grown), taken, other);
            }
            grown = contract_set(grown);
        }
        return grown;
    };
    const auto fits = [&](const std::vector<std::size_t>& members) {
        const double gain = gain_of(members);
        return free_set(members) && gain > 0 && rear + gain <= top - gain;
    };
    for (const auto& candidate : candidates) {
        const auto& members = sets[candidate.lead];
        const std::string lead = problem.parts[candidate.lead].reference;
        const double gain = gain_of(members);
        if (gain <= 0) continue;
        if (rear + gain > top - gain) {
            report.kept_on_top.emplace_back(gain, lead + ": the rear would hold more than the top");
            continue;
        }
        std::string why, wider_why, swap_why;
        std::vector<std::size_t> moved = members;
        const Snapshot entry = kernel.snapshot();
        const std::vector<Pose>& before = entry.placement;
        std::size_t freed = released(members);
        bool flipped = in_place(members, lead, why);
        const std::vector<std::size_t> wider = contract_set(members);
        const bool grew = wider.size() > members.size() && fits(wider) &&
                          (wide || std::all_of(wider.begin(), wider.end(), [&](std::size_t part) {
                              return kernel.placement()[part].face == Face::top;
                          }));
        if (!flipped && grew) {
            freed += released(wider);
            if (in_place(wider, lead + " with the parts its contracts tie to it", wider_why)) {
                flipped = true;
                moved = wider;
            }
        }
        const std::vector<std::size_t>& body = grew ? wider : members;
        if (!flipped && wide && elsewhere(body)) {
            flipped = true;
            moved = body;
            ++report.shifted;
        }
        if (!flipped && wide) {
            const std::vector<std::size_t> grown = exchange_set(body, swap_why);
            if (grown.size() > body.size() && fits(grown)) freed += released(grown);
            if (grown.size() > body.size() && fits(grown) && (in_place(grown, lead, swap_why) || elsewhere(grown))) {
                flipped = true;
                moved = grown;
                ++report.exchanged;
            }
        }
        if (!flipped) {
            kernel.restore(entry);
            if (freed > 0) why += "; " + std::to_string(freed) + " face-bound parts released from its copper field first";
            if (!wider_why.empty()) why += "; " + wider_why;
            if (!why.empty()) {
                std::ostringstream far_text;
                if (wide)
                    far_text << "; no rear seat in any turn within " << to_mm(static_cast<Nm>(constants::balance_reach.value))
                             << " mm";
                why += far_text.str();
                if (!swap_why.empty()) why += "; changing faces with what is under it: " + swap_why;
                report.kept_on_top.emplace_back(gain, why);
            }
            continue;
        }
        double area = 0;
        for (const std::size_t part : moved) {
            const double own = area_mm2(gate_at(problem, part, kernel.placement()[part]));
            if (before[part].face == Face::top) {
                area += own;
                ++report.parts;
            } else {
                area -= own;
                ++report.risen;
            }
        }
        ++report.flipped;
        report.released += freed;
        top -= area;
        rear += area;
    }
    report.top_after = face_area(Face::top);
    report.rear_after = face_area(Face::bottom);
    return report;
}

bool steps_aside(Kernel& kernel, std::size_t part, const std::vector<Point>& offsets) {
    const Problem& problem = kernel.problem();
    const Pose from = kernel.placement()[part];
    const bool flips = may_sink(problem, kernel.placement(), part) || from.face == Face::bottom;
    const Face other = from.face == Face::top ? Face::bottom : Face::top;
    for (const Point by : offsets)
        for (const Face face : {from.face, other}) {
            if (face != from.face && !flips) continue;
            if (face == from.face && by.x == 0 && by.y == 0) continue;
            const Pose pose{shifted(from.at, by), from.turn, face};
            if (crowds_escape(problem, kernel.placement(), part, pose)) continue;
            if (kernel.rejection(part, pose)) continue;
            if (kernel.move(part, pose)) return true;
        }
    return false;
}

namespace {

struct Seat {
    Pose pose;
    Nm gap = 0;
};

bool evicts(Kernel& kernel, std::size_t guest, const Pose& seat, const std::vector<char>& settled,
            const std::vector<Point>& aside, std::size_t& moved_aside) {
    const Problem& problem = kernel.problem();
    const Probe probe = kernel.probe({{guest, seat}});
    if (!probe.placeable || probe.blockers.empty()) return false;
    for (const std::size_t blocker : probe.blockers) {
        const Part& item = problem.parts[blocker];
        if (settled[blocker] || item.fixed || item.connector ||
            item.fanout_pins > static_cast<int>(constants::small_pins.value))
            return false;
    }
    const Snapshot before = kernel.snapshot();
    bool sound = kernel.force({{guest, seat}});
    for (std::size_t index = 0; sound && index < probe.blockers.size(); ++index)
        sound = steps_aside(kernel, probe.blockers[index], aside);
    sound = sound && !kernel.breach(guest);
    for (std::size_t index = 0; sound && index < probe.blockers.size(); ++index)
        sound = !kernel.breach(probe.blockers[index]);
    if (!sound) {
        kernel.restore(before);
        return false;
    }
    moved_aside += probe.blockers.size();
    return true;
}

}

bool seat_first(Kernel& kernel, const NetOrder& rule, Nm pitch) {
    const Problem& problem = kernel.problem();
    const Pose anchor = kernel.placement()[rule.anchor];
    const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
    if (pins.empty()) return false;
    Box pin = pins.front();
    for (const auto& box : pins) pin = united(pin, box);
    const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
    const std::vector<Point> ring = seat_ring(pitch, static_cast<Nm>(constants::ring_limit.value), {0, 0});
    const std::vector<Point> far_ring = seat_ring(static_cast<Nm>(constants::far_pitch.value), static_cast<Nm>(constants::wide_reach.value), {0, 0});
    const auto gap_of = [&](std::size_t part, const Pose& pose) {
        return squared_net_gap(problem, rule.anchor, anchor, rule.anchor_names, part, pose, rule.net);
    };
    std::vector<Seat> seats;
    const Pose lead_from = kernel.placement()[rule.lead];
    for (const Point by : ring)
        for (int turn = 0; turn < turn_count; ++turn) {
            const Pose pose{shifted(target, by), static_cast<Turn>(turn), lead_from.face};
            seats.push_back({pose, gap_of(rule.lead, pose)});
        }
    std::stable_sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) { return a.gap < b.gap; });
    const auto carried_back = [&](std::size_t rival, const Pose& from, double beyond) {
        std::vector<std::size_t> set{rival};
        for (std::size_t index = 0; index < set.size(); ++index) {
            const auto follow = [&](const PadGap& tie) {
                if (tie.anchor == set[index] && tie.member != rule.lead && tie.member != rule.anchor &&
                    !problem.parts[tie.member].fixed && std::find(set.begin(), set.end(), tie.member) == set.end())
                    set.push_back(tie.member);
            };
            for (const PadGap& tie : problem.constraints.pad_gaps) follow(tie);
            for (const PadGap& tie : problem.constraints.soft_gaps) follow(tie);
        }
        if (set.size() == 1) return false;
        for (const std::vector<Point>* offsets : {&ring, &far_ring})
            for (const Point by : *offsets) {
                Pose pose = from;
                pose.at = shifted(from.at, by);
                if (gap_of(rival, pose) <= beyond || crowds_escape(problem, kernel.placement(), rival, pose)) continue;
                std::vector<Move> moves{{rival, pose}};
                for (std::size_t index = 1; index < set.size(); ++index) {
                    Pose with = kernel.placement()[set[index]];
                    with.at = shifted(with.at, by);
                    moves.push_back({set[index], with});
                }
                const Snapshot held = kernel.snapshot();
                if (kernel.force(moves) &&
                    std::none_of(set.begin(), set.end(), [&](std::size_t member) { return kernel.breach(member).has_value(); }))
                    return true;
                kernel.restore(held);
            }
        return false;
    };
    const auto settle = [&](const Seat& seat, bool clearing) {
        const Snapshot before = kernel.snapshot();
        std::size_t stepped = 0;
        if (clearing ? !evicts(kernel, rule.lead, seat.pose, std::vector<char>(problem.parts.size(), 0),
                               seat_ring(pitch, static_cast<Nm>(constants::aside_reach.value), {0, 0}), stepped)
                     : !kernel.force({{rule.lead, seat.pose}}))
            return false;
        bool sound = true;
        for (const std::size_t rival : rule.rivals) {
            const Pose from = kernel.placement()[rival];
            if (gap_of(rival, from) > seat.gap) continue;
            if (problem.parts[rival].fixed) {
                sound = false;
                break;
            }
            bool moved = false;
            for (const std::vector<Point>* offsets : {&ring, &far_ring}) {
              for (const Point by : *offsets) {
                for (int turn = 0; turn < turn_count && !moved; ++turn) {
                    const Pose pose{shifted(from.at, by), static_cast<Turn>(turn), from.face};
                    if (gap_of(rival, pose) <= seat.gap || crowds_escape(problem, kernel.placement(), rival, pose) ||
                        kernel.rejection(rival, pose))
                        continue;
                    moved = kernel.move(rival, pose);
                }
                if (moved) break;
              }
              if (moved) break;
            }
            if (!moved) moved = carried_back(rival, from, seat.gap);
            if (!moved) {
                sound = false;
                break;
            }
        }
        if (sound && !kernel.breach(rule.lead) && net_order_met(problem, rule, kernel.placement(), rule.lead, nullptr))
            return true;
        kernel.restore(before);
        return false;
        };
    std::size_t tries = 0;
    for (const Seat& seat : seats) {
        if (tries >= static_cast<std::size_t>(constants::order_tries.value)) break;
        if (crowds_escape(problem, kernel.placement(), rule.lead, seat.pose)) continue;
        const Probe probe = kernel.probe({{rule.lead, seat.pose}});
        if (!probe.placeable || std::any_of(probe.blockers.begin(), probe.blockers.end(), [&](std::size_t blocker) {
                return std::find(rule.rivals.begin(), rule.rivals.end(), blocker) == rule.rivals.end();
            }))
            continue;
        ++tries;
        if (settle(seat, false)) return true;
    }
    if (settle({lead_from, gap_of(rule.lead, lead_from)}, false)) return true;
    std::size_t cleared = 0;
    for (const Seat& seat : seats) {
        if (cleared >= static_cast<std::size_t>(constants::evict_tries.value)) break;
        if (crowds_escape(problem, kernel.placement(), rule.lead, seat.pose)) continue;
        const Probe probe = kernel.probe({{rule.lead, seat.pose}});
        if (!probe.placeable || std::all_of(probe.blockers.begin(), probe.blockers.end(), [&](std::size_t blocker) {
                return std::find(rule.rivals.begin(), rule.rivals.end(), blocker) != rule.rivals.end();
            }))
            continue;
        ++cleared;
        if (settle(seat, true)) return true;
    }
    return false;
}

bool seat_faced(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius, bool evict, std::size_t& moved_aside) {
    const Problem& problem = kernel.problem();
    const std::size_t part = rule.member;
    if (!kernel.release(part)) return false;
    const Pose& anchor = kernel.placement()[rule.anchor];
    const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
    if (pins.empty()) return false;
    Box pin = pins.front();
    for (const auto& box : pins) pin = united(pin, box);
    const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
    const Pose from = kernel.placement()[part];
    const bool flips = may_sink(problem, kernel.placement(), part) || from.face == Face::bottom;
    std::vector<Seat> seats;
    for (const Point by : seat_ring(pitch, radius, {0, 0}))
        for (const Face face : {Face::top, Face::bottom}) {
            if (face != from.face && !flips) continue;
            for (int turn = 0; turn < turn_count; ++turn) {
                const Pose pose{shifted(target, by), static_cast<Turn>(turn), face};
                if (!pair_faced(problem, kernel.board(), rule.anchor, anchor, part, pose, rule.or_under)) continue;
                seats.push_back({pose, squared_pad_gap(problem, rule, anchor, pose)});
            }
        }
    std::stable_sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) { return a.gap < b.gap; });
    const std::vector<char> settled(problem.parts.size(), 0);
    const std::vector<Point> aside = seat_ring(pitch, static_cast<Nm>(constants::aside_reach.value), {0, 0});
    std::size_t tries = 0;
    for (const Seat& seat : seats) {
        if (crowds_escape(problem, kernel.placement(), part, seat.pose)) continue;
        if (!kernel.rejection(part, seat.pose)) {
            if (kernel.move(part, seat.pose)) return true;
            continue;
        }
        if (evict && tries < static_cast<std::size_t>(constants::evict_tries.value)) {
            ++tries;
            if (evicts(kernel, part, seat.pose, settled, aside, moved_aside)) return true;
        }
    }
    return false;
}

bool seat_faced_chain(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius, std::size_t& moved_aside) {
    const Problem& problem = kernel.problem();
    const std::size_t part = rule.member;
    if (!kernel.release(part)) return false;
    const Pose anchor = kernel.placement()[rule.anchor];
    const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
    if (pins.empty()) return false;
    Box pin = pins.front();
    for (const auto& box : pins) pin = united(pin, box);
    const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
    std::vector<Seat> seats;
    for (const Point by : seat_ring(pitch, radius, {0, 0}))
        for (int turn = 0; turn < turn_count; ++turn) {
            const Pose pose{shifted(target, by), static_cast<Turn>(turn), anchor.face};
            if (!pair_faced(problem, kernel.board(), rule.anchor, anchor, part, pose, rule.or_under)) continue;
            seats.push_back({pose, squared_pad_gap(problem, rule, anchor, pose)});
        }
    std::stable_sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) { return a.gap < b.gap; });
    const std::vector<Point> aside = seat_ring(pitch, static_cast<Nm>(constants::aside_reach.value), {0, 0});
    std::size_t tries = 0;
    for (const Seat& seat : seats) {
        if (crowds_escape(problem, kernel.placement(), part, seat.pose)) continue;
        const Probe probe = kernel.probe({{part, seat.pose}});
        if (!probe.placeable || probe.blockers.empty()) continue;
        if (std::any_of(probe.blockers.begin(), probe.blockers.end(), [&](std::size_t blocker) {
                return blocker == rule.anchor || problem.parts[blocker].fixed || problem.parts[blocker].connector;
            }))
            continue;
        if (tries++ >= static_cast<std::size_t>(constants::evict_tries.value)) break;
        const Snapshot before = kernel.snapshot();
        std::size_t stepped = 0;
        bool sound = kernel.force({{part, seat.pose}});
        for (std::size_t index = 0; sound && index < probe.blockers.size(); ++index) {
            const std::size_t blocker = probe.blockers[index];
            const auto own = std::find_if(problem.constraints.soft_gaps.begin(), problem.constraints.soft_gaps.end(),
                                          [&](const PadGap& tie) { return tie.member == blocker && tie.same_face; });
            sound = own != problem.constraints.soft_gaps.end() ? seat_faced(kernel, *own, pitch, radius, true, stepped)
                                                                : steps_aside(kernel, blocker, aside);
            sound = sound && !kernel.breach(blocker);
        }
        if (sound && !kernel.breach(part)) {
            moved_aside += probe.blockers.size() + stepped;
            return true;
        }
        kernel.restore(before);
    }
    return false;
}

bool seat_faced_together(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius) {
    const Problem& problem = kernel.problem();
    const std::size_t part = rule.member;
    std::vector<std::size_t> set{part};
    for (std::size_t index = 0; index < set.size(); ++index) {
        const auto follow = [&](const PadGap& tie) {
            if (tie.anchor == set[index] && !problem.parts[tie.member].fixed &&
                std::find(set.begin(), set.end(), tie.member) == set.end())
                set.push_back(tie.member);
        };
        for (const PadGap& tie : problem.constraints.pad_gaps) follow(tie);
        for (const PadGap& tie : problem.constraints.soft_gaps) follow(tie);
    }
    if (set.size() == 1) return false;
    const Pose& anchor = kernel.placement()[rule.anchor];
    const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
    if (pins.empty()) return false;
    Box pin = pins.front();
    for (const auto& box : pins) pin = united(pin, box);
    const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
    const Pose from = kernel.placement()[part];
    std::vector<Seat> seats;
    for (const Point by : seat_ring(pitch, radius, {0, 0}))
        for (int turn = 0; turn < turn_count; ++turn) {
            const Pose pose{shifted(target, by), static_cast<Turn>(turn), anchor.face};
            if (!pair_faced(problem, kernel.board(), rule.anchor, anchor, part, pose, rule.or_under)) continue;
            seats.push_back({pose, squared_pad_gap(problem, rule, anchor, pose)});
        }
    std::stable_sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) { return a.gap < b.gap; });
    for (const Seat& seat : seats) {
        const Point by{seat.pose.at.x - from.at.x, seat.pose.at.y - from.at.y};
        std::vector<Move> moves{{part, seat.pose}};
        bool possible = true;
        for (std::size_t index = 1; index < set.size(); ++index) {
            const Part& item = problem.parts[set[index]];
            Pose pose = kernel.placement()[set[index]];
            pose.at = shifted(pose.at, by);
            if (pose.face != seat.pose.face) {
                if (!problem.footprints[item.footprint].flippable || (item.top_only && seat.pose.face == Face::bottom)) {
                    possible = false;
                    break;
                }
                pose.face = seat.pose.face;
            }
            moves.push_back({set[index], pose});
        }
        if (!possible) continue;
        const Snapshot before = kernel.snapshot();
        if (kernel.force(moves) &&
            std::none_of(set.begin(), set.end(), [&](std::size_t member) { return kernel.breach(member).has_value(); }))
            return true;
        kernel.restore(before);
    }
    return false;
}

std::string seat_obstacles(const Kernel& placed_kernel, const PadGap& rule, Nm pitch) {
    const std::size_t part = rule.member;
    Kernel kernel = placed_kernel;
    if (!kernel.release(part)) return "it owns a copper pour and cannot leave it";
    const Problem& problem = kernel.problem();
    const Pose from = kernel.placement()[part];
    const Pose& anchor = kernel.placement()[rule.anchor];
    const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
    if (pins.empty()) return "the served pin has no pad";
    Box pin = pins.front();
    for (const auto& box : pins) pin = united(pin, box);
    const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
    const bool flips = may_sink(problem, kernel.placement(), part) || from.face == Face::bottom;
    std::map<std::string, std::size_t> tally;
    std::size_t seats = 0;
    const Nm apart = pad_gap_length(problem, rule, kernel.placement());
    const Nm coarse = static_cast<Nm>(constants::far_pitch.value);
    const bool far = apart > 2 * static_cast<Nm>(constants::ring_limit.value);
    const Nm bound = far ? apart : rule.reach;
    for (const Point by : seat_ring(far ? coarse : pitch, bound + pitch, {0, 0}))
        for (const Face face : {Face::bottom, Face::top})
            for (int turn = 0; turn < turn_count; ++turn) {
                const Pose pose{shifted(target, by), static_cast<Turn>(turn), face};
                if (squared_pad_gap(problem, rule, anchor, pose) > squared(bound)) continue;
                if (!pair_faced(problem, kernel.board(), rule.anchor, anchor, part, pose, rule.or_under)) continue;
                ++seats;
                if (face != from.face && !flips) {
                    ++tally[face == Face::bottom ? "rear face not permitted" : "top face not permitted"];
                } else if (crowds_escape(problem, kernel.placement(), part, pose)) {
                    ++tally["crowds an escape on the other face"];
                } else if (const auto found = kernel.rejection(part, pose)) {
                    const std::size_t other = found->part == part ? found->other : found->part;
                    std::string holder = other < problem.parts.size() && other != part ? problem.parts[other].reference : "board";
                    if (found->kind == Breach::reserved) {
                        const Box swept = placed(problem.footprints[problem.parts[part].footprint].on(pose.face).gate_box, pose.at, pose.turn);
                        for (std::size_t reserve = 0; reserve < kernel.reserves().size(); ++reserve)
                            if (overlaps(swept, kernel.reserves()[reserve])) {
                                holder = problem.reserves[reserve].source;
                                break;
                            }
                    }
                    ++tally[std::string(breach_name(found->kind)) + " " + holder];
                } else {
                    ++tally["open seat"];
                }
            }
    std::vector<std::pair<std::size_t, std::string>> ranked;
    for (const auto& [reason, count] : tally) ranked.emplace_back(count, reason);
    std::sort(ranked.begin(), ranked.end(), [](const auto& a, const auto& b) {
        return a.first != b.first ? a.first > b.first : a.second < b.second;
    });
    const auto where = [&](std::size_t index) {
        const Pose& pose = kernel.placement()[index];
        std::ostringstream out;
        out << problem.parts[index].reference << " at " << to_mm(pose.at.x) << "," << to_mm(pose.at.y)
            << (pose.face == Face::top ? " top" : " rear");
        return out.str();
    };
    std::string text = where(part) + ", " + where(rule.anchor) + "; " + std::to_string(seats) +
                       (far ? " seats nearer than it is now" : " seats within reach");
    for (std::size_t index = 0; index < ranked.size() && index < static_cast<std::size_t>(constants::obstacle_rows.value); ++index)
        text += "; " + std::to_string(ranked[index].first) + " " + ranked[index].second;
    return text;
}

OrderReport lead_first(Kernel& kernel, Nm pitch) {
    const Problem& problem = kernel.problem();
    OrderReport report;
    const std::vector<Point> ring = seat_ring(pitch, static_cast<Nm>(constants::ring_limit.value), {0, 0});
    for (const NetOrder& rule : net_orders_of(problem)) {
        ++report.wanted;
        const auto met = [&] { return net_order_met(problem, rule, kernel.placement(), rule.lead, nullptr); };
        if (met()) {
            ++report.met_before;
            ++report.met_after;
            continue;
        }
        const Pose anchor = kernel.placement()[rule.anchor];
        const Nm bound = rival_bound(problem, rule, kernel.placement());
        const Nm now = squared_net_gap(problem, rule.anchor, anchor, rule.anchor_names, rule.lead,
                                       kernel.placement()[rule.lead], rule.net);
        const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
        Box pin = pins.front();
        for (const auto& box : pins) pin = united(pin, box);
        const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
        std::vector<Seat> seats;
        for (const Point by : ring)
            for (int turn = 0; turn < turn_count; ++turn) {
                const Pose pose{shifted(target, by), static_cast<Turn>(turn), anchor.face};
                const Nm gap = squared_net_gap(problem, rule.anchor, anchor, rule.anchor_names, rule.lead, pose, rule.net);
                if (gap <= bound || gap < now) seats.push_back({pose, gap});
            }
        std::stable_sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) { return a.gap < b.gap; });
        for (const Seat& seat : seats) {
            if (crowds_escape(problem, kernel.placement(), rule.lead, seat.pose) || kernel.rejection(rule.lead, seat.pose))
                continue;
            if (kernel.move(rule.lead, seat.pose)) break;
        }
        const bool nearer = met();
        const Nm lead = squared_net_gap(problem, rule.anchor, anchor, rule.anchor_names, rule.lead,
                                        kernel.placement()[rule.lead], rule.net);
        for (const std::size_t rival : rule.rivals) {
            const Pose from = kernel.placement()[rival];
            const auto gap = [&](const Pose& pose) {
                return squared_net_gap(problem, rule.anchor, anchor, rule.anchor_names, rival, pose, rule.net);
            };
            if (nearer || problem.parts[rival].fixed || gap(from) >= lead) continue;
            for (const Point by : ring) {
                const Pose pose{shifted(from.at, by), from.turn, from.face};
                if (gap(pose) < lead || crowds_escape(problem, kernel.placement(), rival, pose) ||
                    kernel.rejection(rival, pose))
                    continue;
                if (kernel.move(rival, pose)) {
                    ++report.moved_back;
                    break;
                }
            }
        }
        if (!met()) continue;
        if (nearer) ++report.reseated;
        ++report.met_after;
    }
    return report;
}

AttractReport attract(Kernel& kernel, Nm pitch, Nm reach) {
    const Problem& problem = kernel.problem();
    AttractReport report;
    report.routed_before = kernel.routed_length();
    const auto& rules = problem.constraints.soft_gaps;
    const auto faced = [&](const PadGap& rule, const Pose& anchor, const Pose& member) {
        return !rule.same_face ||
               pair_faced(problem, kernel.board(), rule.anchor, anchor, rule.member, member, rule.or_under);
    };
    const auto met = [&](const PadGap& rule) {
        if (!faced(rule, kernel.placement()[rule.anchor], kernel.placement()[rule.member])) return false;
        return squared_pad_gap(problem, rule, kernel.placement()[rule.anchor], kernel.placement()[rule.member]) <=
               squared(rule.limit);
    };
    std::vector<std::size_t> order;
    for (std::size_t index = 0; index < rules.size(); ++index)
        if (rules[index].sense == Sense::at_most) order.push_back(index);
    std::stable_sort(order.begin(), order.end(),
                     [&](std::size_t a, std::size_t b) {
                         if (rules[a].first != rules[b].first) return rules[a].first;
                         return rules[a].limit < rules[b].limit;
                     });
    for (const std::size_t index : order)
        if (met(rules[index])) ++report.met_before;
    std::vector<char> settled(problem.parts.size(), 0);
    std::vector<std::vector<std::size_t>> served(problem.parts.size());
    for (const std::size_t index : order) served[rules[index].anchor].push_back(rules[index].member);
    const auto train = [&](std::size_t head, const Pose& pose) {
        const Point from = kernel.placement()[head].at;
        const Point by{pose.at.x - from.x, pose.at.y - from.y};
        std::vector<Move> moves{{head, pose}};
        for (std::size_t next = 0; next < moves.size(); ++next)
            for (const std::size_t follower : served[moves[next].part]) {
                if (std::any_of(moves.begin(), moves.end(), [&](const Move& move) { return move.part == follower; })) continue;
                Pose carried = kernel.placement()[follower];
                carried.at = shifted(carried.at, by);
                moves.push_back({follower, carried});
            }
        return moves;
    };
    std::map<Nm, std::vector<Point>> rings;
    const std::vector<Point> aside = seat_ring(pitch, static_cast<Nm>(constants::aside_reach.value), {0, 0});
    for (const std::size_t index : order) {
        const PadGap& rule = rules[index];
        const std::size_t part = rule.member;
        if (met(rule)) {
            settled[part] = 1;
            continue;
        }
        ++report.wanted;
        const Pose from = kernel.placement()[part];
        const Pose& anchor = kernel.placement()[rule.anchor];
        const Nm before = squared_pad_gap(problem, rule, anchor, from);
        const std::vector<Box> pins = named_boxes(problem, rule.anchor, anchor, rule.anchor_names);
        if (pins.empty()) continue;
        Box pin = pins.front();
        for (const auto& box : pins) pin = united(pin, box);
        const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
        const Nm radius = std::max(reach, static_cast<Nm>(constants::ring_limit.value));
        auto ring = rings.find(radius);
        if (ring == rings.end()) ring = rings.emplace(radius, seat_ring(pitch, radius, {0, 0})).first;
        const bool flips = may_sink(problem, kernel.placement(), part) || from.face == Face::bottom;
        const Nm within = squared(rule.limit);
        const auto seats_on = [&](const std::vector<Point>& offsets) {
            std::vector<Seat> seats;
            for (const Point by : offsets)
                for (const Face face : {Face::bottom, Face::top}) {
                    if (face != from.face && !flips) continue;
                    if (rule.same_face && !rule.or_under && face != anchor.face) continue;
                    for (int turn = 0; turn < turn_count; ++turn) {
                        const Pose pose{shifted(target, by), static_cast<Turn>(turn), face};
                        const Nm gap = squared_pad_gap(problem, rule, anchor, pose);
                        if (!faced(rule, anchor, pose)) continue;
                        if (gap < before || !faced(rule, anchor, from)) seats.push_back({pose, gap});
                    }
                }
            std::stable_sort(seats.begin(), seats.end(), [&](const Seat& a, const Seat& b) {
                const bool near_a = a.gap <= within, near_b = b.gap <= within;
                if (near_a != near_b) return near_a;
                if (near_a && a.pose.face != b.pose.face) return a.pose.face == Face::bottom;
                return a.gap < b.gap;
            });
            return seats;
        };
        bool seated = false;
        std::size_t tries = 0;
        for (const Seat& seat : seats_on(ring->second)) {
            if (crowds_escape(problem, kernel.placement(), part, seat.pose)) continue;
            if (!served[part].empty()) {
                seated = kernel.move_many(train(part, seat.pose));
            } else if (!kernel.rejection(part, seat.pose)) {
                seated = kernel.move(part, seat.pose);
            } else if (seat.gap <= within && tries < static_cast<std::size_t>(constants::evict_tries.value)) {
                ++tries;
                seated = evicts(kernel, part, seat.pose, settled, aside, report.moved_aside);
            }
            if (seated) break;
        }
        const Nm apart = pad_gap_length(problem, rule, kernel.placement());
        const Nm coarse = static_cast<Nm>(constants::far_pitch.value);
        for (Nm wide = radius * 2; !seated && wide / 2 < apart; wide *= 2)
            for (const Seat& seat : seats_on(seat_ring(coarse, wide, {0, 0}))) {
                if (served[part].empty() && kernel.rejection(part, seat.pose)) continue;
                if (crowds_escape(problem, kernel.placement(), part, seat.pose)) continue;
                seated = served[part].empty() ? kernel.move(part, seat.pose)
                                              : kernel.move_many(train(part, seat.pose));
                if (seated) {
                    ++report.far_seated;
                    break;
                }
            }
        settled[part] = 1;
        if (!seated) continue;
        ++report.seated;
        if (from.face == Face::top && kernel.placement()[part].face == Face::bottom) ++report.to_rear;
    }
    std::map<std::size_t, std::vector<std::size_t>> siblings;
    for (const std::size_t index : order)
        if (!met(rules[index])) siblings[rules[index].anchor].push_back(index);
    const Nm near_radius = std::max(reach, static_cast<Nm>(constants::ring_limit.value));
    const std::vector<Point> near = seat_ring(pitch, near_radius, {0, 0});
    for (const auto& [owner, wanting] : siblings) {
        if (wanting.size() < 2) continue;
        const Snapshot before = kernel.snapshot();
        std::vector<char> pending(problem.parts.size(), 0);
        for (const std::size_t index : wanting) pending[rules[index].member] = 1;
        std::vector<std::size_t> touched;
        for (const std::size_t index : wanting) {
            const PadGap& rule = rules[index];
            const std::size_t part = rule.member;
            pending[part] = 0;
            const Pose from = kernel.placement()[part];
            const Pose anchor = kernel.placement()[owner];
            const std::vector<Box> pins = named_boxes(problem, owner, anchor, rule.anchor_names);
            if (pins.empty()) continue;
            Box pin = pins.front();
            for (const auto& box : pins) pin = united(pin, box);
            const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
            const bool flips = may_sink(problem, kernel.placement(), part) || from.face == Face::bottom;
            std::vector<Seat> seats;
            for (const Point by : near)
                for (const Face face : {Face::bottom, Face::top}) {
                    if (face != from.face && !flips) continue;
                    for (int turn = 0; turn < turn_count; ++turn) {
                        const Pose pose{shifted(target, by), static_cast<Turn>(turn), face};
                        if (!faced(rule, anchor, pose)) continue;
                        const Nm gap = squared_pad_gap(problem, rule, anchor, pose);
                        if (gap <= squared(rule.limit)) seats.push_back({pose, gap});
                    }
                }
            std::stable_sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) { return a.gap < b.gap; });
            for (const Seat& seat : seats) {
                if (crowds_escape(problem, kernel.placement(), part, seat.pose)) continue;
                const std::vector<Move> moves = train(part, seat.pose);
                std::vector<Move> back;
                for (const Move& move : moves) back.push_back({move.part, kernel.placement()[move.part]});
                if (!kernel.force(moves)) continue;
                const bool sound = std::all_of(moves.begin(), moves.end(), [&](const Move& move) {
                    const auto found = kernel.breach(move.part);
                    return !found || (found->kind == Breach::contract && pending[found->other]);
                });
                if (sound) {
                    for (const Move& move : moves) touched.push_back(move.part);
                    break;
                }
                kernel.force(back);
            }
        }
        const bool legal = std::none_of(touched.begin(), touched.end(),
                                        [&](std::size_t part) { return kernel.breach(part).has_value(); }) &&
                           std::none_of(wanting.begin(), wanting.end(), [&](std::size_t index) {
                               return kernel.breach(rules[index].member).has_value();
                           });
        if (!legal || touched.empty()) {
            kernel.restore(before);
            continue;
        }
        for (const std::size_t index : wanting)
            if (met(rules[index])) ++report.together;
    }
    for (const std::size_t index : order)
        if (met(rules[index])) ++report.met_after;
    report.routed_after = kernel.routed_length();
    return report;
}

}
