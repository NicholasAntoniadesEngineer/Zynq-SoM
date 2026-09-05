#include "schgen/legalize.hpp"

#include "schgen/occupancy.hpp"

#include <algorithm>
#include <cmath>
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

}  // namespace schgen
