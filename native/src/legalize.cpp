#include "schgen/legalize.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/quantize.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace schgen {

PairAxis pair_axis(const Box4& a, const Box4& b) {
    const double gx = std::max(b.x0 - a.x1, a.x0 - b.x1);
    const double gy = std::max(b.y0 - a.y1, a.y0 - b.y1);
    const double nx = gx / std::max(1.0, ((a.x1 - a.x0) + (b.x1 - b.x0)) / 2.0);
    const double ny = gy / std::max(1.0, ((a.y1 - a.y0) + (b.y1 - b.y0)) / 2.0);
    if (nx >= ny) {
        return PairAxis{true, a.x0 <= b.x0};
    }
    return PairAxis{false, a.y0 <= b.y0};
}

BellmanResult bellman_ford(std::size_t node_count,
                           const std::vector<int>& src,
                           const std::vector<int>& dst,
                           const std::vector<double>& cost) {
    if (src.size() != dst.size() || src.size() != cost.size()) {
        throw std::runtime_error("bellman_ford: edge arrays required same length");
    }
    if (node_count == 0) {
        throw std::runtime_error("bellman_ford: node_count required");
    }
    const int n = static_cast<int>(node_count);
    const int ecount = static_cast<int>(src.size());
    for (int i = 0; i < ecount; ++i) {
        if (src[i] < 0 || dst[i] < 0 || src[i] >= n || dst[i] >= n) {
            throw std::runtime_error("bellman_ford: edge endpoint out of range");
        }
    }

    std::vector<double> dist(node_count, 0.0);
    std::vector<int> pred_node(node_count, -1);
    std::vector<int> pred_edge(node_count, -1);
    int last = -1;
    for (int sweep = 0; sweep < n; ++sweep) {
        bool relaxed = false;
        for (int e = 0; e < ecount; ++e) {
            const int u = src[e];
            const int v = dst[e];
            const double c = cost[e];
            if (dist[static_cast<std::size_t>(u)] + c
                < dist[static_cast<std::size_t>(v)] - 1e-12) {
                dist[static_cast<std::size_t>(v)] =
                    dist[static_cast<std::size_t>(u)] + c;
                pred_node[static_cast<std::size_t>(v)] = u;
                pred_edge[static_cast<std::size_t>(v)] = e;
                relaxed = true;
                last = v;
            }
        }
        if (!relaxed) {
            return BellmanResult{true, dist, {}};
        }
    }
    if (last < 0) {
        throw std::runtime_error("bellman_ford: relaxed without a last node");
    }
    int node = last;
    for (int i = 0; i < n; ++i) {
        const int prev = pred_node[static_cast<std::size_t>(node)];
        if (prev < 0) {
            throw std::runtime_error("bellman_ford: predecessor missing");
        }
        node = prev;
    }
    std::vector<int> tags;
    const int start = node;
    while (true) {
        const int prev = pred_node[static_cast<std::size_t>(node)];
        const int edge = pred_edge[static_cast<std::size_t>(node)];
        if (prev < 0 || edge < 0) {
            throw std::runtime_error("bellman_ford: cycle walk broke");
        }
        tags.push_back(edge);
        node = prev;
        if (node == start || static_cast<int>(tags.size()) > n + 1) {
            break;
        }
    }
    return BellmanResult{false, {}, tags};
}

double flow_budget(double board_w, double board_h,
                   const std::optional<Box4>& som_core) {
    const double area = std::max(board_w * board_h, 1.0);
    double som_diag = 0.0;
    if (som_core.has_value()) {
        const Box4& s = *som_core;
        som_diag = std::hypot(s.x1 - s.x0, s.y1 - s.y0);
    }
    return 0.35 * std::sqrt(area) + 1.0 * som_diag;
}

double bbox_gap(const Box4& a, const Box4& b) {
    const double dx = std::max(std::max(a.x0 - b.x1, b.x0 - a.x1), 0.0);
    const double dy = std::max(std::max(a.y0 - b.y1, b.y0 - a.y1), 0.0);
    return std::hypot(dx, dy);
}

double rect_gap(const Box4& a, const Box4& b) {
    const double dx = std::max(std::max(b.x0 - a.x1, a.x0 - b.x1), 0.0);
    const double dy = std::max(std::max(b.y0 - a.y1, a.y0 - b.y1), 0.0);
    if (dx == 0.0 && dy == 0.0) {
        return 0.0;
    }
    if (dx == 0.0) {
        return dy;
    }
    if (dy == 0.0) {
        return dx;
    }
    return std::sqrt(dx * dx + dy * dy);
}

std::pair<double, double> facing_dot(double zone_x, double zone_y,
                                     double out_x, double out_y,
                                     double down_x, double down_y) {
    const double ox = out_x - zone_x;
    const double oy = out_y - zone_y;
    const double dx = down_x - zone_x;
    const double dy = down_y - zone_y;
    const double dot = ox * dx + oy * dy;
    const double mo = std::hypot(ox, oy);
    const double md = std::hypot(dx, dy);
    double angle = 180.0;
    if (mo > 1e-9 && md > 1e-9) {
        const double c = std::max(-1.0, std::min(1.0, dot / (mo * md)));
        angle = std::acos(c) * (180.0 / 3.141592653589793);
    }
    return {dot, angle};
}

std::optional<std::pair<double, double>> predicted_centroid(
    double pose_x, double pose_y, double origin_x, double origin_y,
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    const std::vector<std::string>* refs) {
    std::unordered_set<std::string> allow;
    if (refs != nullptr) {
        allow.insert(refs->begin(), refs->end());
    }
    double xs = 0.0;
    double ys = 0.0;
    int n = 0;
    for (const auto& off : offsets) {
        const std::string& ref = std::get<0>(off);
        if (refs != nullptr && allow.find(ref) == allow.end()) {
            continue;
        }
        xs += py_round(origin_x + pose_x + std::get<1>(off), 4);
        ys += py_round(origin_y + pose_y + std::get<2>(off), 4);
        ++n;
    }
    if (n == 0) {
        return std::nullopt;
    }
    return std::make_pair(py_round(xs / static_cast<double>(n), 4),
                          py_round(ys / static_cast<double>(n), 4));
}

std::optional<Box4> predicted_bbox(
    double pose_x, double pose_y, double origin_x, double origin_y,
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        pad_union) {
    std::unordered_map<std::string, std::pair<double, double>> off;
    off.reserve(offsets.size());
    for (const auto& row : offsets) {
        off[std::get<0>(row)] = {std::get<1>(row), std::get<2>(row)};
    }
    bool any = false;
    Box4 acc;
    for (const auto& pad : pad_union) {
        const auto it = off.find(std::get<0>(pad));
        if (it == off.end()) {
            throw std::runtime_error("predicted_bbox: pad ref missing offset");
        }
        const double dx = it->second.first;
        const double dy = it->second.second;
        const double px = py_round(origin_x + pose_x + dx, 4);
        const double py = py_round(origin_y + pose_y + dy, 4);
        const double x0 = px + (std::get<1>(pad) - dx);
        const double y0 = py + (std::get<2>(pad) - dy);
        const double x1 = px + (std::get<3>(pad) - dx);
        const double y1 = py + (std::get<4>(pad) - dy);
        if (!any) {
            acc = Box4{x0, y0, x1, y1};
            any = true;
        } else {
            acc.x0 = std::min(acc.x0, x0);
            acc.y0 = std::min(acc.y0, y0);
            acc.x1 = std::max(acc.x1, x1);
            acc.y1 = std::max(acc.y1, y1);
        }
    }
    if (!any) {
        return std::nullopt;
    }
    return Box4{py_round(acc.x0, 4), py_round(acc.y0, 4),
                py_round(acc.x1, 4), py_round(acc.y1, 4)};
}

std::optional<Box4> pad_union_hull(
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        pad_union) {
    if (pad_union.empty()) {
        return std::nullopt;
    }
    double x0 = std::get<1>(pad_union[0]);
    double y0 = std::get<2>(pad_union[0]);
    double x1 = std::get<3>(pad_union[0]);
    double y1 = std::get<4>(pad_union[0]);
    for (std::size_t i = 1; i < pad_union.size(); ++i) {
        x0 = std::min(x0, std::get<1>(pad_union[i]));
        y0 = std::min(y0, std::get<2>(pad_union[i]));
        x1 = std::max(x1, std::get<3>(pad_union[i]));
        y1 = std::max(y1, std::get<4>(pad_union[i]));
    }
    return Box4{x0, y0, x1, y1};
}

std::pair<double, double> centroid_offset(
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    double half_w, double half_h) {
    if (offsets.empty()) {
        return {half_w, half_h};
    }
    double xs = 0.0;
    double ys = 0.0;
    for (const auto& off : offsets) {
        xs += std::get<1>(off);
        ys += std::get<2>(off);
    }
    const double n = static_cast<double>(offsets.size());
    return {xs / n, ys / n};
}

double channel_demand_mm(int n_airwires, int min_nets, double floor_mm,
                         double per_net_mm) {
    if (min_nets <= 0) {
        throw std::runtime_error("channel_demand_mm: min_nets required");
    }
    if (n_airwires < min_nets) {
        return 0.0;
    }
    return floor_mm + per_net_mm * static_cast<double>(n_airwires);
}

std::pair<double, std::string> channel_gap_mm(
    bool near_max_adjacent, int cross_airwire_count, double clear,
    int channel_min_nets, double channel_floor_mm, double channel_per_net_mm) {
    if (channel_min_nets <= 0) {
        throw std::runtime_error("channel_gap_mm: channel_min_nets required");
    }
    if (near_max_adjacent) {
        return {clear, "near_max-adjacency(terminus)"};
    }
    const double channel = channel_demand_mm(
        cross_airwire_count, channel_min_nets, channel_floor_mm,
        channel_per_net_mm);
    if (channel > clear) {
        return {channel,
                "D13-channel(" + std::to_string(cross_airwire_count)
                    + " nets)"};
    }
    return {clear, "CLEAR"};
}

namespace {

std::string pair_key(const std::string& a, const std::string& b) {
    if (a <= b) {
        return a + '\x1f' + b;
    }
    return b + '\x1f' + a;
}

}  // namespace

std::vector<BuiltSep> legalize_build_seps(
    const std::vector<std::string>& names,
    const std::vector<Box4>& seed_rects,
    const std::vector<std::string>& fixed_names,
    const std::vector<Box4>& fixed_rects,
    const std::vector<std::tuple<std::string, std::string, int>>& demand_rows,
    const std::vector<std::pair<std::string, std::string>>& near_max_pairs,
    double clear, int channel_min_nets, double channel_floor_mm,
    double channel_per_net_mm) {
    if (names.size() != seed_rects.size()) {
        throw std::runtime_error(
            "legalize_build_seps: names and seed_rects required same length");
    }
    if (fixed_names.size() != fixed_rects.size()) {
        throw std::runtime_error(
            "legalize_build_seps: fixed_names and fixed_rects required same "
            "length");
    }
    std::unordered_map<std::string, int> demand_of;
    for (const auto& row : demand_rows) {
        demand_of[pair_key(std::get<0>(row), std::get<1>(row))] =
            std::get<2>(row);
    }
    std::unordered_set<std::string> near_of;
    for (const auto& pair : near_max_pairs) {
        near_of.insert(pair_key(pair.first, pair.second));
    }
    std::vector<std::size_t> fixed_order(fixed_names.size());
    for (std::size_t i = 0; i < fixed_order.size(); ++i) {
        fixed_order[i] = i;
    }
    std::sort(fixed_order.begin(), fixed_order.end(),
              [&](std::size_t a, std::size_t b) {
                  return fixed_names[a] < fixed_names[b];
              });
    auto gap_of = [&](const std::string& a, const std::string& b) {
        const std::string key = pair_key(a, b);
        const auto near_it = near_of.find(key);
        const auto demand_it = demand_of.find(key);
        const int count = demand_it == demand_of.end() ? 0 : demand_it->second;
        return channel_gap_mm(near_it != near_of.end(), count, clear,
                              channel_min_nets, channel_floor_mm,
                              channel_per_net_mm);
    };
    std::vector<BuiltSep> seps;
    for (std::size_t i = 0; i < names.size(); ++i) {
        for (std::size_t j = i + 1; j < names.size(); ++j) {
            const PairAxis axis = pair_axis(seed_rects[i], seed_rects[j]);
            const auto gap = gap_of(names[i], names[j]);
            const std::string& lo = axis.a_first ? names[i] : names[j];
            const std::string& hi = axis.a_first ? names[j] : names[i];
            seps.push_back(BuiltSep{axis.axis_x ? "x" : "y", lo, hi, gap.first,
                                    gap.second, true});
        }
        for (std::size_t fi : fixed_order) {
            const PairAxis axis = pair_axis(seed_rects[i], fixed_rects[fi]);
            const auto gap = gap_of(names[i], fixed_names[fi]);
            const std::string tagged = "#" + fixed_names[fi];
            const std::string lo = axis.a_first ? names[i] : tagged;
            const std::string hi = axis.a_first ? tagged : names[i];
            seps.push_back(BuiltSep{axis.axis_x ? "x" : "y", lo, hi, gap.first,
                                    gap.second, true});
        }
    }
    return seps;
}

bool rects_overlap_any(const std::vector<Box4>& probes,
                       const std::vector<Box4>& obstacles, double eps) {
    for (const Box4& probe : probes) {
        for (const Box4& obstacle : obstacles) {
            if (std::min(probe.x1, obstacle.x1) - std::max(probe.x0, obstacle.x0)
                    > eps
                && std::min(probe.y1, obstacle.y1)
                           - std::max(probe.y0, obstacle.y0)
                       > eps) {
                return true;
            }
        }
    }
    return false;
}

std::vector<std::pair<int, int>> mst_manhattan(
    const std::vector<std::pair<double, double>>& pts) {
    const int n = static_cast<int>(pts.size());
    if (n < 2) {
        return {};
    }
    std::vector<char> in_tree(static_cast<std::size_t>(n), 0);
    in_tree[0] = 1;
    std::vector<double> best_d(static_cast<std::size_t>(n));
    std::vector<int> best_u(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        best_d[static_cast<std::size_t>(i)] =
            std::fabs(pts[static_cast<std::size_t>(i)].first - pts[0].first)
            + std::fabs(pts[static_cast<std::size_t>(i)].second - pts[0].second);
    }
    std::vector<std::pair<int, int>> edges;
    edges.reserve(static_cast<std::size_t>(n - 1));
    for (int step = 0; step < n - 1; ++step) {
        int u = -1;
        double ud = 0.0;
        bool have = false;
        for (int i = 0; i < n; ++i) {
            if (in_tree[static_cast<std::size_t>(i)]) {
                continue;
            }
            if (!have || best_d[static_cast<std::size_t>(i)] < ud) {
                ud = best_d[static_cast<std::size_t>(i)];
                u = i;
                have = true;
            }
        }
        if (u < 0) {
            break;
        }
        in_tree[static_cast<std::size_t>(u)] = 1;
        edges.emplace_back(best_u[static_cast<std::size_t>(u)], u);
        for (int i = 0; i < n; ++i) {
            if (in_tree[static_cast<std::size_t>(i)]) {
                continue;
            }
            const double d =
                std::fabs(pts[static_cast<std::size_t>(i)].first
                          - pts[static_cast<std::size_t>(u)].first)
                + std::fabs(pts[static_cast<std::size_t>(i)].second
                            - pts[static_cast<std::size_t>(u)].second);
            if (d < best_d[static_cast<std::size_t>(i)]) {
                best_d[static_cast<std::size_t>(i)] = d;
                best_u[static_cast<std::size_t>(i)] = u;
            }
        }
    }
    return edges;
}

double cross_net_cost(
    const std::vector<std::tuple<double, double, int, int>>& pts,
    double via_mm, const std::vector<std::uint8_t>& sheet_is_bot) {
    std::vector<std::pair<double, double>> xy;
    xy.reserve(pts.size());
    for (const auto& p : pts) {
        xy.emplace_back(std::get<0>(p), std::get<1>(p));
    }
    const auto edges = mst_manhattan(xy);
    bool have_bot = false;
    for (std::uint8_t flag : sheet_is_bot) {
        if (flag != 0) {
            have_bot = true;
            break;
        }
    }
    double cross = 0.0;
    for (const auto& e : edges) {
        const auto& a = pts[static_cast<std::size_t>(e.first)];
        const auto& b = pts[static_cast<std::size_t>(e.second)];
        if (std::get<2>(a) == std::get<2>(b)) {
            continue;
        }
        const double dx = std::get<0>(a) - std::get<0>(b);
        const double dy = std::get<1>(a) - std::get<1>(b);
        cross += std::sqrt(dx * dx + dy * dy);
        const int sa = std::get<2>(a);
        const int sb = std::get<2>(b);
        const bool a_bot =
            sa >= 0 && sa < static_cast<int>(sheet_is_bot.size())
            && sheet_is_bot[static_cast<std::size_t>(sa)] != 0;
        const bool b_bot =
            sb >= 0 && sb < static_cast<int>(sheet_is_bot.size())
            && sheet_is_bot[static_cast<std::size_t>(sb)] != 0;
        if (via_mm != 0.0 && have_bot && (a_bot || b_bot)
            && std::get<3>(a) != std::get<3>(b)) {
            cross += via_mm;
        }
    }
    return cross;
}

double weighted_median(const std::vector<std::pair<double, double>>& pulls) {
    if (pulls.empty()) {
        throw std::runtime_error("weighted_median: pulls required");
    }
    std::vector<std::pair<double, double>> ordered = pulls;
    std::stable_sort(ordered.begin(), ordered.end(),
                     [](const std::pair<double, double>& a,
                        const std::pair<double, double>& b) {
                         return a.second < b.second;
                     });
    double tot = 0.0;
    for (const auto& p : ordered) {
        tot += p.first;
    }
    double acc = 0.0;
    double best = ordered[0].second;
    for (const auto& p : ordered) {
        acc += p.first;
        if (acc >= tot / 2.0 - 1e-12) {
            best = p.second;
            break;
        }
    }
    return best;
}

bool constraint_edges_ok(const std::vector<int>& src,
                         const std::vector<int>& dst,
                         const std::vector<double>& cost,
                         const std::vector<double>& pos) {
    if (src.size() != dst.size() || src.size() != cost.size()) {
        throw std::runtime_error("constraint_edges_ok: edge arrays required");
    }
    const int n = static_cast<int>(pos.size());
    for (std::size_t i = 0; i < src.size(); ++i) {
        if (src[i] < 0 || dst[i] < 0 || src[i] >= n || dst[i] >= n) {
            throw std::runtime_error("constraint_edges_ok: endpoint out of range");
        }
        const double pu = pos[static_cast<std::size_t>(src[i])];
        const double pv = pos[static_cast<std::size_t>(dst[i])];
        if (pv - pu > cost[i] + 1e-9) {
            return false;
        }
    }
    return true;
}

std::pair<double, double> constraint_bounds(int node,
                                            const std::vector<int>& src,
                                            const std::vector<int>& dst,
                                            const std::vector<double>& cost,
                                            const std::vector<double>& pos) {
    if (src.size() != dst.size() || src.size() != cost.size()) {
        throw std::runtime_error("constraint_bounds: edge arrays required");
    }
    const int n = static_cast<int>(pos.size());
    if (node < 0 || node >= n) {
        throw std::runtime_error("constraint_bounds: node out of range");
    }
    double lo = -std::numeric_limits<double>::infinity();
    double hi = std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < src.size(); ++i) {
        if (src[i] < 0 || dst[i] < 0 || src[i] >= n || dst[i] >= n) {
            throw std::runtime_error("constraint_bounds: endpoint out of range");
        }
        if (dst[i] == node && src[i] != node) {
            hi = std::min(hi, pos[static_cast<std::size_t>(src[i])] + cost[i]);
        }
        if (src[i] == node && dst[i] != node) {
            lo = std::max(lo, pos[static_cast<std::size_t>(dst[i])] - cost[i]);
        }
    }
    return {lo, hi};
}

std::optional<double> min_box_gap(const std::vector<Box4>& a,
                                  const std::vector<Box4>& b) {
    if (a.empty() || b.empty()) {
        return std::nullopt;
    }
    double best = bbox_gap(a[0], b[0]);
    for (const Box4& aa : a) {
        for (const Box4& bb : b) {
            best = std::min(best, bbox_gap(aa, bb));
        }
    }
    return best;
}

std::vector<WallSepEdge> wall_sep_edges(
    bool axis_x, const std::vector<std::string>& names,
    const std::vector<double>& sizes, double span, double clear,
    const std::vector<SepSpec>& seps,
    const std::vector<std::pair<std::string, Box4>>& frects) {
    if (names.size() != sizes.size()) {
        throw std::runtime_error("wall_sep_edges: names and sizes required same length");
    }
    std::unordered_map<std::string, double> size_of;
    size_of.reserve(names.size());
    for (std::size_t i = 0; i < names.size(); ++i) {
        size_of[names[i]] = sizes[i];
    }
    std::unordered_map<std::string, Box4> frect;
    frect.reserve(frects.size());
    for (const auto& row : frects) {
        frect[row.first] = row.second;
    }
    std::vector<WallSepEdge> out;
    out.reserve(names.size() * 2 + seps.size());
    for (std::size_t i = 0; i < names.size(); ++i) {
        const std::string& n = names[i];
        const double w = sizes[i];
        out.push_back(WallSepEdge{"#0", n, span - clear - w, "wall-hi", -1, n});
        out.push_back(WallSepEdge{n, "#0", -clear, "wall-lo", -1, n});
    }
    for (int si = 0; si < static_cast<int>(seps.size()); ++si) {
        const SepSpec& s = seps[static_cast<std::size_t>(si)];
        if (s.axis_x != axis_x) {
            continue;
        }
        const bool lo_f = !s.lo.empty() && s.lo[0] == '#';
        const bool hi_f = !s.hi.empty() && s.hi[0] == '#';
        if (lo_f && hi_f) {
            continue;
        }
        if (lo_f) {
            const auto it = frect.find(s.lo.substr(1));
            if (it == frect.end()) {
                throw std::runtime_error("wall_sep_edges: fixed lo missing");
            }
            const double hi = axis_x ? it->second.x1 : it->second.y1;
            out.push_back(WallSepEdge{s.hi, "#0", -(hi + s.gap), "sep", si, ""});
        } else if (hi_f) {
            const auto it = frect.find(s.hi.substr(1));
            if (it == frect.end()) {
                throw std::runtime_error("wall_sep_edges: fixed hi missing");
            }
            const auto sz = size_of.find(s.lo);
            if (sz == size_of.end()) {
                throw std::runtime_error("wall_sep_edges: movable lo missing");
            }
            const double lo = axis_x ? it->second.x0 : it->second.y0;
            out.push_back(WallSepEdge{"#0", s.lo, lo - s.gap - sz->second, "sep",
                                      si, ""});
        } else {
            const auto sz = size_of.find(s.lo);
            if (sz == size_of.end()) {
                throw std::runtime_error("wall_sep_edges: movable pair missing");
            }
            out.push_back(WallSepEdge{s.hi, s.lo, -(sz->second + s.gap), "sep",
                                      si, ""});
        }
    }
    return out;
}

std::vector<NearMaxEdge> near_max_edges(
    const std::string& subject, const std::string& target, double bound,
    bool axis_x, const Box4& hull_s, const Box4& hull_g, const Box4& seed_s,
    const Box4& seed_g, bool s_movable, bool g_movable,
    const std::optional<std::pair<double, double>>& pose_s,
    const std::optional<std::pair<double, double>>& pose_g) {
    if (bound < 0.0 || (!s_movable && !g_movable)) {
        return {};
    }
    const PairAxis pa = pair_axis(seed_s, seed_g);
    const bool dom_x = pa.axis_x;
    const std::string& lo = pa.a_first ? subject : target;
    const std::string& hi = pa.a_first ? target : subject;
    const Box4& hlo = pa.a_first ? hull_s : hull_g;
    const Box4& hhi = pa.a_first ? hull_g : hull_s;
    const bool lo_mov = pa.a_first ? s_movable : g_movable;
    const bool hi_mov = pa.a_first ? g_movable : s_movable;
    auto pose_of = [&](const std::string& name)
        -> const std::optional<std::pair<double, double>>& {
        return name == subject ? pose_s : pose_g;
    };
    auto axis_coord = [](const std::optional<std::pair<double, double>>& pose,
                         bool use_x) {
        if (!pose.has_value()) {
            throw std::runtime_error("near_max_edges: fixed pose required");
        }
        return use_x ? pose->first : pose->second;
    };
    auto c0 = [](const Box4& b, bool use_x) { return use_x ? b.x0 : b.y0; };
    auto c1 = [](const Box4& b, bool use_x) { return use_x ? b.x1 : b.y1; };
    std::vector<NearMaxEdge> out;
    if (axis_x == dom_x) {
        const double cost = bound + c1(hlo, dom_x) - c0(hhi, dom_x);
        if (lo_mov && hi_mov) {
            out.push_back(NearMaxEdge{lo, hi, cost, false});
        } else if (lo_mov) {
            const double f = axis_coord(pose_of(hi), dom_x);
            out.push_back(NearMaxEdge{
                lo, "#0", -(f + c0(hhi, dom_x) - bound - c1(hlo, dom_x)),
                false});
        } else {
            const double f = axis_coord(pose_of(lo), dom_x);
            out.push_back(NearMaxEdge{
                "#0", hi, f + c1(hlo, dom_x) + bound - c0(hhi, dom_x), false});
        }
    } else {
        const bool perp_x = !dom_x;
        const double a0 = c0(hull_s, perp_x);
        const double a2 = c1(hull_s, perp_x);
        const double b0 = c0(hull_g, perp_x);
        const double b2 = c1(hull_g, perp_x);
        if (s_movable && g_movable) {
            out.push_back(NearMaxEdge{subject, target, a2 - b0, true});
            out.push_back(NearMaxEdge{target, subject, b2 - a0, true});
        } else if (s_movable) {
            const double f = axis_coord(pose_g, perp_x);
            out.push_back(NearMaxEdge{subject, "#0", -(f + b0 - a2), true});
            out.push_back(NearMaxEdge{"#0", subject, f + b2 - a0, true});
        } else {
            const double f = axis_coord(pose_s, perp_x);
            out.push_back(NearMaxEdge{target, "#0", -(f + a0 - b2), true});
            out.push_back(NearMaxEdge{"#0", target, f + a2 - b0, true});
        }
    }
    return out;
}

namespace {

std::string format_g(double value) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%g", value);
    return buf;
}

std::string format_dot(double value) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%+.2f", value);
    return buf;
}

}  // namespace

std::vector<EvalTermOut> evaluate_terms(
    double board_w, double board_h, const std::optional<Box4>& som_core,
    const std::vector<std::pair<std::string, std::pair<double, double>>>&
        poses,
    const std::vector<EvalMetric>& metrics, const std::vector<EvalTermIn>& terms,
    const std::vector<std::pair<std::string, double>>& far_guard,
    const std::vector<std::pair<std::string, Box4>>& som_j_rects,
    double origin_x, double origin_y) {
    std::unordered_map<std::string, std::pair<double, double>> pose_of;
    for (const auto& p : poses) {
        pose_of[p.first] = p.second;
    }
    std::unordered_map<std::string, const EvalMetric*> metric_of;
    for (const auto& m : metrics) {
        metric_of[m.name] = &m;
    }
    std::unordered_map<std::string, double> guard_of;
    for (const auto& g : far_guard) {
        guard_of[g.first] = g.second;
    }
    std::unordered_map<std::string, Box4> jack_of;
    for (const auto& j : som_j_rects) {
        jack_of[j.first] = j.second;
    }
    const double budget = flow_budget(board_w, board_h, som_core);

    auto centroid_of =
        [&](const std::string& name) -> std::optional<std::pair<double, double>> {
        if (name == "@som") {
            if (!som_core.has_value()) {
                return std::nullopt;
            }
            const Box4& s = *som_core;
            return std::make_pair(py_round((s.x0 + s.x1) / 2.0, 4),
                                  py_round((s.y0 + s.y1) / 2.0, 4));
        }
        if (name.rfind("som_j", 0) == 0) {
            const auto it = jack_of.find(name);
            if (it == jack_of.end()) {
                return std::nullopt;
            }
            const Box4& r = it->second;
            return std::make_pair(
                py_round((r.x0 + r.x1) / 2.0 + origin_x, 4),
                py_round((r.y0 + r.y1) / 2.0 + origin_y, 4));
        }
        const auto pose_it = pose_of.find(name);
        const auto met_it = metric_of.find(name);
        if (pose_it == pose_of.end() || met_it == metric_of.end()) {
            return std::nullopt;
        }
        return predicted_centroid(pose_it->second.first, pose_it->second.second,
                                  origin_x, origin_y, met_it->second->offsets,
                                  nullptr);
    };

    auto bbox_of = [&](const std::string& name) -> std::optional<Box4> {
        if (name == "@som") {
            return som_core;
        }
        if (name.rfind("som_j", 0) == 0) {
            const auto it = jack_of.find(name);
            if (it == jack_of.end()) {
                return std::nullopt;
            }
            const Box4& r = it->second;
            return Box4{r.x0 + origin_x, r.y0 + origin_y, r.x1 + origin_x,
                        r.y1 + origin_y};
        }
        const auto pose_it = pose_of.find(name);
        const auto met_it = metric_of.find(name);
        if (pose_it == pose_of.end() || met_it == metric_of.end()) {
            return std::nullopt;
        }
        return predicted_bbox(pose_it->second.first, pose_it->second.second,
                              origin_x, origin_y, met_it->second->offsets,
                              met_it->second->pad_union);
    };

    auto guard_at = [&](const std::string& name) {
        const auto it = guard_of.find(name);
        return it == guard_of.end() ? 0.0 : it->second;
    };

    std::vector<EvalTermOut> out;
    out.reserve(terms.size());
    for (const EvalTermIn& t : terms) {
        if (t.kind == "flow_hop") {
            const auto ca = centroid_of(t.subject);
            const auto cb = centroid_of(t.target);
            if (!ca.has_value() || !cb.has_value()) {
                out.push_back(EvalTermOut{std::numeric_limits<double>::infinity(),
                                          py_round(budget, 4),
                                          -std::numeric_limits<double>::infinity(),
                                          false, "UNRESOLVED"});
                continue;
            }
            const double d = std::hypot(ca->first - cb->first,
                                        ca->second - cb->second);
            const double g = guard_at(t.subject) + guard_at(t.target);
            const double eff = budget - g;
            std::string note;
            if (g != 0.0) {
                note = "incl L4 guard " + format_g(g) + "mm";
            }
            out.push_back(EvalTermOut{d, py_round(eff, 4),
                                      py_round(eff - d, 4), d <= eff, note});
        } else if (t.kind == "near_max" || t.kind == "near_intent") {
            const auto ba = bbox_of(t.subject);
            const auto bb = bbox_of(t.target);
            const double bound = t.bound_set ? t.bound : 0.0;
            if (!ba.has_value() || !bb.has_value()) {
                out.push_back(EvalTermOut{
                    std::numeric_limits<double>::infinity(), bound,
                    -std::numeric_limits<double>::infinity(),
                    t.kind == "near_intent", "UNRESOLVED"});
                continue;
            }
            const double g = bbox_gap(*ba, *bb);
            if (t.kind == "near_intent") {
                out.push_back(EvalTermOut{g, 0.0, 0.0, true, "advisory"});
            } else {
                out.push_back(EvalTermOut{g, bound, py_round(bound - g, 4),
                                          g <= bound, ""});
            }
        } else if (t.kind == "far_min") {
            const auto ca = centroid_of(t.subject);
            const auto cb = centroid_of(t.target);
            const double guard = std::max(guard_at(t.subject),
                                          guard_at(t.target));
            const double bound = (t.bound_set ? t.bound : 0.0) + guard;
            if (!ca.has_value() || !cb.has_value()) {
                out.push_back(EvalTermOut{
                    std::numeric_limits<double>::infinity(), bound,
                    -std::numeric_limits<double>::infinity(), false,
                    "UNRESOLVED"});
                continue;
            }
            const double d = std::hypot(ca->first - cb->first,
                                        ca->second - cb->second);
            std::string note;
            if (guard != 0.0) {
                note = "incl FAR_L4_GUARD " + format_g(guard) + "mm";
            }
            out.push_back(EvalTermOut{d, bound, py_round(d - bound, 4),
                                      d >= bound, note});
        } else if (t.kind == "facing") {
            const auto czone = centroid_of(t.subject);
            std::optional<std::pair<double, double>> cout;
            const auto pose_it = pose_of.find(t.subject);
            const auto met_it = metric_of.find(t.subject);
            if (pose_it != pose_of.end() && met_it != metric_of.end()) {
                cout = predicted_centroid(
                    pose_it->second.first, pose_it->second.second, origin_x,
                    origin_y, met_it->second->offsets, &t.out_refs);
            }
            const auto cdown = centroid_of(t.target);
            if (!czone.has_value() || !cout.has_value() || !cdown.has_value()) {
                out.push_back(EvalTermOut{180.0, 90.0, -90.0, false,
                                          "UNRESOLVED"});
                continue;
            }
            const auto face = facing_dot(czone->first, czone->second,
                                         cout->first, cout->second,
                                         cdown->first, cdown->second);
            const std::string dot_note = "dot=" + format_dot(face.first);
            if (guard_at(t.subject) != 0.0 || guard_at(t.target) != 0.0) {
                out.push_back(EvalTermOut{
                    face.second, 90.0, py_round(90.0 - face.second, 4), true,
                    dot_note + " L4-guarded participant - gate-arbitrated"});
            } else {
                out.push_back(EvalTermOut{
                    face.second, 90.0, py_round(90.0 - face.second, 4),
                    face.first > 0.0, dot_note});
            }
        } else {
            throw std::runtime_error("evaluate_terms: unknown term kind "
                                     + t.kind);
        }
    }
    return out;
}

namespace {

void collect_nodes(const std::vector<NamedEdge>& edges,
                   const std::vector<std::string>& names,
                   std::vector<std::string>* nodes,
                   std::unordered_map<std::string, int>* index) {
    auto add = [&](const std::string& name) {
        if (index->find(name) != index->end()) {
            return;
        }
        (*index)[name] = static_cast<int>(nodes->size());
        nodes->push_back(name);
    };
    add("#0");
    for (const std::string& name : names) {
        add(name);
    }
    for (const NamedEdge& e : edges) {
        add(e.src);
        add(e.dst);
    }
}

void edges_to_arrays(const std::vector<NamedEdge>& edges,
                     const std::unordered_map<std::string, int>& index,
                     std::vector<int>* src, std::vector<int>* dst,
                     std::vector<double>* cost) {
    src->clear();
    dst->clear();
    cost->clear();
    src->reserve(edges.size());
    dst->reserve(edges.size());
    cost->reserve(edges.size());
    for (const NamedEdge& e : edges) {
        src->push_back(index.at(e.src));
        dst->push_back(index.at(e.dst));
        cost->push_back(e.cost);
    }
}

}  // namespace

std::pair<std::vector<double>, std::vector<double>> legalize_descend_passes(
    const std::vector<std::string>& names,
    const std::vector<double>& pos_x, const std::vector<double>& pos_y,
    const std::vector<double>& seed_x, const std::vector<double>& seed_y,
    const std::vector<NamedEdge>& edges_x,
    const std::vector<NamedEdge>& edges_y,
    const std::vector<std::pair<std::string, std::string>>& hops,
    const std::vector<std::pair<std::string, std::pair<double, double>>>&
        cent_off,
    const std::vector<std::pair<std::string, std::pair<double, double>>>&
        fixed_poses,
    double som_mid_x, double som_mid_y, bool has_som, bool seed_only,
    double hop_weight, double seed_weight, int median_passes) {
    if (names.size() != pos_x.size() || names.size() != pos_y.size()
        || names.size() != seed_x.size() || names.size() != seed_y.size()) {
        throw std::runtime_error(
            "legalize_descend_passes: name arrays required same length");
    }
    if (median_passes <= 0) {
        throw std::runtime_error(
            "legalize_descend_passes: median_passes required");
    }
    std::unordered_map<std::string, int> name_index;
    for (std::size_t i = 0; i < names.size(); ++i) {
        name_index[names[i]] = static_cast<int>(i);
    }
    std::unordered_map<std::string, std::pair<double, double>> fixed_of;
    for (const auto& f : fixed_poses) {
        fixed_of[f.first] = f.second;
    }
    std::unordered_map<std::string, std::pair<double, double>> cent_of;
    for (const auto& c : cent_off) {
        cent_of[c.first] = c.second;
    }
    auto centroid_xy = [&](const std::string& name) {
        const auto it = cent_of.find(name);
        return it == cent_of.end() ? std::pair<double, double>{0.0, 0.0}
                                   : it->second;
    };
    std::vector<double> px = pos_x;
    std::vector<double> py = pos_y;
    std::vector<std::string> nodes_x;
    std::vector<std::string> nodes_y;
    std::unordered_map<std::string, int> index_x;
    std::unordered_map<std::string, int> index_y;
    collect_nodes(edges_x, names, &nodes_x, &index_x);
    collect_nodes(edges_y, names, &nodes_y, &index_y);
    std::vector<int> src_x;
    std::vector<int> dst_x;
    std::vector<double> cost_x;
    std::vector<int> src_y;
    std::vector<int> dst_y;
    std::vector<double> cost_y;
    edges_to_arrays(edges_x, index_x, &src_x, &dst_x, &cost_x);
    edges_to_arrays(edges_y, index_y, &src_y, &dst_y, &cost_y);

    for (int pass = 0; pass < median_passes; ++pass) {
        double moved = 0.0;
        for (std::size_t ni = 0; ni < names.size(); ++ni) {
            const std::string& n = names[ni];
            for (int axis = 0; axis < 2; ++axis) {
                const bool axis_x = (axis == 0);
                auto& pos = axis_x ? px : py;
                const auto& index = axis_x ? index_x : index_y;
                const auto& nodes = axis_x ? nodes_x : nodes_y;
                const auto& src = axis_x ? src_x : src_y;
                const auto& dst = axis_x ? dst_x : dst_y;
                const auto& cost = axis_x ? cost_x : cost_y;
                std::vector<double> posv(nodes.size(), 0.0);
                for (std::size_t k = 0; k < nodes.size(); ++k) {
                    if (nodes[k] == "#0") {
                        posv[k] = 0.0;
                        continue;
                    }
                    const auto it = name_index.find(nodes[k]);
                    if (it != name_index.end()) {
                        posv[k] = pos[static_cast<std::size_t>(it->second)];
                    }
                }
                const auto nit = index.find(n);
                if (nit == index.end()) {
                    continue;
                }
                const auto bounds = constraint_bounds(nit->second, src, dst,
                                                      cost, posv);
                const double lo = bounds.first;
                const double hi = bounds.second;
                if (lo > hi) {
                    continue;
                }
                std::vector<std::pair<double, double>> pulls;
                if (!seed_only) {
                    const auto self_c = centroid_xy(n);
                    const double co = axis_x ? self_c.first : self_c.second;
                    for (const auto& hop : hops) {
                        const std::string* other = nullptr;
                        if (hop.first == n) {
                            other = &hop.second;
                        } else if (hop.second == n) {
                            other = &hop.first;
                        }
                        if (other == nullptr) {
                            continue;
                        }
                        const auto oit = name_index.find(*other);
                        const auto oc_xy = centroid_xy(*other);
                        const double oc = axis_x ? oc_xy.first : oc_xy.second;
                        if (oit != name_index.end()) {
                            const std::size_t oi =
                                static_cast<std::size_t>(oit->second);
                            const double op = (axis_x ? px : py)[oi];
                            pulls.emplace_back(hop_weight, op + oc - co);
                        } else if (fixed_of.find(*other) != fixed_of.end()) {
                            const auto& fp = fixed_of[*other];
                            pulls.emplace_back(
                                hop_weight,
                                (axis_x ? fp.first : fp.second) + oc - co);
                        } else if (*other == "@som" && has_som) {
                            pulls.emplace_back(
                                hop_weight,
                                (axis_x ? som_mid_x : som_mid_y) - co);
                        }
                    }
                }
                pulls.emplace_back(seed_only ? 1.0 : seed_weight,
                                   axis_x ? seed_x[ni] : seed_y[ni]);
                const double best = weighted_median(pulls);
                double q = legalize_pose_quantum(best);
                q = std::max(lo, std::min(q, hi));
                const double old = pos[ni];
                if (std::fabs(q - old) > 1e-12) {
                    pos[ni] = q;
                    moved = std::max(moved, std::fabs(q - old));
                }
            }
        }
        if (moved <= 1e-9) {
            break;
        }
    }
    return {px, py};
}

std::pair<double, double> interior_dims(double area, double aspect,
                                        double min_mm, double max_mm) {
    if (aspect <= 0.0) {
        throw std::runtime_error("interior_dims: aspect required");
    }
    if (min_mm <= 0.0 || max_mm <= 0.0) {
        throw std::runtime_error("interior_dims: min_mm and max_mm required");
    }
    const double raw = std::sqrt(area / aspect);
    const double h = placeholder_zone_half_mm(
        std::min(max_mm, std::max(min_mm, raw)));
    const double w = placeholder_zone_half_mm(std::max(min_mm, area / h));
    return {w, h};
}

std::tuple<double, double, double, double, double, double> derive_outline_wh(
    double som_w, double som_h, double halo, double edge_band, double perim,
    double pack_eff, double comp_area) {
    if (pack_eff <= 0.0) {
        throw std::runtime_error("derive_outline_wh: pack_eff required");
    }
    const double core_w = som_w + 2.0 * halo;
    const double core_h = som_h + 2.0 * halo;
    const double banded_w = core_w + 2.0 * edge_band;
    const double banded_h = core_h + 2.0 * edge_band;
    const double som_keepout = core_w * core_h;
    const double need_area = comp_area / pack_eff + som_keepout;
    const double aspect = banded_w / banded_h;
    const double area_w = std::sqrt(need_area * aspect);
    const double area_h = std::sqrt(need_area / aspect);
    const double w = outline_snap_up(std::max(banded_w, area_w) + 2.0 * perim);
    const double h = outline_snap_up(std::max(banded_h, area_h) + 2.0 * perim);
    return {w, h, banded_w, banded_h, area_w, area_h};
}

RepairAxisResult legalize_repair_axis(
    bool axis_x, const std::vector<std::string>& names,
    const std::vector<double>& sizes, double span, double clear,
    const std::vector<RepairSep>& seps_in,
    const std::vector<std::pair<std::string, Box4>>& frects,
    const std::vector<NamedEdge>& extra, int repair_max) {
    if (names.size() != sizes.size()) {
        throw std::runtime_error(
            "legalize_repair_axis: names and sizes required same length");
    }
    if (repair_max < 0) {
        throw std::runtime_error("legalize_repair_axis: repair_max required");
    }
    RepairAxisResult out;
    out.seps = seps_in;
    for (int rep = 0; rep <= repair_max; ++rep) {
        std::vector<SepSpec> spec;
        spec.reserve(out.seps.size());
        for (const auto& sep : out.seps) {
            spec.push_back(SepSpec{sep.axis_x, sep.lo, sep.hi, sep.gap});
        }
        const auto wall = wall_sep_edges(axis_x, names, sizes, span, clear,
                                         spec, frects);
        std::vector<NamedEdge> edges;
        std::vector<int> sep_of_edge;
        edges.reserve(wall.size() + extra.size());
        sep_of_edge.reserve(wall.size() + extra.size());
        for (const auto& edge : wall) {
            edges.push_back(NamedEdge{edge.src, edge.dst, edge.cost});
            sep_of_edge.push_back(edge.kind == "sep" ? edge.sep_index : -1);
        }
        for (const auto& edge : extra) {
            edges.push_back(edge);
            sep_of_edge.push_back(-1);
        }
        std::vector<std::string> nodes;
        std::unordered_map<std::string, int> index;
        collect_nodes(edges, names, &nodes, &index);
        std::vector<int> src;
        std::vector<int> dst;
        std::vector<double> cost;
        edges_to_arrays(edges, index, &src, &dst, &cost);
        const BellmanResult hit = bellman_ford(nodes.size(), src, dst, cost);
        if (hit.feasible) {
            const auto base_it = index.find("#0");
            if (base_it == index.end()) {
                throw std::runtime_error("legalize_repair_axis: #0 required");
            }
            const double base =
                hit.dist[static_cast<std::size_t>(base_it->second)];
            out.pos.resize(names.size());
            for (std::size_t i = 0; i < names.size(); ++i) {
                const auto nit = index.find(names[i]);
                if (nit == index.end()) {
                    throw std::runtime_error(
                        "legalize_repair_axis: name missing from graph");
                }
                out.pos[i] =
                    hit.dist[static_cast<std::size_t>(nit->second)] - base;
            }
            out.ok = true;
            return out;
        }
        bool flipped = false;
        for (int edge_i : hit.cycle_edges) {
            if (edge_i < 0
                || edge_i >= static_cast<int>(sep_of_edge.size())) {
                continue;
            }
            const int sep_i = sep_of_edge[static_cast<std::size_t>(edge_i)];
            if (sep_i < 0 || sep_i >= static_cast<int>(out.seps.size())) {
                continue;
            }
            RepairSep& sep = out.seps[static_cast<std::size_t>(sep_i)];
            if (!sep.flippable) {
                continue;
            }
            out.flips.emplace_back(sep.lo, sep.hi, sep.axis_x);
            RepairSep moved = sep;
            moved.axis_x = !moved.axis_x;
            moved.flippable = false;
            out.seps.erase(out.seps.begin()
                           + static_cast<std::ptrdiff_t>(sep_i));
            out.seps.push_back(moved);
            flipped = true;
            break;
        }
        if (!flipped) {
            out.fail = "cycle";
            return out;
        }
    }
    out.fail = "exhausted";
    return out;
}

}  // namespace schgen
