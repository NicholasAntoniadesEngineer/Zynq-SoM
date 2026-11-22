#include "schgen/layout_density.hpp"

#include "schgen/layout_squeeze.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <sstream>

namespace schgen::layout {
namespace {

int dense_level() { return densest_density; }
int sparse_level() { return sparsest_density; }

std::string millimetres(Nm value) {
    std::ostringstream out;
    out << to_mm(value) << " mm";
    return out.str();
}

std::pair<std::size_t, std::size_t> ordered(std::size_t first, std::size_t second) {
    return {std::min(first, second), std::max(first, second)};
}

std::map<std::pair<std::size_t, std::size_t>, Nm> limits_of(const Problem& problem) {
    std::map<std::pair<std::size_t, std::size_t>, Nm> limits;
    for (const SpacingLimit& limit : problem.constraints.spacing_limits)
        limits[ordered(limit.first, limit.second)] = limit.limit;
    return limits;
}

Nm wanted_between(const Problem& problem, std::size_t first, std::size_t second) {
    if (problem.parts[first].fixed && problem.parts[second].fixed) return 0;
    return std::max(problem.parts[first].spacing, problem.parts[second].spacing);
}

}

int DensityChoice::of(const std::string& sheet) const {
    if (board < sparse_level() || board > dense_level())
        throw LayoutError("layout: the board states no density from " + std::to_string(sparse_level()) + " to " +
                          std::to_string(dense_level()));
    const auto found = sheets.find(sheet);
    return found == sheets.end() ? board : found->second;
}

bool DensityChoice::spaced() const {
    if (board < dense_level()) return true;
    return std::any_of(sheets.begin(), sheets.end(), [](const auto& entry) { return entry.second < dense_level(); });
}

Nm density_spacing(int level) {
    if (level < sparse_level() || level > dense_level())
        throw LayoutError("layout: density " + std::to_string(level) + " is not " + density_range());
    return static_cast<Nm>(dense_level() - level) * to_nm(constants::density_step.value);
}

void apply_density(Problem& problem, const DensityChoice& choice) {
    for (Part& part : problem.parts) part.spacing = density_spacing(choice.of(part.group));
    problem.constraints.spacing_limits.clear();
    if (!choice.spaced()) return;
    std::map<std::pair<std::size_t, std::size_t>, SpacingLimit> limits;
    const auto offer = [&](std::size_t first, std::size_t second, Nm room, const std::string& source) {
        if (first == second) return;
        const Nm limit = std::max<Nm>(room, 0);
        if (limit >= wanted_between(problem, first, second)) return;
        const auto key = ordered(first, second);
        const auto found = limits.find(key);
        if (found == limits.end() || limit < found->second.limit) limits[key] = {key.first, key.second, limit, source};
    };
    const auto among = [&](const std::vector<std::size_t>& parts, const std::string& source) {
        for (std::size_t first = 0; first < parts.size(); ++first)
            for (std::size_t second = first + 1; second < parts.size(); ++second) offer(parts[first], parts[second], 0, source);
    };
    for (const auto& unit : bundle(problem).units) among(unit, "tied cluster of " + problem.parts[unit.front()].reference);
    std::map<std::size_t, std::vector<std::size_t>> served;
    const auto bind = [&](std::size_t anchor, std::size_t member, const std::string& source) {
        offer(anchor, member, 0, source);
        served[anchor].push_back(member);
    };
    for (const PadGap& rule : problem.constraints.pad_gaps)
        if (rule.sense == Sense::at_most) bind(rule.anchor, rule.member, rule.source);
    for (const PadGap& rule : problem.constraints.soft_gaps)
        if (rule.sense == Sense::at_most) bind(rule.anchor, rule.member, rule.source);
    for (const NearestGap& rule : problem.constraints.nearest_gaps)
        for (const std::size_t member : rule.members) bind(rule.anchor, member, rule.source);
    for (const NetOrder& rule : net_orders_of(problem)) offer(rule.anchor, rule.lead, 0, rule.source + ", first on its net");
    for (auto& [anchor, members] : served) {
        std::sort(members.begin(), members.end());
        members.erase(std::unique(members.begin(), members.end()), members.end());
        among(members, "parts that serve " + problem.parts[anchor].reference);
    }
    for (const Reserve& reserve : problem.reserves) among(reserve.members, "parts held together on " + reserve.source);
    for (const GroupGap& rule : problem.constraints.group_gaps) {
        if (rule.sense != Sense::at_most || rule.second_is_core || rule.measure != GroupMeasure::hull_gap) continue;
        for (std::size_t first = 0; first < problem.parts.size(); ++first) {
            if (problem.parts[first].group != rule.first) continue;
            for (std::size_t second = 0; second < problem.parts.size(); ++second)
                if (problem.parts[second].group == rule.second)
                    offer(first, second, rule.limit - problem.rules.group_guard, rule.source + ", within " + millimetres(rule.limit));
        }
    }
    for (auto& entry : limits) problem.constraints.spacing_limits.push_back(std::move(entry.second));
}

Problem without_density(const Problem& problem) {
    Problem dense = problem;
    for (Part& part : dense.parts) part.spacing = 0;
    dense.constraints.spacing_limits.clear();
    return dense;
}

Nm spacing_between(const Problem& problem, std::size_t first, std::size_t second) {
    const Nm wanted = wanted_between(problem, first, second);
    if (wanted == 0) return 0;
    for (const SpacingLimit& limit : problem.constraints.spacing_limits)
        if (ordered(limit.first, limit.second) == ordered(first, second)) return std::min(wanted, limit.limit);
    return wanted;
}

double courtyard_gap(const Problem& problem, std::size_t first, const Pose& first_pose, std::size_t second,
                     const Pose& second_pose) {
    const Variant& a = problem.footprints[problem.parts[first].footprint].on(first_pose.face);
    const Variant& b = problem.footprints[problem.parts[second].footprint].on(second_pose.face);
    double best = std::numeric_limits<double>::infinity();
    const auto reach = [](const Box& box, const Disc& disc) {
        const Nm across = axis_gap(box.x0, box.x1, disc.centre.x, disc.centre.x);
        const Nm along = axis_gap(box.y0, box.y1, disc.centre.y, disc.centre.y);
        return std::max(0.0, std::hypot(static_cast<double>(across), static_cast<double>(along)) - static_cast<double>(disc.radius));
    };
    for (const Box& local : a.court_boxes) {
        const Box box = placed(local, first_pose.at, first_pose.turn);
        for (const Box& other : b.court_boxes)
            best = std::min(best, std::sqrt(static_cast<double>(squared_gap(box, placed(other, second_pose.at, second_pose.turn)))));
        for (const Disc& other : b.court_discs) best = std::min(best, reach(box, placed(other, second_pose.at, second_pose.turn)));
    }
    for (const Disc& local : a.court_discs) {
        const Disc disc = placed(local, first_pose.at, first_pose.turn);
        for (const Box& other : b.court_boxes) best = std::min(best, reach(placed(other, second_pose.at, second_pose.turn), disc));
        for (const Disc& other : b.court_discs) {
            const Disc peer = placed(other, second_pose.at, second_pose.turn);
            best = std::min(best, std::max(0.0, std::hypot(static_cast<double>(disc.centre.x - peer.centre.x),
                                                           static_cast<double>(disc.centre.y - peer.centre.y)) -
                                                    static_cast<double>(disc.radius + peer.radius)));
        }
    }
    return best / constants::nano_scale.value;
}

std::string density_table() {
    std::ostringstream text;
    text << "TABLE (level: gap added between courtyards on one face):\n";
    for (int level = dense_level(); level >= sparse_level(); --level) {
        const Nm gap = density_spacing(level);
        text << "    " << level << ": " << millimetres(gap);
        if (level == dense_level()) text << "  (" << constants::density_dense.basis << ")";
        for (const NamedConstant& mark : {constants::most_excess, constants::inspect_gap, constants::iron_gap})
            if (gap == to_nm(mark.value)) text << "  (" << mark.basis << ")";
        text << "\n";
    }
    text << "  rule: gap = (" << constants::density_dense.value << " - level) x " << constants::density_step.value << " mm\n";
    for (const NamedConstant& constant : constants::density_registry)
        text << "  constant " << constant.name << " = " << constant.value << " " << constant.unit << " [" << constant.proof
             << "]: " << constant.basis << "\n";
    text << "  status: the figures come from the pages named above, opened on 2026-11-23; the IPC-7351 and IPC-7352 texts "
            "were not opened, so the table is proposed for review\n";
    return text.str();
}

std::string density_statement(const DensityChoice& choice) {
    std::ostringstream text;
    text << "LAYOUT DENSITY: board level " << choice.board << " of " << sparse_level() << " to " << dense_level() << "; "
         << choice.sheets.size() << " subsystems state their own level\n"
         << "  the layout squeeze is off, so the placement is as handed over and no gap is measured\n";
    for (const auto& [name, level] : choice.sheets)
        text << "    " << name << ": level " << level << " (stated for it), " << millimetres(density_spacing(level)) << "\n";
    text << density_table();
    return text.str();
}

std::string density_report(const Problem& problem, const Placement& placement, const DensityChoice& choice) {
    std::ostringstream text;
    text << "LAYOUT DENSITY: board level " << choice.board << " of " << sparse_level() << " to " << dense_level() << "; "
         << choice.sheets.size() << " subsystems state their own level\n"
         << "  a lower level only adds a gap between courtyards on the same face; every other rule keeps its limit\n"
         << "  two parts of different subsystems keep the larger of their two gaps; two fixed parts keep none\n";
    struct Row {
        std::size_t parts = 0, limited = 0;
        double tightest = std::numeric_limits<double>::infinity();
        std::string pair;
    };
    std::map<std::string, Row> rows;
    for (const Part& part : problem.parts) ++rows[part.group].parts;
    const auto limits = limits_of(problem);
    std::size_t breaches = 0;
    for (std::size_t first = 0; first < problem.parts.size(); ++first)
        for (std::size_t second = first + 1; second < problem.parts.size(); ++second) {
            const Nm wanted = wanted_between(problem, first, second);
            if (wanted == 0) continue;
            const auto limit = limits.find(ordered(first, second));
            const Nm need = limit == limits.end() ? wanted : std::min(wanted, limit->second);
            if (limit != limits.end()) {
                ++rows[problem.parts[first].group].limited;
                if (problem.parts[second].group != problem.parts[first].group) ++rows[problem.parts[second].group].limited;
            }
            if (placement[first].face != placement[second].face) continue;
            const double gap = courtyard_gap(problem, first, placement[first], second, placement[second]);
            if (gap < to_mm(need) - to_mm(problem.rules.compare_guard)) ++breaches;
            if (limit != limits.end()) continue;
            for (const std::size_t part : {first, second}) {
                Row& row = rows[problem.parts[part].group];
                if (problem.parts[part].spacing != wanted || gap >= row.tightest) continue;
                row.tightest = gap;
                row.pair = problem.parts[first].reference + " / " + problem.parts[second].reference;
            }
        }
    text << "SUBSYSTEMS (level, gap added, parts, pairs limited by another rule, smallest gap measured where the full gap applies):\n";
    for (const auto& [name, row] : rows) {
        const int level = choice.of(name);
        text << "    " << name << ": level " << level << (choice.sheets.count(name) ? " (stated for it)" : " (board level)")
             << ", " << millimetres(density_spacing(level)) << ", " << row.parts << " parts, " << row.limited << " limited pairs";
        if (density_spacing(level) > 0 && !row.pair.empty()) text << ", smallest " << row.tightest << " mm (" << row.pair << ")";
        text << "\n";
    }
    text << "GAPS NOT KEPT: " << breaches << "\n" << density_table();
    std::map<std::string, std::vector<const SpacingLimit*>> by_source;
    for (const SpacingLimit& limit : problem.constraints.spacing_limits) by_source[limit.source].push_back(&limit);
    text << "PAIRS WHERE ANOTHER RULE LIMITS THE GAP: " << problem.constraints.spacing_limits.size() << " in " << by_source.size()
         << " rules (the rule wins: parts it binds together keep no added gap, and a distance limit between subsystems caps the gap at that limit)\n";
    for (const auto& [source, pairs] : by_source) {
        const SpacingLimit& lead = *pairs.front();
        text << "    " << source << ": ";
        if (pairs.size() == 1)
            text << problem.parts[lead.first].reference << " / " << problem.parts[lead.second].reference << " keep "
                 << millimetres(lead.limit) << " instead of " << millimetres(wanted_between(problem, lead.first, lead.second));
        else
            text << pairs.size() << " pairs keep " << millimetres(lead.limit);
        text << "\n";
    }
    return text.str();
}

}
