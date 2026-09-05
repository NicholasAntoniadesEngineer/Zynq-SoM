#pragma once

#include <cstddef>
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

}  // namespace schgen
