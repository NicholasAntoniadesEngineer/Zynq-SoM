#include "schgen/legalize.hpp"

#include "schgen/occupancy.hpp"

#include <algorithm>
#include <cmath>
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

}  // namespace schgen
