#include "schgen/measure.hpp"

#include "schgen/board_decision_policy.hpp"
#include "schgen/pcb_checks.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>

namespace schgen::measure {
namespace {

enum Side : std::size_t { north, east, south, west };

enum class Category { plane, power, signal };

struct NetPad {
    double x = 0, y = 0;
    const std::string* group = nullptr;
};

using NetPads = std::map<std::string, std::vector<NetPad>>;

struct Span {
    double total = 0, cross = 0;
};

struct SignalNet {
    std::string name;
    double length = 0, pitch = 0;
    Rect box;
    int pads = 0;
};

struct FaceShapes {
    std::vector<Rect> plain, clearance, fanout, keepouts;
};

Rect grown(Rect rect, double margin) {
    return {rect.x0 - margin, rect.y0 - margin, rect.x1 + margin, rect.y1 + margin};
}

Rect clipped(Rect rect, Rect limit) {
    return {std::max(rect.x0, limit.x0), std::max(rect.y0, limit.y0),
            std::min(rect.x1, limit.x1), std::min(rect.y1, limit.y1)};
}

Rect united(Rect a, Rect b) {
    return {std::min(a.x0, b.x0), std::min(a.y0, b.y0), std::max(a.x1, b.x1), std::max(a.y1, b.y1)};
}

double separation(Rect a, Rect b) {
    const double dx = std::max({a.x0 - b.x1, b.x0 - a.x1, 0.0});
    const double dy = std::max({a.y0 - b.y1, b.y0 - a.y1, 0.0});
    return std::hypot(dx, dy);
}

double quantile(std::vector<double> values, const Constant& share) {
    std::sort(values.begin(), values.end());
    const double rank = std::ceil(share.value * static_cast<double>(values.size()));
    const std::size_t index = rank < 1 ? 0 : static_cast<std::size_t>(rank) - 1;
    return values[std::min(index, values.size() - 1)];
}

bool has_through(const Part& part) {
    return std::any_of(part.pads.begin(), part.pads.end(),
                       [](const Pad& pad) { return pad.through; });
}

bool listed(const std::vector<std::string>& names, const std::string& name) {
    return std::find(names.begin(), names.end(), name) != names.end();
}

FaceShapes face_shapes(const Board& board, const Options& options, Face face) {
    FaceShapes shapes;
    const double clearance = board_decision_policy::placement::clear / 2;
    for (const auto& part : board.parts) {
        if (part.face == face) {
            const double fanout = pcb_fanout_need(part.pin_count).first / 2;
            shapes.plain.push_back(clipped(part.courtyard, board.outline));
            shapes.clearance.push_back(clipped(grown(part.courtyard, clearance), board.outline));
            shapes.fanout.push_back(clipped(grown(part.courtyard, fanout), board.outline));
            continue;
        }
        for (const auto& pad : part.pads) {
            if (!pad.through) continue;
            const Rect hole = clipped({pad.x - pad.reach, pad.y - pad.reach,
                                       pad.x + pad.reach, pad.y + pad.reach}, board.outline);
            shapes.plain.push_back(hole);
            shapes.clearance.push_back(hole);
            shapes.fanout.push_back(hole);
        }
    }
    for (const auto& keepout : options.keepouts) {
        if (keepout.face != face) continue;
        const auto zone = std::find_if(board.zones.begin(), board.zones.end(),
            [&](const Zone& candidate) { return candidate.name == keepout.zone; });
        if (zone == board.zones.end())
            throw MeasureError("measure: keepout zone not found: " + keepout.zone);
        shapes.keepouts.push_back(clipped(zone->box, board.outline));
    }
    return shapes;
}

double outside_keepouts(const std::vector<Rect>& shapes, const std::vector<Rect>& keepouts,
                        double keepout_area) {
    std::vector<Rect> all = shapes;
    all.insert(all.end(), keepouts.begin(), keepouts.end());
    return union_area(all) - keepout_area;
}

FaceMetrics face_metrics(const Board& board, const Options& options, Face face) {
    const FaceShapes shapes = face_shapes(board, options, face);
    FaceMetrics metrics;
    for (const auto& part : board.parts) {
        if (part.face != face) continue;
        ++metrics.parts;
        metrics.courtyard += part.courtyard.area();
    }
    metrics.occupied = union_area(shapes.plain);
    metrics.occupied_clearance = union_area(shapes.clearance);
    metrics.occupied_fanout = union_area(shapes.fanout);
    metrics.keepout = union_area(shapes.keepouts);
    metrics.usable = board.outline.area() - metrics.keepout;
    if (metrics.usable <= 0) throw MeasureError("measure: keepouts leave no usable area");
    const double fanout_outside =
        outside_keepouts(shapes.fanout, shapes.keepouts, metrics.keepout);
    metrics.utilisation =
        outside_keepouts(shapes.plain, shapes.keepouts, metrics.keepout) / metrics.usable;
    metrics.utilisation_fanout = fanout_outside / metrics.usable;
    metrics.demand_fanout = fanout_outside + metrics.keepout;
    return metrics;
}

SubsystemMetrics subsystem_metrics(const Board& board, const Options& options) {
    std::map<std::string, std::vector<const Part*>> members;
    for (const auto& part : board.parts)
        if (!part.group.empty()) members[part.group].push_back(&part);
    for (const auto& name : options.excluded_groups)
        if (!members.count(name)) throw MeasureError("measure: excluded group not found: " + name);
    SubsystemMetrics out;
    std::vector<double> ratios;
    for (const auto& [name, parts] : members) {
        GroupMetrics group;
        group.name = name;
        group.parts = static_cast<int>(parts.size());
        group.box = parts.front()->courtyard;
        double top = 0, bottom = 0;
        for (const Part* part : parts) {
            group.box = united(group.box, part->courtyard);
            if (part->face == Face::top) {
                top += part->courtyard.area();
            } else {
                bottom += part->courtyard.area();
                ++group.bottom_parts;
            }
        }
        group.courtyard = top + bottom;
        group.box_ratio = group.courtyard > 0 ? group.box.area() / group.courtyard : 0;
        group.busiest_fill = group.box.area() > 0 ? std::max(top, bottom) / group.box.area() : 0;
        group.excluded = listed(options.excluded_groups, name);
        if (!group.excluded) {
            out.box_total += group.box.area();
            out.courtyard_total += group.courtyard;
            ratios.push_back(group.box_ratio);
        }
        out.groups.push_back(std::move(group));
    }
    out.box_ratio = out.courtyard_total > 0 ? out.box_total / out.courtyard_total : 0;
    out.median_ratio = ratios.empty() ? 0 : quantile(ratios, constants::middle_quantile);
    out.box_share = out.box_total / board.outline.area();
    return out;
}

NetPads net_pads(const Board& board) {
    NetPads nets;
    for (const auto& part : board.parts)
        for (const auto& pad : part.pads)
            if (!pad.net.empty()) nets[pad.net].push_back({pad.x, pad.y, &part.group});
    return nets;
}

bool matches(std::string_view pattern, std::string_view text) {
    std::size_t at = 0, in = 0, mark = 0, star = std::string_view::npos;
    while (in < text.size()) {
        if (at < pattern.size() && (pattern[at] == '?' || pattern[at] == text[in])) {
            ++at;
            ++in;
        } else if (at < pattern.size() && pattern[at] == '*') {
            star = at++;
            mark = in;
        } else if (star != std::string_view::npos) {
            at = star + 1;
            in = ++mark;
        } else {
            return false;
        }
    }
    while (at < pattern.size() && pattern[at] == '*') ++at;
    return at == pattern.size();
}

const NetClass& class_named(const Board& board, const std::string& name) {
    const auto found = std::find_if(board.classes.begin(), board.classes.end(),
        [&](const NetClass& candidate) { return candidate.name == name; });
    if (found == board.classes.end())
        throw MeasureError("measure: net class not defined: " + name);
    return *found;
}

const NetClass& class_of(const Board& board, const std::string& net) {
    for (const auto& rule : board.patterns)
        if (matches(rule.pattern, net)) return class_named(board, rule.net_class);
    return class_named(board, "Default");
}

int layer_count(const Board& board, std::string_view kind) {
    return static_cast<int>(std::count_if(board.copper.begin(), board.copper.end(),
        [&](const Layer& layer) { return layer.kind == kind; }));
}

bool on_power_layer(const Board& board, const Zone& zone) {
    for (const auto& name : zone.layers)
        for (const auto& layer : board.copper)
            if (layer.name == name && layer.kind == "power") return true;
    return false;
}

Category category_of(const Board& board, const Options& options, const std::string& net) {
    for (const auto& zone : board.zones)
        if (zone.net == net && on_power_layer(board, zone)) return Category::plane;
    if (listed(options.power_classes, class_of(board, net).name)) return Category::power;
    return Category::signal;
}

double euclid(const NetPad& a, const NetPad& b) { return std::hypot(a.x - b.x, a.y - b.y); }

double manhattan(const NetPad& a, const NetPad& b) {
    return std::fabs(a.x - b.x) + std::fabs(a.y - b.y);
}

template <class Distance>
Span spanning(const std::vector<NetPad>& pads, Distance distance) {
    const std::size_t count = pads.size();
    std::vector<double> best(count, std::numeric_limits<double>::infinity());
    std::vector<std::size_t> from(count, 0);
    std::vector<char> used(count, 0);
    best.front() = 0;
    Span span;
    for (std::size_t step = 0; step < count; ++step) {
        std::size_t pick = count;
        for (std::size_t index = 0; index < count; ++index)
            if (!used[index] && (pick == count || best[index] < best[pick])) pick = index;
        used[pick] = 1;
        if (step > 0) {
            span.total += best[pick];
            if (*pads[pick].group != *pads[from[pick]].group) span.cross += best[pick];
        }
        for (std::size_t index = 0; index < count; ++index) {
            if (used[index]) continue;
            const double length = distance(pads[pick], pads[index]);
            if (length < best[index]) {
                best[index] = length;
                from[index] = pick;
            }
        }
    }
    return span;
}

AirwireMetrics airwire_metrics(const Board& board, const Options& options, const NetPads& nets,
                               std::vector<SignalNet>& signals) {
    AirwireMetrics out;
    for (const auto& [name, pads] : nets) {
        if (pads.size() < 2) continue;
        const Span direct = spanning(pads, euclid), routed = spanning(pads, manhattan);
        const Category category = category_of(board, options, name);
        WireTotals& totals = category == Category::plane   ? out.plane
                             : category == Category::power ? out.power
                                                           : out.signal;
        ++totals.nets;
        totals.connections += static_cast<int>(pads.size()) - 1;
        totals.euclid += direct.total;
        totals.manhattan += routed.total;
        totals.cross_euclid += direct.cross;
        totals.cross_manhattan += routed.cross;
        if (category != Category::signal) continue;
        Rect box{pads.front().x, pads.front().y, pads.front().x, pads.front().y};
        for (const auto& pad : pads) box = united(box, {pad.x, pad.y, pad.x, pad.y});
        const NetClass& rule = class_of(board, name);
        signals.push_back({name, routed.total, rule.track_width + rule.clearance, box,
                           static_cast<int>(pads.size())});
    }
    for (const auto& net : signals) out.longest.push_back({net.name, net.length, net.pads});
    std::stable_sort(out.longest.begin(), out.longest.end(),
        [](const NetLength& a, const NetLength& b) { return a.manhattan > b.manhattan; });
    const auto keep = static_cast<std::size_t>(constants::longest_count.value);
    if (out.longest.size() > keep) out.longest.resize(keep);
    return out;
}

Rect widened(Rect box, double pitch) {
    if (box.width() < pitch) {
        const double middle = (box.x0 + box.x1) / 2;
        box.x0 = middle - pitch / 2;
        box.x1 = middle + pitch / 2;
    }
    if (box.height() < pitch) {
        const double middle = (box.y0 + box.y1) / 2;
        box.y0 = middle - pitch / 2;
        box.y1 = middle + pitch / 2;
    }
    return box;
}

DemandMetrics demand_metrics(const Board& board, const std::vector<SignalNet>& signals) {
    DemandMetrics out;
    const double bin = constants::demand_bin.value;
    const int layers = layer_count(board, "signal");
    if (layers == 0) throw MeasureError("measure: board has no signal layer");
    const NetClass& standard = class_named(board, "Default");
    out.default_pitch = standard.track_width + standard.clearance;
    out.columns = static_cast<int>(std::ceil(board.outline.width() / bin));
    out.rows = static_cast<int>(std::ceil(board.outline.height() / bin));
    const auto cell = [&](int row, int column) {
        const double x = board.outline.x0 + column * bin, y = board.outline.y0 + row * bin;
        return Rect{x, y, x + bin, y + bin};
    };
    const auto slot = [&](int row, int column) {
        return static_cast<std::size_t>(row) * static_cast<std::size_t>(out.columns) +
               static_cast<std::size_t>(column);
    };
    const std::size_t count = static_cast<std::size_t>(out.rows) * static_cast<std::size_t>(out.columns);
    std::vector<double> demand(count, 0), capacity(count, 0);
    for (int row = 0; row < out.rows; ++row)
        for (int column = 0; column < out.columns; ++column)
            capacity[slot(row, column)] = layers * clipped(cell(row, column), board.outline).area();
    for (const auto& net : signals) {
        if (net.pitch <= 0) throw MeasureError("measure: net class of " + net.name + " has no pitch");
        const Rect box = widened(net.box, net.pitch);
        const double density = net.length * net.pitch / box.area();
        const int first_column = std::max(0, static_cast<int>(std::floor((box.x0 - board.outline.x0) / bin)));
        const int last_column = std::min(out.columns - 1, static_cast<int>(std::floor((box.x1 - board.outline.x0) / bin)));
        const int first_row = std::max(0, static_cast<int>(std::floor((box.y0 - board.outline.y0) / bin)));
        const int last_row = std::min(out.rows - 1, static_cast<int>(std::floor((box.y1 - board.outline.y0) / bin)));
        for (int row = first_row; row <= last_row; ++row)
            for (int column = first_column; column <= last_column; ++column)
                demand[slot(row, column)] += density * clipped(cell(row, column), box).area();
    }
    out.bins.assign(count, 0);
    std::vector<double> used;
    double demand_total = 0, capacity_total = 0;
    for (std::size_t index = 0; index < count; ++index) {
        if (capacity[index] <= 0) continue;
        out.bins[index] = demand[index] / capacity[index];
        used.push_back(out.bins[index]);
        demand_total += demand[index];
        capacity_total += capacity[index];
    }
    if (used.empty()) throw MeasureError("measure: outline holds no demand bin");
    out.mean = demand_total / capacity_total;
    out.peak = *std::max_element(used.begin(), used.end());
    out.high = quantile(used, constants::high_quantile);
    out.upper = quantile(used, constants::upper_quantile);
    out.median = quantile(used, constants::middle_quantile);
    out.congested = static_cast<int>(std::count_if(used.begin(), used.end(),
        [](double value) { return value > constants::demand_alert.value; }));
    return out;
}

std::vector<GapTier> gap_metrics(const Board& board) {
    std::map<double, std::vector<double>> tiers;
    for (const auto& part : board.parts) {
        if (!part.electrical) continue;
        double nearest = std::numeric_limits<double>::infinity();
        for (const auto& other : board.parts)
            if (&other != &part && other.face == part.face)
                nearest = std::min(nearest, separation(part.courtyard, other.courtyard));
        if (std::isinf(nearest)) continue;
        tiers[pcb_fanout_need(part.pin_count).first].push_back(nearest);
    }
    std::vector<GapTier> out;
    for (const auto& [need, gaps] : tiers) {
        GapTier tier;
        tier.need = need;
        tier.parts = static_cast<int>(gaps.size());
        tier.minimum = *std::min_element(gaps.begin(), gaps.end());
        tier.maximum = *std::max_element(gaps.begin(), gaps.end());
        tier.lower = quantile(gaps, constants::lower_quartile);
        tier.median = quantile(gaps, constants::middle_quantile);
        tier.upper = quantile(gaps, constants::upper_quartile);
        const double limit = need - constants::touch_tolerance.value;
        tier.below = static_cast<int>(std::count_if(gaps.begin(), gaps.end(),
            [&](double gap) { return gap < limit; }));
        out.push_back(tier);
    }
    return out;
}

std::array<EdgeMetrics, edge_count> edge_metrics(const Board& board) {
    std::array<EdgeMetrics, edge_count> out;
    const Rect& outline = board.outline;
    out[north].name = "north";
    out[east].name = "east";
    out[south].name = "south";
    out[west].name = "west";
    out[north].length = out[south].length = outline.width();
    out[east].length = out[west].length = outline.height();
    for (const auto& part : board.parts) {
        if (!part.electrical || part.pin_count < 2) continue;
        const Rect& court = part.courtyard;
        const std::array<double, edge_count> beyond{outline.y0 - court.y0, court.x1 - outline.x1,
                                           court.y1 - outline.y1, outline.x0 - court.x0};
        auto side = static_cast<std::size_t>(
            std::max_element(beyond.begin(), beyond.end()) - beyond.begin());
        bool mounted = beyond[side] > constants::touch_tolerance.value;
        if (!mounted && has_through(part)) {
            const std::array<double, edge_count> inside{court.y0 - outline.y0, outline.x1 - court.x1,
                                               outline.y1 - court.y1, court.x0 - outline.x0};
            side = static_cast<std::size_t>(
                std::min_element(inside.begin(), inside.end()) - inside.begin());
            mounted = inside[side] <= constants::edge_band.value;
        }
        if (!mounted) continue;
        const Rect within = clipped(court, outline);
        const double width = side == north || side == south ? within.width() : within.height();
        out[side].parts.push_back({part.reference, width});
        out[side].run += width;
    }
    for (auto& edge : out) {
        std::sort(edge.parts.begin(), edge.parts.end(),
            [](const EdgePart& a, const EdgePart& b) { return a.reference < b.reference; });
        edge.ratio = edge.length > 0 ? edge.run / edge.length : 0;
    }
    return out;
}

BoundMetrics bound_metrics(const Report& report) {
    BoundMetrics bounds;
    bounds.top_demand = report.top.demand_fanout;
    bounds.bottom_demand = report.bottom.demand_fanout;
    bounds.balanced_demand = (bounds.top_demand + bounds.bottom_demand) / 2;
    bounds.outline_ratio =
        bounds.balanced_demand > 0 ? report.area / bounds.balanced_demand : 0;
    for (const auto& edge : report.edges) bounds.perimeter_run += edge.run;
    bounds.perimeter_ratio = bounds.perimeter_run / (2 * (report.width + report.height));
    return bounds;
}

}

double union_area(const std::vector<Rect>& rects) {
    std::vector<double> stops;
    for (const auto& rect : rects) {
        if (rect.area() <= 0) continue;
        stops.push_back(rect.x0);
        stops.push_back(rect.x1);
    }
    std::sort(stops.begin(), stops.end());
    stops.erase(std::unique(stops.begin(), stops.end()), stops.end());
    double total = 0;
    for (std::size_t index = 0; index + 1 < stops.size(); ++index) {
        std::vector<std::pair<double, double>> spans;
        for (const auto& rect : rects)
            if (rect.area() > 0 && rect.x0 <= stops[index] && rect.x1 >= stops[index + 1])
                spans.emplace_back(rect.y0, rect.y1);
        std::sort(spans.begin(), spans.end());
        double covered = 0, reach = -std::numeric_limits<double>::infinity();
        for (const auto& [low, high] : spans) {
            if (high <= reach) continue;
            covered += high - std::max(low, reach);
            reach = high;
        }
        total += covered * (stops[index + 1] - stops[index]);
    }
    return total;
}

Report measure_board(const Board& board, const Options& options) {
    for (const auto& name : options.power_classes) class_named(board, name);
    Report report;
    report.options = options;
    report.width = board.outline.width();
    report.height = board.outline.height();
    report.area = board.outline.area();
    if (report.area <= 0) throw MeasureError("measure: outline has no area");
    report.signal_layers = layer_count(board, "signal");
    report.power_layers = layer_count(board, "power");
    report.parts = static_cast<int>(board.parts.size());
    for (const auto& part : board.parts) {
        if (has_through(part)) ++report.through_parts;
        if (part.courtyard_from_pads) ++report.pad_courtyards;
    }
    report.without_geometry = board.without_geometry;
    report.top = face_metrics(board, options, Face::top);
    report.bottom = face_metrics(board, options, Face::bottom);
    report.subsystems = subsystem_metrics(board, options);
    const NetPads nets = net_pads(board);
    std::vector<SignalNet> signals;
    report.airwire = airwire_metrics(board, options, nets, signals);
    report.demand = demand_metrics(board, signals);
    report.gaps = gap_metrics(board);
    report.edges = edge_metrics(board);
    report.bounds = bound_metrics(report);
    return report;
}

}
