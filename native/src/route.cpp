#include "schgen/occupancy.hpp"
#include "schgen/route.hpp"

#include <algorithm>
#include <climits>
#include <cmath>
#include <deque>
#include <stdexcept>
#include <unordered_set>

namespace schgen {
namespace {

constexpr double kSnapTol = 1e-3;
constexpr double kBlockEps = 1e-6;
constexpr int kJoinMargin = 12;

}  // namespace

bool route_snap_ok(double value, double grid) {
    return std::abs(value / grid - std::round(value / grid)) < kSnapTol;
}

RouteCell route_cell_of(double x, double y, double grid) {
    if (!(route_snap_ok(x, grid) && route_snap_ok(y, grid))) {
        throw std::runtime_error("route: point is off the schematic grid");
    }
    return {static_cast<int>(std::lround(x / grid)),
            static_cast<int>(std::lround(y / grid))};
}

RoutePoint route_point_of(int i, int j, double grid) {
    return {py_round(static_cast<double>(i) * grid, 3),
            py_round(static_cast<double>(j) * grid, 3)};
}

std::vector<RouteCell> route_cells_between(RoutePoint a, RoutePoint b,
                                           double grid) {
    const RouteCell ca = route_cell_of(a.first, a.second, grid);
    const RouteCell cb = route_cell_of(b.first, b.second, grid);
    if (ca.first != cb.first && ca.second != cb.second) {
        throw std::runtime_error("route: segment is not orthogonal");
    }
    std::vector<RouteCell> out;
    if (ca.first == cb.first) {
        const int lo = std::min(ca.second, cb.second);
        const int hi = std::max(ca.second, cb.second);
        out.reserve(static_cast<std::size_t>(hi - lo + 1));
        for (int j = lo; j <= hi; ++j) {
            out.emplace_back(ca.first, j);
        }
        return out;
    }
    const int lo = std::min(ca.first, cb.first);
    const int hi = std::max(ca.first, cb.first);
    out.reserve(static_cast<std::size_t>(hi - lo + 1));
    for (int i = lo; i <= hi; ++i) {
        out.emplace_back(i, ca.second);
    }
    return out;
}

std::uint64_t RouteGrid::pack(int i, int j) {
    return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(i)) << 32)
        ^ static_cast<std::uint32_t>(j);
}

void RouteGrid::claim(const std::string& owner,
                      const std::vector<RouteCell>& cells,
                      const std::string& what) {
    for (const RouteCell& c : cells) {
        const auto it = owner_.find(pack(c.first, c.second));
        if (it != owner_.end() && it->second != owner) {
            throw std::runtime_error(
                "route: cell contested: " + it->second + " vs " + owner
                + " (" + what + ")");
        }
        owner_[pack(c.first, c.second)] = owner;
    }
}

void RouteGrid::block_box(double x0, double y0, double x1, double y1,
                          double grid) {
    const int i0 = static_cast<int>(x0 / grid) - 1;
    const int i1 = static_cast<int>(x1 / grid) + 2;
    const int j0 = static_cast<int>(y0 / grid) - 1;
    const int j1 = static_cast<int>(y1 / grid) + 2;
    for (int i = i0; i < i1; ++i) {
        for (int j = j0; j < j1; ++j) {
            const double x = static_cast<double>(i) * grid;
            const double y = static_cast<double>(j) * grid;
            if (x0 + kBlockEps < x && x < x1 - kBlockEps
                && y0 + kBlockEps < y && y < y1 - kBlockEps) {
                owner_.emplace(pack(i, j), "#blocked");
            }
        }
    }
}

bool RouteGrid::free_or(const std::string& net, RouteCell cell) const {
    const auto it = owner_.find(pack(cell.first, cell.second));
    return it == owner_.end() || it->second == net;
}

std::vector<RouteCell> RouteGrid::occupied() const {
    std::vector<RouteCell> out;
    out.reserve(owner_.size());
    for (const auto& [k, _n] : owner_) {
        const int i = static_cast<int>(static_cast<std::uint32_t>(k >> 32));
        const int j = static_cast<int>(static_cast<std::uint32_t>(k));
        out.emplace_back(i, j);
    }
    return out;
}

std::vector<RoutePoint> route_bfs_join(
    const RouteGrid& grid, const std::string& net,
    const std::vector<RoutePoint>& comp_a,
    const std::vector<RoutePoint>& comp_b, double grid_mm) {
    std::unordered_set<std::uint64_t> starts;
    std::unordered_set<std::uint64_t> goals;
    auto pack = [](RouteCell c) {
        return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(c.first))
                << 32)
            ^ static_cast<std::uint32_t>(c.second);
    };
    std::vector<RouteCell> occ = grid.occupied();
    for (const RoutePoint& p : comp_a) {
        const RouteCell c = route_cell_of(p.first, p.second, grid_mm);
        starts.insert(pack(c));
        occ.push_back(c);
    }
    for (const RoutePoint& p : comp_b) {
        const RouteCell c = route_cell_of(p.first, p.second, grid_mm);
        goals.insert(pack(c));
        occ.push_back(c);
    }
    if (occ.empty()) {
        throw std::runtime_error("route: bfs join has no occupied cells");
    }
    int i0 = occ[0].first;
    int i1 = occ[0].first;
    int j0 = occ[0].second;
    int j1 = occ[0].second;
    for (const RouteCell& c : occ) {
        i0 = std::min(i0, c.first);
        i1 = std::max(i1, c.first);
        j0 = std::min(j0, c.second);
        j1 = std::max(j1, c.second);
    }
    i0 -= kJoinMargin;
    i1 += kJoinMargin;
    j0 -= kJoinMargin;
    j1 += kJoinMargin;

    std::unordered_map<std::uint64_t, RouteCell> prev;
    std::deque<RouteCell> q;
    for (const RoutePoint& p : comp_a) {
        const RouteCell c = route_cell_of(p.first, p.second, grid_mm);
        prev.emplace(pack(c), RouteCell{INT32_MIN, INT32_MIN});
        q.push_back(c);
    }
    RouteCell hit{0, 0};
    bool found = false;
    const RouteCell dirs[4] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
    while (!q.empty()) {
        const RouteCell c = q.front();
        q.pop_front();
        if (goals.count(pack(c)) != 0) {
            hit = c;
            found = true;
            break;
        }
        for (const RouteCell& d : dirs) {
            const RouteCell n{c.first + d.first, c.second + d.second};
            if (!(i0 <= n.first && n.first <= i1 && j0 <= n.second
                  && n.second <= j1)) {
                continue;
            }
            if (prev.count(pack(n)) != 0 || !grid.free_or(net, n)) {
                continue;
            }
            prev.emplace(pack(n), c);
            q.push_back(n);
        }
    }
    if (!found) {
        throw std::runtime_error(
            "route: no free corridor joins its parts — placement must expand");
    }
    std::vector<RouteCell> chain{hit};
    while (true) {
        const RouteCell p = prev.at(pack(chain.back()));
        if (p.first == INT32_MIN && p.second == INT32_MIN) {
            break;
        }
        chain.push_back(p);
    }
    std::reverse(chain.begin(), chain.end());
    std::vector<RoutePoint> pts;
    pts.reserve(chain.size());
    for (const RouteCell& c : chain) {
        pts.push_back(route_point_of(c.first, c.second, grid_mm));
    }
    std::vector<RoutePoint> way{pts.front()};
    for (std::size_t i = 1; i + 1 < pts.size(); ++i) {
        const auto [x0, y0] = pts[i - 1];
        const auto [x1, y1] = pts[i];
        const auto [x2, y2] = pts[i + 1];
        if (!((x0 == x1 && x1 == x2) || (y0 == y1 && y1 == y2))) {
            way.push_back(pts[i]);
        }
    }
    way.push_back(pts.back());
    return way;
}

}  // namespace schgen
