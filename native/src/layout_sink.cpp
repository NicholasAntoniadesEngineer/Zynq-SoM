#include "schgen/layout_sink.hpp"

#include <algorithm>
#include <limits>

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

double area_of(Box box) { return to_mm(box.width()) * to_mm(box.height()); }

}

BalanceReport balance_faces(Kernel& kernel, Nm pitch, Nm reach) {
    const Problem& problem = kernel.problem();
    const std::size_t count = problem.parts.size();
    std::vector<std::size_t> parent(count);
    for (std::size_t part = 0; part < count; ++part) parent[part] = part;
    const auto root = [&](std::size_t part) {
        while (parent[part] != part) part = parent[part] = parent[parent[part]];
        return part;
    };
    const auto join = [&](std::size_t first, std::size_t second) {
        const std::size_t a = root(first), b = root(second);
        if (a != b) parent[std::max(a, b)] = std::min(a, b);
    };
    for (const auto& rule : problem.constraints.nearest_gaps)
        if (rule.same_face)
            for (const std::size_t member : rule.members) join(rule.anchor, member);
    for (const auto& rule : problem.constraints.face_pairs) join(rule.first, rule.second);
    for (const auto& reserve : problem.reserves)
        for (const std::size_t member : reserve.members) join(reserve.members.front(), member);
    std::vector<std::vector<std::size_t>> sets(count);
    for (std::size_t part = 0; part < count; ++part) sets[root(part)].push_back(part);
    BalanceReport report;
    const auto face_area = [&](Face face) {
        double total = 0;
        for (std::size_t part = 0; part < count; ++part)
            if (kernel.placement()[part].face == face) total += area_of(gate_at(problem, part, kernel.placement()[part]));
        return total;
    };
    report.top_before = face_area(Face::top);
    report.rear_before = face_area(Face::bottom);
    double top = report.top_before, rear = report.rear_before;
    struct Candidate {
        std::size_t lead = 0;
        double area = 0;
    };
    std::vector<Candidate> candidates;
    for (std::size_t lead = 0; lead < count; ++lead) {
        const auto& members = sets[lead];
        if (members.empty()) continue;
        const bool movable = std::all_of(members.begin(), members.end(), [&](std::size_t part) {
            return may_sink(problem, kernel.placement(), part) &&
                   mirrors_across_x(problem.footprints[problem.parts[part].footprint]).has_value();
        });
        if (!movable) continue;
        double area = 0;
        for (const std::size_t part : members) area += area_of(gate_at(problem, part, kernel.placement()[part]));
        candidates.push_back({lead, area});
    }
    std::stable_sort(candidates.begin(), candidates.end(),
                     [](const Candidate& a, const Candidate& b) { return a.area > b.area; });
    report.sets = candidates.size();
    const std::vector<Point> offsets = seat_ring(pitch, reach, {0, 0});
    for (const auto& candidate : candidates) {
        if (rear + candidate.area > top - candidate.area) continue;
        const auto& members = sets[candidate.lead];
        Box hull = gate_at(problem, members.front(), kernel.placement()[members.front()]);
        for (const std::size_t part : members) hull = united(hull, gate_at(problem, part, kernel.placement()[part]));
        std::size_t along_x = 0, along_y = 0;
        for (const std::size_t part : members) {
            const Part& item = problem.parts[part];
            if (!item.edge) continue;
            const Pose& pose = kernel.placement()[part];
            (turned(item.edge->mouth_on(pose.face), pose.turn).x != 0 ? along_x : along_y) += 1;
        }
        if (along_x != 0 && along_y != 0) continue;
        const bool about_x = along_x == 0;
        const Nm pivot = about_x ? hull.x0 + hull.x1 : hull.y0 + hull.y1;
        std::vector<Move> mirror;
        for (const std::size_t part : members) {
            const Pose& from = kernel.placement()[part];
            const bool across_x = *mirrors_across_x(problem.footprints[problem.parts[part].footprint]);
            const int back = (turn_count - static_cast<int>(from.turn) + (across_x == about_x ? 0 : 2)) % turn_count;
            const Point at = about_x ? Point{pivot - from.at.x, from.at.y} : Point{from.at.x, pivot - from.at.y};
            mirror.push_back({part, {at, static_cast<Turn>(back), Face::bottom}});
        }
        bool flipped = false;
        for (const Point by : offsets) {
            std::vector<Move> moves = mirror;
            for (auto& move : moves) move.pose.at = shifted(move.pose.at, by);
            if (std::any_of(moves.begin(), moves.end(), [&](const Move& move) {
                    return crowds_escape(problem, kernel.placement(), move.part, move.pose);
                }))
                continue;
            if (kernel.move_many(moves)) {
                flipped = true;
                break;
            }
        }
        if (!flipped) continue;
        ++report.flipped;
        report.parts += members.size();
        top -= candidate.area;
        rear += candidate.area;
    }
    report.top_after = face_area(Face::top);
    report.rear_after = face_area(Face::bottom);
    return report;
}

AttractReport attract(Kernel& kernel, Nm pitch, Nm reach) {
    const Problem& problem = kernel.problem();
    AttractReport report;
    report.routed_before = kernel.routed_length();
    const std::vector<Point> offsets = seat_ring(pitch, reach, {0, 0});
    const auto met = [&](const PadGap& rule) {
        return squared_pad_gap(problem, rule, kernel.placement()[rule.anchor], kernel.placement()[rule.member]) <=
               squared(rule.limit);
    };
    for (const auto& rule : problem.constraints.soft_gaps) {
        if (rule.sense != Sense::at_most) continue;
        if (met(rule)) {
            ++report.met_before;
            continue;
        }
        ++report.wanted;
        const std::size_t part = rule.member;
        const Pose from = kernel.placement()[part];
        const Nm before = squared_pad_gap(problem, rule, kernel.placement()[rule.anchor], from);
        std::vector<Box> pins = named_boxes(problem, rule.anchor, kernel.placement()[rule.anchor], rule.anchor_names);
        if (pins.empty()) continue;
        Box pin = pins.front();
        for (const auto& box : pins) pin = united(pin, box);
        const Point target{(pin.x0 + pin.x1) / 2, (pin.y0 + pin.y1) / 2};
        const bool flips = may_sink(problem, kernel.placement(), part) || from.face == Face::bottom;
        bool seated = false;
        for (const Point by : offsets) {
            for (const Face face : {Face::bottom, Face::top}) {
                if (face != from.face && !flips) continue;
                for (int turn = 0; turn < turn_count && !seated; ++turn) {
                    const Pose pose{shifted(target, by), static_cast<Turn>(turn), face};
                    if (squared_pad_gap(problem, rule, kernel.placement()[rule.anchor], pose) >= before) continue;
                    if (crowds_escape(problem, kernel.placement(), part, pose)) continue;
                    if (kernel.rejection(part, pose)) continue;
                    seated = kernel.move(part, pose);
                }
                if (seated) break;
            }
            if (seated) break;
        }
        if (!seated) continue;
        ++report.seated;
        if (from.face == Face::top && kernel.placement()[part].face == Face::bottom) ++report.to_rear;
    }
    report.met_after = static_cast<std::size_t>(std::count_if(
        problem.constraints.soft_gaps.begin(), problem.constraints.soft_gaps.end(),
        [&](const PadGap& rule) { return rule.sense == Sense::at_most && met(rule); }));
    report.routed_after = kernel.routed_length();
    return report;
}

}
