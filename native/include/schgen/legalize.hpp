#pragma once

#include <cstddef>
#include <optional>
#include <utility>
#include <vector>

#include "schgen/seat.hpp"

namespace schgen {

struct PairAxis {
    bool axis_x = true;
    bool a_first = true;
};

struct BellmanResult {
    bool feasible = false;
    std::vector<double> dist;
    std::vector<int> cycle_edges;
};

PairAxis pair_axis(const Box4& a, const Box4& b);

BellmanResult bellman_ford(std::size_t node_count,
                           const std::vector<int>& src,
                           const std::vector<int>& dst,
                           const std::vector<double>& cost);

double flow_budget(double board_w, double board_h,
                   const std::optional<Box4>& som_core);
double bbox_gap(const Box4& a, const Box4& b);
std::pair<double, double> facing_dot(double zone_x, double zone_y,
                                     double out_x, double out_y,
                                     double down_x, double down_y);

}  // namespace schgen
