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
std::pair<double, std::string> channel_gap_mm(
    bool near_max_adjacent, int cross_airwire_count, double clear,
    int channel_min_nets, double channel_floor_mm, double channel_per_net_mm);

struct BuiltSep {
    std::string axis;
    std::string lo;
    std::string hi;
    double gap = 0.0;
    std::string basis;
    bool flippable = true;
};

std::vector<BuiltSep> legalize_build_seps(
    const std::vector<std::string>& names,
    const std::vector<Box4>& seed_rects,
    const std::vector<std::string>& fixed_names,
    const std::vector<Box4>& fixed_rects,
    const std::vector<std::tuple<std::string, std::string, int>>& demand_rows,
    const std::vector<std::pair<std::string, std::string>>& near_max_pairs,
    double clear, int channel_min_nets, double channel_floor_mm,
    double channel_per_net_mm);

bool rects_overlap_any(const std::vector<Box4>& probes,
                       const std::vector<Box4>& obstacles, double eps);

struct EvalTermIn {
    std::string kind;
    std::string subject;
    std::string target;
    double bound = 0.0;
    bool bound_set = false;
    std::vector<std::string> out_refs;
};

struct EvalMetric {
    std::string name;
    std::vector<std::tuple<std::string, double, double>> offsets;
    std::vector<std::tuple<std::string, double, double, double, double>>
        pad_union;
};

struct EvalTermOut {
    double measured = 0.0;
    double bound = 0.0;
    double margin = 0.0;
    bool ok = false;
    std::string note;
};

std::vector<EvalTermOut> evaluate_terms(
    double board_w, double board_h, const std::optional<Box4>& som_core,
    const std::vector<std::pair<std::string, std::pair<double, double>>>&
        poses,
    const std::vector<EvalMetric>& metrics, const std::vector<EvalTermIn>& terms,
    const std::vector<std::pair<std::string, double>>& far_guard,
    const std::vector<std::pair<std::string, Box4>>& som_j_rects,
    double origin_x, double origin_y);

struct NamedEdge {
    std::string src;
    std::string dst;
    double cost = 0.0;
};

std::pair<std::vector<double>, std::vector<double>> legalize_descend_passes(
    const std::vector<std::string>& names,
    const std::vector<double>& pos_x, const std::vector<double>& pos_y,
    const std::vector<double>& seed_x, const std::vector<double>& seed_y,
    const std::vector<NamedEdge>& edges_x,
    const std::vector<NamedEdge>& edges_y,
    const std::vector<std::pair<std::string, std::string>>& hops,
    const std::vector<std::pair<std::string, std::pair<double, double>>>&
        cent_off,
    const std::vector<std::pair<std::string, std::pair<double, double>>>&
        fixed_poses,
    double som_mid_x, double som_mid_y, bool has_som, bool seed_only,
    double hop_weight, double seed_weight, int median_passes);
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

struct WallSepEdge {
    std::string src;
    std::string dst;
    double cost = 0.0;
    std::string kind;
    int sep_index = -1;
    std::string wall_name;
};

struct SepSpec {
    bool axis_x = true;
    std::string lo;
    std::string hi;
    double gap = 0.0;
};

std::vector<WallSepEdge> wall_sep_edges(
    bool axis_x, const std::vector<std::string>& names,
    const std::vector<double>& sizes, double span, double clear,
    const std::vector<SepSpec>& seps,
    const std::vector<std::pair<std::string, Box4>>& frects);

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

std::pair<double, double> interior_dims(double area, double aspect,
                                        double min_mm, double max_mm);
std::tuple<double, double, double, double, double, double> derive_outline_wh(
    double som_w, double som_h, double halo, double edge_band, double perim,
    double pack_eff, double comp_area);

struct RepairSep {
    bool axis_x = true;
    std::string lo;
    std::string hi;
    double gap = 0.0;
    bool flippable = true;
};

struct RepairAxisResult {
    bool ok = false;
    std::vector<double> pos;
    std::vector<RepairSep> seps;
    std::vector<std::tuple<std::string, std::string, bool>> flips;
    std::string fail;
};

RepairAxisResult legalize_repair_axis(
    bool axis_x, const std::vector<std::string>& names,
    const std::vector<double>& sizes, double span, double clear,
    const std::vector<RepairSep>& seps_in,
    const std::vector<std::pair<std::string, Box4>>& frects,
    const std::vector<NamedEdge>& extra, int repair_max);

}  // namespace schgen
