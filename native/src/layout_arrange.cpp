#include "schgen/layout_arrange.hpp"

#include "schgen/layout_construct.hpp"
#include "schgen/layout_sink.hpp"

#include <algorithm>
#include <functional>
#include <chrono>
#include <cmath>
#include <map>
#include <numeric>
#include <optional>

namespace schgen::layout {
namespace {

inline constexpr std::array<Side, edge_count> sides{Side::north, Side::south, Side::west, Side::east};
inline constexpr std::array<double, 3> block_shapes{0.7, 1.0, 1.5};

bool rides_the_outline(const Part& part) { return part.edge.has_value() || part.corner.has_value(); }

Nm magnitude(Nm value) { return value < 0 ? -value : value; }

struct Cluster {
    std::string sheet, name;
    std::vector<std::size_t> members;
    double area = 0;
};

struct Block {
    std::vector<std::size_t> members;
    std::vector<Pose> base;
};

struct Option {
    std::vector<Pose> poses;
    std::vector<Box> top_boxes;
    Box swept;
};

struct Seat {
    double rank = 0;
    Nm travel = 0;
    std::size_t option = 0;
    Point by;
};

Box hull_of(const Kernel& kernel, const std::vector<std::size_t>& members) {
    return hull_at(kernel.problem(), kernel.placement(), members);
}

std::vector<Cluster> clusters_of(const Kernel& kernel) {
    const Problem& problem = kernel.problem();
    std::vector<Cluster> clusters;
    for (const auto& members : bundle(problem).units) {
        const bool held = std::any_of(members.begin(), members.end(), [&](std::size_t part) {
            return problem.parts[part].fixed || rides_the_outline(problem.parts[part]);
        });
        if (held) continue;
        Cluster cluster;
        cluster.sheet = problem.parts[members.front()].group;
        cluster.name = cluster.sheet + "/" + problem.parts[members.front()].reference;
        cluster.members = members;
        for (const std::size_t part : members) cluster.area += area_mm2(gate_at(problem, part, kernel.placement()[part]));
        clusters.push_back(std::move(cluster));
    }
    std::stable_sort(clusters.begin(), clusters.end(),
                     [](const Cluster& a, const Cluster& b) { return a.area > b.area; });
    return clusters;
}

Block as_placed(const Kernel& kernel, const std::vector<std::size_t>& members) {
    Block block;
    block.members = members;
    for (const std::size_t part : members) block.base.push_back(kernel.placement()[part]);
    return block;
}

std::vector<Block> repacked(const Kernel& kernel, const std::vector<const Cluster*>& clusters) {
    const Nm gap = static_cast<Nm>(constants::arrange_gap.value);
    std::vector<const Cluster*> order = clusters;
    std::vector<Box> hulls;
    std::stable_sort(order.begin(), order.end(), [&](const Cluster* a, const Cluster* b) {
        return hull_of(kernel, a->members).height() > hull_of(kernel, b->members).height();
    });
    double total = 0;
    Nm widest = 0;
    for (const Cluster* cluster : order) {
        hulls.push_back(hull_of(kernel, cluster->members));
        total += static_cast<double>(hulls.back().width() + gap) * static_cast<double>(hulls.back().height() + gap);
        widest = std::max(widest, hulls.back().width() + gap);
    }
    std::vector<Block> blocks;
    if (order.size() == 1) {
        blocks.push_back(as_placed(kernel, order.front()->members));
        return blocks;
    }
    std::vector<Nm> widths;
    for (const double shape : block_shapes)
        widths.push_back(std::max(widest, static_cast<Nm>(std::sqrt(total) * shape)));
    std::sort(widths.begin(), widths.end());
    widths.erase(std::unique(widths.begin(), widths.end()), widths.end());
    for (const Nm width : widths) {
        Block block;
        Nm x = 0, y = 0, shelf = 0;
        for (std::size_t index = 0; index < order.size(); ++index) {
            const Nm wide = hulls[index].width() + gap, tall = hulls[index].height() + gap;
            if (x > 0 && x + wide > width) {
                y += shelf;
                x = 0;
                shelf = 0;
            }
            const Point by{x - hulls[index].x0, y - hulls[index].y0};
            for (const std::size_t part : order[index]->members) {
                Pose pose = kernel.placement()[part];
                pose.at = shifted(pose.at, by);
                block.members.push_back(part);
                block.base.push_back(pose);
            }
            x += wide;
            shelf = std::max(shelf, tall);
        }
        blocks.push_back(std::move(block));
    }
    return blocks;
}

std::vector<Option> options_of(const Kernel& kernel, const Block& block, Nm pitch) {
    const Problem& problem = kernel.problem();
    Box hull = gate_at(problem, block.members.front(), block.base.front());
    for (std::size_t index = 0; index < block.members.size(); ++index)
        hull = united(hull, gate_at(problem, block.members[index], block.base[index]));
    const Point pivot{(hull.x0 + hull.x1) / 2 / pitch * pitch, (hull.y0 + hull.y1) / 2 / pitch * pitch};
    std::vector<Option> options;
    for (int quarter = 0; quarter < turn_count; ++quarter) {
        const Turn turn = static_cast<Turn>(quarter);
        Option option;
        std::optional<Box> swept;
        for (std::size_t index = 0; index < block.members.size(); ++index) {
            const std::size_t part = block.members[index];
            const Point arm{block.base[index].at.x - pivot.x, block.base[index].at.y - pivot.y};
            const Pose pose{shifted(pivot, turned(arm, turn)), combined(block.base[index].turn, turn),
                            block.base[index].face};
            const Box box = gate_at(problem, part, pose);
            swept = swept ? united(*swept, box) : box;
            if (pose.face == Face::top && !problem.parts[part].core_exempt) option.top_boxes.push_back(box);
            option.poses.push_back(pose);
        }
        option.swept = *swept;
        options.push_back(std::move(option));
    }
    return options;
}

std::vector<Move> moves_of(const Block& block, const Option& option, Point by) {
    std::vector<Move> moves;
    for (std::size_t index = 0; index < block.members.size(); ++index) {
        Pose pose = option.poses[index];
        pose.at = shifted(pose.at, by);
        moves.push_back({block.members[index], pose});
    }
    return moves;
}

std::string refusal(Kernel& kernel, const std::vector<Move>& moves) {
    const Problem& problem = kernel.problem();
    const Snapshot before = kernel.snapshot();
    std::string reason = "its reserved area cannot follow";
    if (kernel.force(moves)) {
        reason = "the block as a whole";
        for (const Move& move : moves)
            if (const auto found = kernel.breach(move.part)) {
                const std::size_t other = found->part == move.part ? found->other : found->part;
                reason = std::string(breach_name(found->kind)) + " against " +
                         (other != move.part && other < problem.parts.size() ? problem.parts[other].reference
                                                                             : std::string("the board"));
                break;
            }
    }
    kernel.restore(before);
    return reason;
}

Box beyond(const Box& outline, const Box& body, Side side) {
    switch (side) {
    case Side::north: return {outline.x0, outline.y0, outline.x1, body.y0};
    case Side::south: return {outline.x0, body.y1, outline.x1, outline.y1};
    case Side::west: return {outline.x0, outline.y0, body.x0, outline.y1};
    case Side::east: break;
    }
    return {body.x1, outline.y0, outline.x1, outline.y1};
}

template <typename Rank>
bool seat_block(Kernel& kernel, const std::vector<Block>& blocks, const Box& within, const Rank& rank,
                bool by_airwire, std::size_t tries, std::string* why,
                Nm pitch = static_cast<Nm>(constants::arrange_pitch.value)) {
    const std::optional<Box> body = kernel.board().module_body;
    std::vector<std::pair<std::size_t, Option>> options;
    for (std::size_t block = 0; block < blocks.size(); ++block)
        for (Option& option : options_of(kernel, blocks[block], pitch)) options.emplace_back(block, std::move(option));
    std::vector<Seat> seats;
    for (std::size_t choice = 0; choice < options.size(); ++choice) {
        const Option& option = options[choice].second;
        const Nm first_x = (within.x0 - option.swept.x0) / pitch, last_x = (within.x1 - option.swept.x1) / pitch;
        const Nm first_y = (within.y0 - option.swept.y0) / pitch, last_y = (within.y1 - option.swept.y1) / pitch;
        for (Nm column = first_x; column <= last_x; ++column)
            for (Nm row = first_y; row <= last_y; ++row) {
                const Point by{column * pitch, row * pitch};
                const Box swept = shifted(option.swept, by);
                if (!inside(swept, within)) continue;
                const std::optional<double> value = rank(swept);
                if (!value) continue;
                if (body && std::any_of(option.top_boxes.begin(), option.top_boxes.end(),
                                        [&](const Box& box) { return overlaps(shifted(box, by), *body); }))
                    continue;
                seats.push_back({*value, magnitude(by.x) + magnitude(by.y), choice, by});
            }
    }
    std::sort(seats.begin(), seats.end(), [](const Seat& a, const Seat& b) {
        if (a.rank != b.rank) return a.rank < b.rank;
        if (a.travel != b.travel) return a.travel < b.travel;
        if (a.option != b.option) return a.option < b.option;
        return a.by.x != b.by.x ? a.by.x < b.by.x : a.by.y < b.by.y;
    });
    const auto moves_at = [&](const Seat& seat) {
        return moves_of(blocks[options[seat.option].first], options[seat.option].second, seat.by);
    };
    const Snapshot before = kernel.snapshot();
    std::optional<Seat> best;
    Nm best_routed = 0;
    std::size_t legal = 0;
    const std::size_t wanted = by_airwire ? static_cast<std::size_t>(constants::arrange_choices.value) : 1;
    const std::size_t limit = std::min(seats.size(), tries);
    for (std::size_t index = 0; index < limit && legal < wanted; ++index) {
        if (!kernel.move_many(moves_at(seats[index]))) continue;
        ++legal;
        if (!best || kernel.pulled_length() < best_routed) {
            best = seats[index];
            best_routed = kernel.pulled_length();
        }
        kernel.restore(before);
    }
    if (best && kernel.move_many(moves_at(*best))) return true;
    kernel.restore(before);
    if (why) *why = seats.empty() ? "no room" : refusal(kernel, moves_at(seats.front()));
    return false;
}

Nm make_room(Kernel& kernel, const SqueezeOptions& options, const std::vector<Cluster>& clusters,
             const std::array<bool, edge_count>& kept) {
    const Nm pitch = static_cast<Nm>(constants::arrange_pitch.value);
    const Box outline = kernel.board().outline();
    const Box body = *kernel.board().module_body;
    double leaving = 0, frontage = 0;
    for (std::size_t index = 0; index < edge_count; ++index) {
        const bool lateral = sides[index] == Side::north || sides[index] == Side::south;
        if (kept[index]) {
            frontage += to_mm(lateral ? outline.width() : outline.height());
            continue;
        }
        const Box zone = beyond(outline, body, sides[index]);
        for (const Cluster& cluster : clusters)
            if (overlaps(hull_of(kernel, cluster.members), zone)) leaving += area_mm2(hull_of(kernel, cluster.members));
    }
    if (leaving <= 0 || frontage <= 0) return 0;
    const Nm by = (static_cast<Nm>(leaving * constants::room_factor.value / frontage / to_mm(pitch)) + 1) * pitch;
    for (std::size_t index = 0; index < edge_count; ++index)
        if (kept[index] && !widen(kernel, options, sides[index], by)) return 0;
    return by;
}

ArrangePlan evacuate(Kernel& kernel, const std::vector<Cluster>& clusters, const std::array<bool, edge_count>& kept) {
    const Box outline = kernel.board().outline();
    const Box body = *kernel.board().module_body;
    const Point centre{(body.x0 + body.x1) / 2, (body.y0 + body.y1) / 2};
    ArrangePlan plan;
    std::vector<Box> closed;
    for (std::size_t index = 0; index < edge_count; ++index) {
        if (kept[index]) plan.kept_sides += std::string(plan.kept_sides.empty() ? "" : "+") + side_name(sides[index]);
        else closed.push_back(beyond(outline, body, sides[index]));
    }
    const auto shut = [&](const Box& box) {
        return std::any_of(closed.begin(), closed.end(), [&](const Box& zone) { return overlaps(box, zone); });
    };
    const auto near_module = [&](const Box& swept) -> std::optional<double> {
        if (shut(swept)) return std::nullopt;
        const Nm dx = magnitude((swept.x0 + swept.x1) / 2 - centre.x), dy = magnitude((swept.y0 + swept.y1) / 2 - centre.y);
        return to_mm(std::max(dx, dy));
    };
    std::vector<std::string> order;
    std::map<std::string, std::vector<const Cluster*>> sheets;
    for (const Cluster& cluster : clusters) {
        if (!sheets.count(cluster.sheet)) order.push_back(cluster.sheet);
        sheets[cluster.sheet].push_back(&cluster);
    }
    for (const std::string& sheet : order) {
        const auto& members = sheets[sheet];
        const bool displaced = std::any_of(members.begin(), members.end(), [&](const Cluster* cluster) {
            return shut(hull_of(kernel, cluster->members));
        });
        if (!displaced) continue;
        std::string why;
        if (seat_block(kernel, repacked(kernel, members), outline, near_module, true, static_cast<std::size_t>(constants::arrange_tries.value), &why)) {
            plan.moved += members.size();
            continue;
        }
        bool any_left = false;
        for (const Cluster* cluster : members) {
            if (!shut(hull_of(kernel, cluster->members))) continue;
            if (seat_block(kernel, {as_placed(kernel, cluster->members)}, outline, near_module, true, static_cast<std::size_t>(constants::arrange_tries.value), &why)) {
                ++plan.moved;
                continue;
            }
            if (!any_left) plan.stuck.push_back(cluster->name + " (" + why + ")");
            any_left = true;
        }
    }
    return plan;
}

std::size_t tighten(Kernel& kernel, const std::vector<Cluster>& clusters) {
    const Problem& problem = kernel.problem();
    const Box body = *kernel.board().module_body;
    std::size_t moved = 0;
    for (std::size_t round = 0; round < static_cast<std::size_t>(constants::tighten_rounds.value); ++round) {
        bool improved = false;
        for (const Cluster& cluster : clusters) {
            const Box extent = held_extent(kernel);
            const Box bound = hull_of(kernel, cluster.members);
            if (bound.x0 > extent.x0 && bound.x1 < extent.x1 && bound.y0 > extent.y0 && bound.y1 < extent.y1) continue;
            std::vector<char> own(problem.parts.size(), 0);
            for (const std::size_t part : cluster.members) own[part] = 1;
            Box rest = body;
            for (std::size_t part = 0; part < problem.parts.size(); ++part)
                if (!own[part] && !rides_the_outline(problem.parts[part]))
                    rest = united(rest, gate_at(problem, part, kernel.placement()[part]));
            const double current = area_mm2(extent);
            const auto smaller = [&](const Box& swept) -> std::optional<double> {
                const double area = area_mm2(united(rest, swept));
                return area < current ? std::optional<double>(area) : std::nullopt;
            };
            if (!seat_block(kernel, {as_placed(kernel, cluster.members)}, extent, smaller, false, static_cast<std::size_t>(constants::arrange_tries.value), nullptr)) continue;
            ++moved;
            improved = true;
        }
        if (!improved) break;
    }
    return moved;
}

}

Box held_extent(const Kernel& kernel) {
    const Problem& problem = kernel.problem();
    std::optional<Box> extent = kernel.board().module_body;
    for (std::size_t part = 0; part < problem.parts.size(); ++part) {
        if (rides_the_outline(problem.parts[part])) continue;
        const Box box = gate_at(problem, part, kernel.placement()[part]);
        extent = extent ? united(*extent, box) : box;
    }
    return extent ? *extent : kernel.board().outline();
}

bool rehome(Kernel& kernel, const std::vector<std::size_t>& members) {
    const Problem& problem = kernel.problem();
    const bool held = std::any_of(members.begin(), members.end(), [&](std::size_t part) {
        return problem.parts[part].fixed || rides_the_outline(problem.parts[part]);
    });
    if (held) return false;
    const auto nearest = [](const Box&) -> std::optional<double> { return 0.0; };
    return seat_block(kernel, {as_placed(kernel, members)}, kernel.board().outline(), nearest, false,
                      static_cast<std::size_t>(constants::rehome_tries.value), nullptr,
                      static_cast<Nm>(constants::rehome_pitch.value));
}

std::string extent_holders(const Kernel& kernel) {
    const Problem& problem = kernel.problem();
    const Box extent = held_extent(kernel);
    std::array<std::string, edge_count> names;
    for (std::size_t part = 0; part < problem.parts.size(); ++part) {
        if (rides_the_outline(problem.parts[part])) continue;
        const Box box = gate_at(problem, part, kernel.placement()[part]);
        const std::string label = problem.parts[part].reference + (problem.parts[part].fixed ? " (fixed)" : "");
        if (box.y0 == extent.y0) names[0] = label;
        if (box.y1 == extent.y1) names[1] = label;
        if (box.x0 == extent.x0) names[2] = label;
        if (box.x1 == extent.x1) names[3] = label;
    }
    std::string text;
    for (std::size_t index = 0; index < edge_count; ++index)
        text += std::string(index ? ", " : "") + side_name(sides[index]) + " " +
                (names[index].empty() ? "the module" : names[index]);
    return text;
}

LayReport lay_out(Kernel& kernel) {
    LayReport report;
    const Problem& problem = kernel.problem();
    const Snapshot start = kernel.snapshot();
    std::vector<char> tapped(problem.parts.size(), 0);
    for (const Tap& rule : problem.constraints.taps) tapped[rule.part] = 1;
    std::vector<Cluster> clusters;
    for (Cluster& cluster : clusters_of(kernel)) {
        if (!std::all_of(cluster.members.begin(), cluster.members.end(), [&](std::size_t part) { return kernel.releasable(part); })) continue;
        if (std::all_of(cluster.members.begin(), cluster.members.end(), [&](std::size_t part) { return tapped[part] != 0; })) {
            for (const std::size_t part : cluster.members) kernel.park(part);
            report.deferred += cluster.members.size();
            continue;
        }
        clusters.push_back(std::move(cluster));
    }
    for (bool changed = true; changed;) {
        changed = false;
        std::vector<int> home(problem.parts.size(), -1);
        for (std::size_t index = 0; index < clusters.size(); ++index)
            for (const std::size_t part : clusters[index].members) home[part] = static_cast<int>(index);
        std::vector<char> satellite(clusters.size(), 0);
        const auto bound_to = [&](std::size_t anchor, std::size_t member) {
            if (home[member] >= 0 && home[anchor] < 0 && !kernel.parked(anchor)) satellite[static_cast<std::size_t>(home[member])] = 1;
        };
        for (const PadGap& rule : problem.constraints.pad_gaps) bound_to(rule.anchor, rule.member);
        for (const PadGap& rule : problem.constraints.soft_gaps) bound_to(rule.anchor, rule.member);
        for (const NearestGap& rule : problem.constraints.nearest_gaps)
            for (const std::size_t member : rule.members) bound_to(rule.anchor, member);
        for (const NetOrder& rule : problem.constraints.net_orders) bound_to(rule.anchor, rule.lead);
        std::vector<Cluster> kept;
        for (std::size_t index = 0; index < clusters.size(); ++index) {
            if (satellite[index]) changed = true;
            else kept.push_back(std::move(clusters[index]));
        }
        clusters = std::move(kept);
    }
    report.routed_before = kernel.routed_length();
    report.pulled_before = kernel.pulled_length();
    report.clusters = clusters.size();
    if (clusters.empty()) {
        kernel.restore(start);
        return report;
    }
    std::vector<Block> blocks;
    std::vector<int> cluster_of(problem.parts.size(), -1);
    for (std::size_t index = 0; index < clusters.size(); ++index) {
        blocks.push_back(as_placed(kernel, clusters[index].members));
        for (const std::size_t part : clusters[index].members) cluster_of[part] = static_cast<int>(index);
    }
    struct Sheet {
        std::string name;
        std::vector<std::size_t> clusters;
        double pull = 0;
    };
    std::vector<Sheet> sheets;
    std::map<std::string, std::size_t> sheet_index;
    for (std::size_t index = 0; index < clusters.size(); ++index) {
        const auto found = sheet_index.emplace(clusters[index].sheet, sheets.size());
        if (found.second) sheets.push_back({clusters[index].sheet, {}, 0});
        sheets[found.first->second].clusters.push_back(index);
    }
    for (const Net& net : problem.nets) {
        if (net.category == Category::plane) continue;
        const bool anchored = std::any_of(net.pins.begin(), net.pins.end(), [&](const Pin& pin) { return cluster_of[pin.part] < 0; });
        if (!anchored) continue;
        std::vector<std::size_t> touched;
        for (const Pin& pin : net.pins)
            if (cluster_of[pin.part] >= 0) touched.push_back(sheet_index.at(clusters[static_cast<std::size_t>(cluster_of[pin.part])].sheet));
        std::sort(touched.begin(), touched.end());
        touched.erase(std::unique(touched.begin(), touched.end()), touched.end());
        for (const std::size_t sheet : touched) sheets[sheet].pull += net.pull;
    }
    std::stable_sort(sheets.begin(), sheets.end(), [](const Sheet& a, const Sheet& b) { return a.pull != b.pull ? a.pull > b.pull : a.name < b.name; });
    for (const Cluster& cluster : clusters)
        for (const std::size_t part : cluster.members) kernel.park(part);
    struct Want {
        double x = 0, y = 0, pull = 0;
    };
    const auto want_of = [&](std::size_t index) {
        Want want;
        for (const Net& net : problem.nets) {
            if (net.category == Category::plane) continue;
            bool touches = false;
            std::size_t present = 0;
            for (const Pin& pin : net.pins) {
                if (cluster_of[pin.part] == static_cast<int>(index)) touches = true;
                else if (!kernel.parked(pin.part)) ++present;
            }
            if (!touches || present == 0) continue;
            for (const Pin& pin : net.pins) {
                if (cluster_of[pin.part] == static_cast<int>(index) || kernel.parked(pin.part)) continue;
                const Pose& pose = kernel.placement()[pin.part];
                const Point at = placed(problem.footprints[problem.parts[pin.part].footprint].on(pose.face).pads[pin.pad].centre, pose.at, pose.turn);
                const double share = static_cast<double>(net.pull) / static_cast<double>(present);
                want.x += share * static_cast<double>(at.x);
                want.y += share * static_cast<double>(at.y);
                want.pull += share;
            }
        }
        if (want.pull > 0) {
            want.x /= want.pull;
            want.y /= want.pull;
        }
        return want;
    };
    const Box outline = kernel.board().outline();
    const std::optional<Box> body = kernel.board().module_body;
    const Nm coarse = static_cast<Nm>(constants::arrange_pitch.value);
    std::vector<std::optional<std::size_t>> tied_to(clusters.size());
    const auto seat_near = [&](std::size_t index, Want want, bool anywhere, const std::function<bool()>& accept = {}) {
        const Block& block = blocks[index];
        const bool tied = tied_to[index] && !kernel.parked(*tied_to[index]);
        const Nm pitch = tied ? static_cast<Nm>(constants::search_pitch.value) : coarse;
        const Nm reach = static_cast<Nm>(constants::construct_reach.value);
        if (tied) {
            const Point at = kernel.placement()[*tied_to[index]].at;
            want = {static_cast<double>(at.x), static_cast<double>(at.y), want.pull};
        }
        std::vector<Option> options = options_of(kernel, block, pitch);
        if (std::any_of(block.members.begin(), block.members.end(), [&](std::size_t part) { return !problem.parts[part].via_sites.empty(); })) options.resize(1);
        struct Try {
            double away = 0;
            std::size_t option = 0;
            Point by;
        };
        std::vector<Try> tries;
        for (std::size_t choice = 0; choice < options.size(); ++choice) {
            const Option& option = options[choice];
            const Nm first_x = (outline.x0 - option.swept.x0) / pitch, last_x = (outline.x1 - option.swept.x1) / pitch;
            const Nm first_y = (outline.y0 - option.swept.y0) / pitch, last_y = (outline.y1 - option.swept.y1) / pitch;
            for (Nm column = first_x; column <= last_x; ++column)
                for (Nm row = first_y; row <= last_y; ++row) {
                    const Point by{column * pitch, row * pitch};
                    const Box swept = shifted(option.swept, by);
                    if (!inside(swept, outline)) continue;
                    if (tied && !anywhere &&
                        std::hypot(static_cast<double>(swept.x0 + swept.x1) / 2 - want.x, static_cast<double>(swept.y0 + swept.y1) / 2 - want.y) > static_cast<double>(reach))
                        continue;
                    if (body && std::any_of(option.top_boxes.begin(), option.top_boxes.end(), [&](const Box& box) { return overlaps(shifted(box, by), *body); }))
                        continue;
                    tries.push_back({std::hypot(static_cast<double>(swept.x0 + swept.x1) / 2 - want.x, static_cast<double>(swept.y0 + swept.y1) / 2 - want.y), choice, by});
                }
        }
        std::sort(tries.begin(), tries.end(), [](const Try& a, const Try& b) {
            if (a.away != b.away) return a.away < b.away;
            if (a.option != b.option) return a.option < b.option;
            return a.by.x != b.by.x ? a.by.x < b.by.x : a.by.y < b.by.y;
        });
        const std::size_t limit = anywhere || tied ? tries.size() : std::min(tries.size(), static_cast<std::size_t>(constants::lay_tries.value));
        for (std::size_t attempt = 0; attempt < limit; ++attempt) {
            const std::vector<Move> moves = moves_of(block, options[tries[attempt].option], tries[attempt].by);
            if (!kernel.seat_together(moves)) continue;
            const bool clear = std::none_of(moves.begin(), moves.end(), [&](const Move& move) { return kernel.covers_via_sites(move.part); });
            if (clear && (!accept || accept())) return true;
            for (const Move& move : moves) kernel.park(move.part);
        }
        return false;
    };
    const auto fallback_of = [&](const Sheet& sheet, std::size_t index) {
        const Box home = body ? *body : outline;
        Want want{static_cast<double>(home.x0 + home.x1) / 2, static_cast<double>(home.y0 + home.y1) / 2, 0};
        for (const std::size_t mate : sheet.clusters)
            if (mate != index && !kernel.parked(clusters[mate].members.front())) {
                const Box hull = hull_of(kernel, clusters[mate].members);
                return Want{static_cast<double>(hull.x0 + hull.x1) / 2, static_cast<double>(hull.y0 + hull.y1) / 2, 0};
            }
        return want;
    };
    constexpr int untied = -2, held = -1;
    std::vector<int> leader(clusters.size(), untied);
    const auto tie = [&](std::size_t anchor, std::size_t member) {
        const int mine = cluster_of[member];
        if (mine < 0 || cluster_of[anchor] == mine || leader[static_cast<std::size_t>(mine)] != untied) return;
        leader[static_cast<std::size_t>(mine)] = cluster_of[anchor] < 0 ? held : cluster_of[anchor];
        tied_to[static_cast<std::size_t>(mine)] = anchor;
    };
    for (const PadGap& rule : problem.constraints.pad_gaps) tie(rule.anchor, rule.member);
    for (const PadGap& rule : problem.constraints.soft_gaps) tie(rule.anchor, rule.member);
    for (const NearestGap& rule : problem.constraints.nearest_gaps)
        for (const std::size_t member : rule.members) tie(rule.anchor, member);
    for (const NetOrder& rule : problem.constraints.net_orders) tie(rule.anchor, rule.lead);
    std::vector<std::size_t> order, sheet_of(clusters.size(), 0);
    std::vector<char> listed(clusters.size(), 0);
    const std::function<void(std::size_t)> list = [&](std::size_t index) {
        if (listed[index]) return;
        listed[index] = 1;
        order.push_back(index);
        for (std::size_t follower = 0; follower < clusters.size(); ++follower)
            if (leader[follower] == static_cast<int>(index)) list(follower);
    };
    for (std::size_t sheet = 0; sheet < sheets.size(); ++sheet)
        for (const std::size_t index : sheets[sheet].clusters) sheet_of[index] = sheet;
    for (const Sheet& sheet : sheets)
        for (const std::size_t index : sheet.clusters)
            if (leader[index] == held) list(index);
    for (const Sheet& sheet : sheets)
        for (const std::size_t index : sheet.clusters) list(index);
    const auto gathered = [&](std::size_t index, Want want) {
        std::vector<std::size_t> mates;
        for (const std::size_t mate : sheets[sheet_of[index]].clusters)
            if (mate != index && !kernel.parked(clusters[mate].members.front()))
                mates.insert(mates.end(), clusters[mate].members.begin(), clusters[mate].members.end());
        if (mates.empty()) return want;
        const Box hull = hull_of(kernel, mates);
        const double share = constants::lay_gather.value;
        want.x = want.x * (1 - share) + share * static_cast<double>(hull.x0 + hull.x1) / 2;
        want.y = want.y * (1 - share) + share * static_cast<double>(hull.y0 + hull.y1) / 2;
        return want;
    };
    const auto put_back = [&](std::size_t index) {
        const Block& block = blocks[index];
        std::vector<Move> moves;
        for (std::size_t member = 0; member < block.members.size(); ++member) moves.push_back({block.members[member], block.base[member]});
        return kernel.seat_together(moves);
    };
    const auto waits = [&](std::size_t index) { return kernel.parked(clusters[index].members.front()); };
    const std::function<bool(std::size_t)> followed = [&](std::size_t index) {
        std::vector<std::size_t> placed_now;
        for (std::size_t follower = 0; follower < clusters.size(); ++follower) {
            if (leader[follower] != static_cast<int>(index) || sheet_of[follower] != sheet_of[index] || !waits(follower)) continue;
            if (seat_near(follower, want_of(follower), false, [&] { return followed(follower); })) {
                placed_now.push_back(follower);
                continue;
            }
            for (const std::size_t undo : placed_now)
                for (const std::size_t part : clusters[undo].members)
                    if (!kernel.parked(part)) kernel.park(part);
            return false;
        }
        return true;
    };
    const auto seat_by_plan = [&](std::size_t index) {
        Want want = want_of(index);
        if (want.pull == 0) want = fallback_of(sheets[sheet_of[index]], index);
        else want = gathered(index, want);
        if (seat_near(index, want, false, [&] { return followed(index); })) return true;
        return seat_near(index, want, true, [&] { return followed(index); });
    };
    const Snapshot lifted = kernel.snapshot();
    std::vector<std::size_t> turn(sheets.size());
    std::iota(turn.begin(), turn.end(), std::size_t{0});
    for (std::size_t round = 0; round < static_cast<std::size_t>(constants::lay_rounds.value); ++round) {
    kernel.restore(lifted);
    report.unseated.clear();
    std::vector<std::size_t> failed;
    for (const std::size_t sheet : turn) {
        const Snapshot before = kernel.snapshot();
        bool whole = true;
        for (const bool tied_first : {true, false})
            for (const std::size_t index : order) {
                if (!whole || sheet_of[index] != sheet || !waits(index) || (leader[index] == held) != tied_first) continue;
                if (!seat_by_plan(index)) whole = false;
            }
        if (whole) continue;
        kernel.restore(before);
        bool back = true;
        for (const std::size_t index : sheets[sheet].clusters)
            if (waits(index) && !put_back(index)) back = false;
        if (back) continue;
        kernel.restore(before);
        report.unseated.push_back(sheets[sheet].name + " (no place by plan and its own place is taken)");
        failed.push_back(sheet);
    }
    report.rounds = round + 1;
    if (failed.empty()) break;
    std::vector<std::size_t> next = failed;
    for (const std::size_t sheet : turn)
        if (std::find(failed.begin(), failed.end(), sheet) == failed.end()) next.push_back(sheet);
    if (next == turn) break;
    turn = std::move(next);
    }
    for (std::size_t index = 0; index < clusters.size(); ++index) {
        if (waits(index)) continue;
        const Pose& now = kernel.placement()[clusters[index].members.front()];
        const Pose& was = blocks[index].base.front();
        if (now.at == was.at && now.turn == was.turn && now.face == was.face) ++report.returned;
        else ++report.seated;
    }
    report.routed_after = kernel.routed_length();
    report.pulled_after = kernel.pulled_length();
    report.taken = report.unseated.empty() && report.pulled_after < report.pulled_before;
    if (!report.taken) kernel.restore(start);
    return report;
}

DrawReport draw_in(Kernel& kernel) {
    DrawReport report;
    report.routed_before = kernel.routed_length();
    report.pulled_before = kernel.pulled_length();
    const Problem& problem = kernel.problem();
    const std::vector<Cluster> clusters = clusters_of(kernel);
    report.clusters = clusters.size();
    struct Want {
        double x = 0, y = 0, pull = 0;
    };
    const auto want_of = [&](const std::vector<char>& inside) {
        Want want;
        for (const Net& net : problem.nets) {
            if (net.category == Category::plane) continue;
            bool touches = false;
            std::size_t outside = 0;
            for (const Pin& pin : net.pins) (inside[pin.part] ? touches = true : ++outside);
            if (!touches || outside == 0) continue;
            for (const Pin& pin : net.pins) {
                if (inside[pin.part]) continue;
                const Pose& pose = kernel.placement()[pin.part];
                const Point at = placed(problem.footprints[problem.parts[pin.part].footprint].on(pose.face).pads[pin.pad].centre, pose.at, pose.turn);
                const double share = static_cast<double>(net.pull) / static_cast<double>(outside);
                want.x += share * static_cast<double>(at.x);
                want.y += share * static_cast<double>(at.y);
                want.pull += share;
            }
        }
        if (want.pull > 0) {
            want.x /= want.pull;
            want.y /= want.pull;
        }
        return want;
    };
    const auto away = [](const Box& box, const Want& want) {
        return std::hypot(static_cast<double>(box.x0 + box.x1) / 2 - want.x, static_cast<double>(box.y0 + box.y1) / 2 - want.y);
    };
    for (std::size_t round = 0; round < static_cast<std::size_t>(constants::draw_rounds.value); ++round) {
        std::vector<std::pair<Want, const Cluster*>> order;
        for (const Cluster& cluster : clusters) {
            std::vector<char> inside(problem.parts.size(), 0);
            for (const std::size_t part : cluster.members) inside[part] = 1;
            const Want want = want_of(inside);
            if (want.pull > 0) order.emplace_back(want, &cluster);
        }
        std::stable_sort(order.begin(), order.end(), [](const auto& a, const auto& b) { return a.first.pull > b.first.pull; });
        std::size_t moved = 0;
        for (const auto& [stale, cluster] : order) {
            std::vector<char> inside(problem.parts.size(), 0);
            for (const std::size_t part : cluster->members) inside[part] = 1;
            const Want want = want_of(inside);
            const double now = away(hull_of(kernel, cluster->members), want);
            if (now < constants::draw_slack.value) continue;
            const Nm before = kernel.pulled_length();
            const Snapshot kept = kernel.snapshot();
            std::vector<std::size_t> sheet;
            for (std::size_t part = 0; part < problem.parts.size(); ++part)
                if (problem.parts[part].group == cluster->sheet && !rides_the_outline(problem.parts[part]) && !problem.parts[part].fixed &&
                    problem.parts[part].cohesion_member)
                    sheet.push_back(part);
            const auto extent = [&] {
                if (sheet.empty()) return 0.0;
                const Box hull = hull_of(kernel, sheet);
                return static_cast<double>(hull.x1 - hull.x0) * static_cast<double>(hull.y1 - hull.y0);
            };
            const double held = extent();
            const auto rank = [&](const Box& swept) -> std::optional<double> {
                const double then = away(swept, want);
                if (then >= now) return std::nullopt;
                return then;
            };
            const std::size_t covering = static_cast<std::size_t>(
                std::count_if(cluster->members.begin(), cluster->members.end(), [&](std::size_t part) { return kernel.covers_via_sites(part); }));
            if (seat_block(kernel, {as_placed(kernel, cluster->members)}, kernel.board().outline(), rank, true,
                           static_cast<std::size_t>(constants::draw_tries.value), nullptr) &&
                kernel.pulled_length() < before && extent() <= held &&
                static_cast<std::size_t>(std::count_if(cluster->members.begin(), cluster->members.end(),
                                                       [&](std::size_t part) { return kernel.covers_via_sites(part); })) <= covering)
                ++moved;
            else
                kernel.restore(kept);
        }
        report.moved += moved;
        ++report.rounds;
        if (moved == 0) break;
    }
    report.routed_after = kernel.routed_length();
    report.pulled_after = kernel.pulled_length();
    return report;
}

ArrangeReport arrange(Kernel& kernel, const SqueezeOptions& options, const std::function<void()>& settle) {
    ArrangeReport report;
    report.before = held_extent(kernel);
    if (!kernel.board().module_body) return report;
    const std::vector<Cluster> clusters = clusters_of(kernel);
    report.clusters = clusters.size();
    const Snapshot start = kernel.snapshot();
    const auto squeezed = [&](const Snapshot& from) {
        kernel.restore(from);
        if (settle) settle();
        const SqueezeReport result = squeeze(kernel, options);
        return to_mm(result.after.width) * to_mm(result.after.height);
    };
    const Problem& problem = kernel.problem();
    std::vector<char> movable(problem.parts.size(), 0);
    for (const Cluster& cluster : clusters)
        for (const std::size_t part : cluster.members) movable[part] = 1;
    const Box outline = kernel.board().outline();
    const Box body = *kernel.board().module_body;
    std::array<bool, edge_count> anchored{};
    for (std::size_t index = 0; index < edge_count; ++index) {
        const Box zone = beyond(outline, body, sides[index]);
        for (std::size_t part = 0; part < problem.parts.size() && !anchored[index]; ++part)
            anchored[index] = !movable[part] && !rides_the_outline(problem.parts[part]) &&
                              overlaps(gate_at(problem, part, kernel.placement()[part]), zone);
        if (anchored[index]) report.anchored_sides += std::string(report.anchored_sides.empty() ? "" : ", ") + side_name(sides[index]);
    }
    const auto started = std::chrono::steady_clock::now();
    std::vector<Snapshot> states;
    const std::size_t plans = std::size_t{1} << edge_count;
    for (std::size_t mask = 1; mask < plans; ++mask) {
        std::array<bool, edge_count> kept{};
        bool sound = true;
        for (std::size_t index = 0; index < edge_count; ++index) {
            kept[index] = (mask >> index & 1) != 0;
            sound = sound && (kept[index] || !anchored[index]);
        }
        if (!sound) continue;
        kernel.restore(start);
        const Nm widened = make_room(kernel, options, clusters, kept);
        if (widened == 0) kernel.restore(start);
        ArrangePlan plan = evacuate(kernel, clusters, kept);
        plan.widened = widened;
        plan.tightened = tighten(kernel, clusters);
        plan.span = held_extent(kernel);
        plan.routed = kernel.routed_length();
        report.plans.push_back(std::move(plan));
        states.push_back(kernel.snapshot());
    }
    const auto arranged = std::chrono::steady_clock::now();
    report.plan_seconds = std::chrono::duration<double>(arranged - started).count();
    const bool unchanged = std::all_of(report.plans.begin(), report.plans.end(), [](const ArrangePlan& plan) {
        return plan.moved == 0 && plan.tightened == 0;
    });
    if (unchanged) {
        kernel.restore(start);
        report.holders = extent_holders(kernel);
        return report;
    }
    std::vector<std::size_t> ranked(report.plans.size());
    for (std::size_t index = 0; index < ranked.size(); ++index) ranked[index] = index;
    std::stable_sort(ranked.begin(), ranked.end(), [&](std::size_t a, std::size_t b) {
        return area_mm2(report.plans[a].span) < area_mm2(report.plans[b].span);
    });
    report.unarranged = squeezed(start);
    double best = report.unarranged;
    Snapshot kept_state = start;
    const std::size_t skip = ranked.empty() ? 0 : options.plan_skip % ranked.size();
    const std::size_t finalists = std::min(ranked.size(), skip + static_cast<std::size_t>(constants::arrange_finalists.value));
    for (std::size_t place = skip; place < finalists; ++place) {
        ArrangePlan& plan = report.plans[ranked[place]];
        plan.squeezed = squeezed(states[ranked[place]]);
        if (plan.squeezed >= best) continue;
        best = plan.squeezed;
        report.chosen = ranked[place] + 1;
        kept_state = states[ranked[place]];
    }
    report.squeeze_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - arranged).count();
    kernel.restore(kept_state);
    report.holders = extent_holders(kernel);
    return report;
}

}
