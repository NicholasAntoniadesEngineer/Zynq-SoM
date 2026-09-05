#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <tuple>
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

std::optional<std::pair<double, double>> predicted_centroid(
    double pose_x, double pose_y, double origin_x, double origin_y,
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    const std::vector<std::string>* refs);

double channel_demand_mm(int n_airwires, int min_nets, double floor_mm,
                         double per_net_mm);
std::optional<Box4> pad_union_hull(
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        pad_union);
std::pair<double, double> centroid_offset(
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    double half_w, double half_h);

std::optional<Box4> predicted_bbox(
    double pose_x, double pose_y, double origin_x, double origin_y,
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        pad_union);

}  // namespace schgen
