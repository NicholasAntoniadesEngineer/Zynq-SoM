#pragma once

#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace schgen {

struct PackAnchorIn {
    bool face_override = false;
    char face = '\0';
    double som_x = 0.0;
    double som_y = 0.0;
    double som_w = 0.0;
    double som_h = 0.0;
    double som_halo = 0.0;
    double block_w = 0.0;
    double block_h = 0.0;
    double zone_ax = 0.0;
    double zone_ay = 0.0;
    bool exclusive = false;
    bool inboard = false;
    bool zone_is_at_edge = false;
    char edge = '\0';
    double eb_x = 0.0;
    double eb_y = 0.0;
    double eb_w = 0.0;
    double eb_h = 0.0;
    double eb_cx = 0.0;
    double eb_cy = 0.0;
    double pull_weight = 0.0;
    bool has_soft_pull = false;
    double pull_x = 0.0;
    double pull_y = 0.0;
    double zone_w = 0.0;
    double som_w_scale = 0.0;
    double som_pull = 0.0;
    double aff_pow = 0.0;
    double som_cx = 0.0;
    double som_cy = 0.0;
    std::vector<std::tuple<double, double, double>> affinity;
};

std::pair<double, double> pack_anchor(const PackAnchorIn& in);
std::pair<double, double> zone_anchor(char zone, double som_x, double som_y,
                                      double som_w, double som_h,
                                      double board_w, double board_h);
std::string j_edge_of(double connector_x, double connector_y, double som_w,
                      double som_h);
std::vector<std::pair<std::string, std::string>> j_edge_map(
    const std::vector<std::tuple<std::string, double, double>>& connectors,
    double som_w, double som_h);
std::optional<std::string> dominant_j(
    const std::vector<std::pair<std::string, int>>& affinity);
std::vector<std::string> affinity_j_from_expect(const std::string& expect);
std::optional<std::string> affinity_j_from_target(const std::string& target);
std::vector<std::pair<std::string, std::vector<std::pair<std::string, int>>>>
j_affinity(
    const std::vector<std::string>& sheets,
    const std::vector<std::tuple<std::string, bool, std::string,
                                 std::vector<std::string>>>& bindings);

}  // namespace schgen
