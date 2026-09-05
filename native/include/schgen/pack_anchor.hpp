#pragma once

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

}  // namespace schgen
