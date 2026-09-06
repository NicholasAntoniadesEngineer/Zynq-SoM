#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace schgen {

using RouteCell = std::pair<int, int>;
using RoutePoint = std::pair<double, double>;

bool route_snap_ok(double value, double grid);
RouteCell route_cell_of(double x, double y, double grid);
RoutePoint route_point_of(int i, int j, double grid);
std::vector<RouteCell> route_cells_between(RoutePoint a, RoutePoint b,
                                           double grid);

class RouteGrid {
public:
    void claim(const std::string& owner, const std::vector<RouteCell>& cells,
               const std::string& what);
    void block_box(double x0, double y0, double x1, double y1, double grid);
    bool free_or(const std::string& net, RouteCell cell) const;
    std::vector<RouteCell> occupied() const;

private:
    static std::uint64_t pack(int i, int j);
    std::unordered_map<std::uint64_t, std::string> owner_;
};

std::vector<RoutePoint> route_bfs_join(
    const RouteGrid& grid, const std::string& net,
    const std::vector<RoutePoint>& comp_a,
    const std::vector<RoutePoint>& comp_b, double grid_mm);

}  // namespace schgen
