#include "schgen/legalize.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
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

}  // namespace schgen
