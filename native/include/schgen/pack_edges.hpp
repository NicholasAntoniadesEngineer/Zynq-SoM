#pragma once

#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "schgen/occupancy.hpp"
#include "schgen/seat.hpp"

namespace schgen {

struct PackEdgesSpec {
    double board_w = 0.0;
    double board_h = 0.0;
    double edge_margin = 0.0;
    double edge_inset = 0.0;
    double clear = 0.0;
    double cable_neighbor_gap = 0.0;
    double overmold_side_gap = 0.0;
    double affinity_floor = 0.0;
    double som_x = 0.0;
    double som_y = 0.0;
    double som_w = 0.0;
    double som_h = 0.0;
};

struct PackEdgeJack {
    std::string ref;
    double x = 0.0;
    double y = 0.0;
};

struct PackEdgeBlock {
    std::string name;
    double w = 0.0;
    double h = 0.0;
    std::optional<double> order_hint;
    Halo reach;
    Halo inset;
    std::vector<std::pair<std::string, double>> j_aff;
    bool overmold = false;
    std::string current_edge;
    std::string assigned_edge;
};

struct PackEdgePose {
    std::string name;
    std::string edge;
    double x = 0.0;
    double y = 0.0;
};

struct PackEdgesResult {
    std::vector<PackEdgePose> poses;
    std::vector<std::string> spilled;
    std::size_t feasibility_intervals = 0;
    std::size_t feasibility_runs = 0;
    std::size_t feasibility_rejections = 0;
};

double edge_target(char edge, const PackEdgesSpec& spec,
                   const std::vector<std::pair<std::string, double>>& j_aff,
                   const std::vector<PackEdgeJack>& jacks);

// Null initial_keepouts preserves the existing unconstrained run objective.
// Non-null enables sequential initial feasibility against these body keepouts
// and already seated runs. This is not a complete joint solver; missing poses
// indicate failure, including a rounded candidate failing physical checks.
PackEdgesResult pack_edges(const std::vector<PackEdgeBlock>& blocks,
                           const std::vector<PackEdgeJack>& jacks,
                           const PackEdgesSpec& spec, QuantizationCounts* counts = nullptr,
                           const std::vector<Box4>* initial_keepouts = nullptr);

bool pick_sided_challenger(double est_inc, double est_chal, double eps);

std::vector<int> reseat_rank(
    double anchor_x, double anchor_y,
    const std::vector<std::tuple<double, double, double, double, std::string>>&
        placed);

std::pair<double, double> hf_cap_pose(double beside_oy, double inductor_left,
                                      double template_clear, double hx,
                                      QuantizationCounts* counts = nullptr);

}  // namespace schgen
