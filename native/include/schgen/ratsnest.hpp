#pragma once

#include <map>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace schgen {
// x, y, reference, sheet; point order defines deterministic MST tie-breaking.
using RatsnestPad = std::tuple<double, double, std::string, std::string>;
using RatsnestNets = std::map<std::string, std::vector<RatsnestPad>>;
using RatsnestEdges = std::map<std::string, std::vector<std::pair<int, int>>>;
RatsnestEdges ratsnest_mst(const RatsnestNets& nets);
// Sorted net order and edge order are part of the floating-point contract.
std::tuple<double, double, int> ratsnest_lengths(
    const RatsnestNets& nets, const RatsnestEdges& edges);
}
