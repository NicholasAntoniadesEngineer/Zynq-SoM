#include "schgen/layout_squeeze.hpp"

#include "schgen/layout_sink.hpp"

#include <algorithm>
#include <deque>
#include <numeric>

namespace schgen::layout {
namespace {

Point inward(Side side) {
    switch (side) {
    case Side::north: return {0, 1};
    case Side::south: return {0, -1};
    case Side::west: return {1, 0};
    case Side::east: break;
    }
    return {-1, 0};
}

Board shrunk(Board board, Side side, Nm step) {
    const Point in = inward(side);
    if (in.x > 0) board.origin.x += step;
    if (in.y > 0) board.origin.y += step;
    if (in.x != 0) board.width -= step;
    else board.height -= step;
    return board;
}

Side facing(const Part& part, const Pose& pose) {
    const Point out = turned(part.edge->mouth_on(pose.face), pose.turn);
    if (out.y < 0) return Side::north;
    if (out.y > 0) return Side::south;
    return out.x < 0 ? Side::west : Side::east;
}

std::vector<Point> ring(Nm pitch, Nm reach, Point in) {
    std::vector<Point> offsets;
    const Nm count = reach / pitch;
    for (Nm column = -count; column <= count; ++column)
        for (Nm row = -count; row <= count; ++row)
            if ((column != 0 || row != 0) && squared(column) + squared(row) <= squared(count))
                offsets.push_back({column * pitch, row * pitch});
    std::sort(offsets.begin(), offsets.end(), [&](Point a, Point b) {
        const Nm far_a = squared(a.x) + squared(a.y), far_b = squared(b.x) + squared(b.y);
        if (far_a != far_b) return far_a < far_b;
        const Nm along_a = a.x * in.x + a.y * in.y, along_b = b.x * in.x + b.y * in.y;
        if (along_a != along_b) return along_a > along_b;
        return a.x != b.x ? a.x < b.x : a.y < b.y;
    });
    return offsets;
}

class Squeezer {
public:
    Squeezer(Kernel& kernel, const SqueezeOptions& options)
        : kernel_(kernel), problem_(kernel.problem()), options_(options), bundles_(bundle(problem_)) {}

    SqueezeReport run() {
        if (options_.pitch <= 0 || options_.last_step <= 0 || options_.first_step < options_.last_step ||
            options_.rounds == 0)
            throw LayoutError("layout: squeeze options are not usable");
        if (!kernel_.outline_holds()) throw LayoutError("layout: the starting outline loses the module or fixed copper");
        SqueezeReport report;
        report.before = kernel_.board();
        report.routed_before = kernel_.routed_length();
        if (!kernel_.violations().empty()) {
            Attempt repair;
            settled_.assign(bundles_.units.size(), 0);
            repair.kept = settle(repair);
            if (!repair.kept)
                throw LayoutError("layout: the starting placement cannot be made legal: " + repair.blocker);
            report.attempts.push_back(std::move(repair));
        }
        const auto ratio = static_cast<Nm>(constants::step_ratio.value);
        for (Nm step = options_.first_step; step >= options_.last_step; step /= ratio) {
            bool progress = true;
            while (progress) {
                progress = false;
                for (const bool along_x : {true, false}) report.fallen += fall(along_x);
                for (const bool along_x : {true, false}) {
                    Attempt attempt;
                    attempt.step = step;
                    attempt.scaled = true;
                    attempt.along_x = along_x;
                    attempt.kept = take_scale(attempt);
                    progress = progress || attempt.kept;
                    report.attempts.push_back(std::move(attempt));
                }
                for (const Side side : options_.order) {
                    Attempt attempt;
                    attempt.side = side;
                    attempt.step = step;
                    attempt.kept = take_step(attempt);
                    progress = progress || attempt.kept;
                    report.attempts.push_back(std::move(attempt));
                }
            }
        }
        report.after = kernel_.board();
        report.routed_after = kernel_.routed_length();
        return report;
    }

private:
    bool take_step(Attempt& attempt) {
        const Board board = shrunk(kernel_.board(), attempt.side, attempt.step);
        if (board.width <= 0 || board.height <= 0) {
            attempt.blocker = "the outline has no area left";
            return false;
        }
        const Snapshot before = kernel_.snapshot();
        kernel_.set_board(board);
        const bool kept = carry_edge(attempt) && settle(attempt);
        if (!kept) kernel_.restore(before);
        return kept;
    }

    Nm pivot_of(bool along_x) const {
        const Box outline = kernel_.board().outline();
        const auto& core = kernel_.board().module_core;
        if (core) return (along_x ? core->x0 + core->x1 : core->y0 + core->y1) / 2;
        return (along_x ? outline.x0 + outline.x1 : outline.y0 + outline.y1) / 2;
    }

    std::size_t fall(bool along_x) {
        const Nm pivot = pivot_of(along_x);
        const Side low_side = along_x ? Side::west : Side::north, high_side = along_x ? Side::east : Side::south;
        struct Faller {
            std::size_t unit = 0;
            Nm centre = 0;
        };
        std::vector<Faller> fallers;
        for (std::size_t unit = 0; unit < bundles_.units.size(); ++unit) {
            const auto& members = bundles_.units[unit];
            if (problem_.parts[members.front()].fixed) continue;
            bool held = false;
            Box hull = gate_at(problem_, members.front(), kernel_.placement()[members.front()]);
            for (const std::size_t member : members) {
                const Part& item = problem_.parts[member];
                const Pose& pose = kernel_.placement()[member];
                hull = united(hull, gate_at(problem_, member, pose));
                held = held || (item.edge && (facing(item, pose) == low_side || facing(item, pose) == high_side));
            }
            if (!held) fallers.push_back({unit, along_x ? (hull.x0 + hull.x1) / 2 : (hull.y0 + hull.y1) / 2});
        }
        std::stable_sort(fallers.begin(), fallers.end(), [&](const Faller& a, const Faller& b) {
            const Nm far_a = a.centre < pivot ? pivot - a.centre : a.centre - pivot;
            const Nm far_b = b.centre < pivot ? pivot - b.centre : b.centre - pivot;
            return far_a < far_b;
        });
        std::size_t moved = 0;
        for (const auto& faller : fallers) {
            const Nm reach = faller.centre < pivot ? pivot - faller.centre : faller.centre - pivot;
            const Nm step = faller.centre < pivot ? options_.pitch : -options_.pitch;
            for (Nm gone = options_.pitch; gone <= reach; gone += options_.pitch) {
                if (!kernel_.move_many(carried(faller.unit, along_x ? Point{step, 0} : Point{0, step}))) break;
                ++moved;
            }
        }
        return moved;
    }

    bool take_scale(Attempt& attempt) {
        const Board old = kernel_.board();
        const Box outline = old.outline();
        const bool along_x = attempt.along_x;
        const Nm low = along_x ? outline.x0 : outline.y0, high = along_x ? outline.x1 : outline.y1;
        const Nm pivot = pivot_of(along_x);
        const Nm span = std::max(pivot - low, high - pivot);
        if (pivot <= low || pivot >= high) {
            attempt.blocker = "the outline no longer surrounds its centre";
            return false;
        }
        const auto shift_of = [&](Nm coordinate) {
            const Nm distance = coordinate - pivot;
            const Nm reach = distance < 0 ? -distance : distance;
            const Nm moved = reach * attempt.step / span / options_.pitch * options_.pitch;
            return distance < 0 ? moved : -moved;
        };
        const Nm low_shift = shift_of(low), high_shift = shift_of(high);
        if (low_shift == 0 && high_shift == 0) {
            attempt.blocker = "the step is below the search pitch";
            return false;
        }
        Board board = old;
        (along_x ? board.origin.x : board.origin.y) += low_shift;
        (along_x ? board.width : board.height) += high_shift - low_shift;
        const Snapshot before = kernel_.snapshot();
        kernel_.set_board(board);
        bool kept = kernel_.outline_holds();
        if (!kept) attempt.blocker = "fixed copper or the module";
        if (kept) {
            settled_.assign(bundles_.units.size(), 0);
            const Side low_side = along_x ? Side::west : Side::north, high_side = along_x ? Side::east : Side::south;
            std::vector<Move> moves;
            for (std::size_t unit = 0; unit < bundles_.units.size(); ++unit) {
                const auto& members = bundles_.units[unit];
                if (problem_.parts[members.front()].fixed) continue;
                bool at_low = false, at_high = false;
                Box hull = gate_at(problem_, members.front(), kernel_.placement()[members.front()]);
                for (const std::size_t member : members) {
                    const Part& item = problem_.parts[member];
                    const Pose& pose = kernel_.placement()[member];
                    hull = united(hull, gate_at(problem_, member, pose));
                    if (!item.edge) continue;
                    at_low = at_low || facing(item, pose) == low_side;
                    at_high = at_high || facing(item, pose) == high_side;
                }
                if (at_low && at_high) continue;
                if (at_low || at_high) settled_[unit] = 1;
                const Nm centre = along_x ? (hull.x0 + hull.x1) / 2 : (hull.y0 + hull.y1) / 2;
                const Nm shift = at_low ? low_shift : at_high ? high_shift : shift_of(centre);
                if (shift == 0) continue;
                const std::vector<Move> unit_moves = carried(unit, along_x ? Point{shift, 0} : Point{0, shift});
                moves.insert(moves.end(), unit_moves.begin(), unit_moves.end());
            }
            for (std::size_t part = 0; part < problem_.parts.size(); ++part) {
                const Part& item = problem_.parts[part];
                if (!item.corner) continue;
                Pose pose = kernel_.placement()[part];
                pose.at = corner_site(kernel_.board(), *item.corner);
                if (pose != kernel_.placement()[part]) moves.push_back({part, pose});
            }
            kept = kernel_.force(moves);
            if (!kept) attempt.blocker = "a reserved field cannot follow its parts";
            kept = kept && settle(attempt);
        }
        if (!kept) kernel_.restore(before);
        return kept;
    }

    std::vector<Move> carried(std::size_t unit, Point by) const {
        std::vector<Move> moves;
        moves.reserve(bundles_.units[unit].size());
        for (const std::size_t member : bundles_.units[unit]) {
            Pose pose = kernel_.placement()[member];
            pose.at = shifted(pose.at, by);
            moves.push_back({member, pose});
        }
        return moves;
    }

    bool carry_edge(Attempt& attempt) {
        if (!kernel_.outline_holds()) {
            attempt.blocker = "fixed copper or the module";
            return false;
        }
        settled_.assign(bundles_.units.size(), 0);
        const Point in = inward(attempt.side);
        const Point by{in.x * attempt.step, in.y * attempt.step};
        std::vector<Move> moves;
        for (std::size_t part = 0; part < problem_.parts.size(); ++part) {
            const Part& item = problem_.parts[part];
            const std::size_t unit = bundles_.unit_of[part];
            if (item.corner) {
                Pose pose = kernel_.placement()[part];
                pose.at = corner_site(kernel_.board(), *item.corner);
                if (pose != kernel_.placement()[part]) moves.push_back({part, pose});
                continue;
            }
            if (!item.edge || facing(item, kernel_.placement()[part]) != attempt.side || settled_[unit]) continue;
            settled_[unit] = 1;
            const std::vector<Move> unit_moves = carried(unit, by);
            moves.insert(moves.end(), unit_moves.begin(), unit_moves.end());
        }
        if (!kernel_.force(moves)) {
            attempt.blocker = "a reserved field cannot follow its edge";
            return false;
        }
        return true;
    }

    bool move_part(std::size_t part, const std::vector<Point>& offsets) {
        const Pose from = kernel_.placement()[part];
        for (const Point by : offsets) {
            Pose pose = from;
            pose.at = shifted(from.at, by);
            if (!kernel_.rejection(part, pose) && kernel_.move(part, pose)) return true;
        }
        return false;
    }

    bool move_unit(std::size_t unit, const std::vector<Point>& offsets) {
        for (const Point by : offsets)
            if (kernel_.move_many(carried(unit, by))) return true;
        return false;
    }

    std::optional<std::vector<std::size_t>> push_unit(std::size_t unit, const std::vector<Point>& offsets) {
        for (const Point by : offsets) {
            const std::vector<Move> moves = carried(unit, by);
            const Probe probe = kernel_.probe(moves);
            if (!probe.placeable) continue;
            if (std::any_of(probe.blockers.begin(), probe.blockers.end(),
                            [&](std::size_t blocker) { return settled_[bundles_.unit_of[blocker]] != 0; }))
                continue;
            if (!kernel_.force(moves)) continue;
            settled_[unit] = 1;
            return probe.blockers;
        }
        return std::nullopt;
    }

    std::string named(const Violation& violation) const {
        return problem_.parts[violation.part].reference + " " + breach_name(violation.kind) + " " +
               problem_.parts[violation.other].reference;
    }

    bool settle(Attempt& attempt) {
        const Point in = attempt.scaled ? Point{0, 0} : inward(attempt.side);
        const std::vector<Point> near = ring(options_.pitch, options_.part_reach, in);
        const std::vector<Point> far = ring(options_.pitch, options_.unit_reach, in);
        std::deque<std::size_t> fresh, held;
        std::vector<char> queued(problem_.parts.size(), 0), stuck(problem_.parts.size(), 0);
        const auto enqueue = [&](std::size_t part) {
            if (queued[part] || stuck[part] || problem_.parts[part].fixed) return false;
            queued[part] = 1;
            (settled_[bundles_.unit_of[part]] ? held : fresh).push_back(part);
            return true;
        };
        for (std::size_t round = 0; round < options_.rounds; ++round) {
            const auto found = kernel_.violations();
            if (found.empty()) return true;
            bool any = false;
            for (const auto& violation : found) {
                any = enqueue(violation.part) || any;
                any = enqueue(violation.other) || any;
            }
            if (!any) {
                if (attempt.blocker.empty()) attempt.blocker = named(found.front());
                return false;
            }
            while (!fresh.empty() || !held.empty()) {
                auto& source = fresh.empty() ? held : fresh;
                const std::size_t part = source.front();
                source.pop_front();
                queued[part] = 0;
                const auto breach = kernel_.breach(part);
                if (!breach) continue;
                const std::size_t unit = bundles_.unit_of[part];
                const bool alone = bundles_.units[unit].size() == 1;
                if (move_part(part, alone ? far : near)) {
                    ++attempt.relocated;
                    continue;
                }
                if (sink_part(kernel_, part, far)) {
                    ++attempt.sunk;
                    continue;
                }
                if (!alone && move_unit(unit, far)) {
                    ++attempt.relocated;
                    continue;
                }
                const auto blockers = settled_[unit] ? std::nullopt : push_unit(unit, far);
                if (!blockers) {
                    stuck[part] = 1;
                    if (attempt.blocker.empty()) attempt.blocker = named(*breach);
                    continue;
                }
                ++attempt.pushed;
                for (const std::size_t blocker : *blockers) enqueue(blocker);
            }
        }
        const auto left = kernel_.violations();
        if (!left.empty() && attempt.blocker.empty()) attempt.blocker = named(left.front());
        return left.empty();
    }

    Kernel& kernel_;
    const Problem& problem_;
    SqueezeOptions options_;
    Bundles bundles_;
    std::vector<char> settled_;
};

}

const char* side_name(Side side) {
    switch (side) {
    case Side::north: return "north";
    case Side::south: return "south";
    case Side::west: return "west";
    case Side::east: break;
    }
    return "east";
}

Bundles bundle(const Problem& problem) {
    const std::size_t count = problem.parts.size();
    std::vector<std::size_t> parent(count);
    std::iota(parent.begin(), parent.end(), std::size_t{0});
    const auto root = [&](std::size_t part) {
        while (parent[part] != part) part = parent[part] = parent[parent[part]];
        return part;
    };
    const auto join = [&](std::size_t first, std::size_t second) {
        if (problem.parts[first].fixed || problem.parts[second].fixed) return;
        const std::size_t a = root(first), b = root(second);
        if (a != b) parent[std::max(a, b)] = std::min(a, b);
    };
    for (const auto& rule : problem.constraints.pad_gaps)
        if (rule.sense == Sense::at_most && rule.rigid) join(rule.anchor, rule.member);
    for (const auto& rule : problem.constraints.nearest_gaps)
        for (const std::size_t member : rule.members) join(rule.anchor, member);
    for (const auto& reserve : problem.reserves) {
        std::optional<std::size_t> hub;
        for (const std::size_t member : reserve.members) {
            if (problem.parts[member].fixed) continue;
            if (hub) join(*hub, member);
            else hub = member;
        }
    }
    Bundles bundles;
    bundles.unit_of.assign(count, 0);
    for (std::size_t part = 0; part < count; ++part) {
        const std::size_t lead = root(part);
        if (lead == part) {
            bundles.unit_of[part] = bundles.units.size();
            bundles.units.emplace_back();
        }
        bundles.unit_of[part] = bundles.unit_of[lead];
        bundles.units[bundles.unit_of[part]].push_back(part);
    }
    return bundles;
}

SqueezeOptions default_squeeze() {
    SqueezeOptions options;
    options.pitch = static_cast<Nm>(constants::search_pitch.value);
    options.part_reach = static_cast<Nm>(constants::part_reach.value);
    options.unit_reach = static_cast<Nm>(constants::unit_reach.value);
    options.first_step = static_cast<Nm>(constants::first_step.value);
    options.last_step = static_cast<Nm>(constants::last_step.value);
    options.rounds = static_cast<std::size_t>(constants::settle_rounds.value);
    return options;
}

SqueezeReport squeeze(Kernel& kernel, const SqueezeOptions& options) { return Squeezer(kernel, options).run(); }

SqueezeReport squeeze_best(Kernel& kernel, const SqueezeOptions& options) {
    const Snapshot start = kernel.snapshot();
    const auto area = [](const SqueezeReport& report) {
        return to_mm(report.after.width) * to_mm(report.after.height);
    };
    std::optional<SqueezeReport> best;
    Snapshot kept = start;
    std::vector<double> tried;
    for (std::size_t first = 0; first < edge_count; ++first)
        for (const bool backwards : {false, true}) {
            SqueezeOptions variant = options;
            for (std::size_t index = 0; index < edge_count; ++index)
                variant.order[index] =
                    options.order[(backwards ? first + edge_count - index : first + index) % edge_count];
            kernel.restore(start);
            SqueezeReport report = squeeze(kernel, variant);
            tried.push_back(area(report));
            const bool better = !best || area(report) < area(*best) ||
                                (area(report) == area(*best) && report.routed_after < best->routed_after);
            if (!better) continue;
            best = std::move(report);
            kept = kernel.snapshot();
        }
    kernel.restore(kept);
    best->tried = std::move(tried);
    return *best;
}

}
