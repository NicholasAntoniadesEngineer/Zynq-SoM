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
double rect_gap(const Box4& a, const Box4& b);
std::pair<double, double> facing_dot(double zone_x, double zone_y,
                                     double out_x, double out_y,
                                     double down_x, double down_y);

std::optional<std::pair<double, double>> predicted_centroid(
    double pose_x, double pose_y, double origin_x, double origin_y,
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    const std::vector<std::string>* refs);

double channel_demand_mm(int n_airwires, int min_nets, double floor_mm,
                         double per_net_mm);
std::vector<std::pair<int, int>> mst_manhattan(
    const std::vector<std::pair<double, double>>& pts);
double weighted_median(const std::vector<std::pair<double, double>>& pulls);
bool constraint_edges_ok(const std::vector<int>& src,
                         const std::vector<int>& dst,
                         const std::vector<double>& cost,
                         const std::vector<double>& pos);
std::pair<double, double> constraint_bounds(int node,
                                            const std::vector<int>& src,
                                            const std::vector<int>& dst,
                                            const std::vector<double>& cost,
                                            const std::vector<double>& pos);
std::optional<double> min_box_gap(const std::vector<Box4>& a,
                                  const std::vector<Box4>& b);
std::optional<Box4> pad_union_hull(
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        pad_union);
std::pair<double, double> centroid_offset(
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    double half_w, double half_h);

struct NearMaxEdge {
    std::string src;
    std::string dst;
    double cost = 0.0;
    bool perp = false;
};

std::vector<NearMaxEdge> near_max_edges(
    const std::string& subject, const std::string& target, double bound,
    bool axis_x, const Box4& hull_s, const Box4& hull_g, const Box4& seed_s,
    const Box4& seed_g, bool s_movable, bool g_movable,
    const std::optional<std::pair<double, double>>& pose_s,
    const std::optional<std::pair<double, double>>& pose_g);

std::optional<Box4> predicted_bbox(
    double pose_x, double pose_y, double origin_x, double origin_y,
    const std::vector<std::tuple<std::string, double, double>>& offsets,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        pad_union);

}  // namespace schgen
