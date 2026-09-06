#pragma once

#include "schgen/occupancy.hpp"
#include "schgen/pack_anchor.hpp"

#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace schgen {

struct RefineBlock {
    std::string name;
    double x = 0.0;
    double y = 0.0;
    double w = 0.0;
    double h = 0.0;
    Halo reach;
    Halo inset;
    int mask = 0;
    std::vector<Comp> comps;
    PackAnchorIn anchor;
    std::string pull_to;
    std::vector<std::pair<std::string, double>> aff_named;
};

struct RefineResult {
    std::vector<std::pair<double, double>> poses;
    int passes = 0;
};

RefineResult refine_pack_passes(
    const Occupancy& occupancy, std::vector<RefineBlock> blocks,
    const std::unordered_map<std::string, std::pair<double, double>>&
        start_centers,
    int max_passes, double board_w, double board_h);

struct SeatShapeCand {
    int index = 0;
    double w = 0.0;
    double h = 0.0;
    Halo reach;
    Halo inset;
    int mask = 0;
    std::string side;
    std::vector<Comp> comps;
    double win_x0 = 0.0;
    double win_x1 = 0.0;
    double win_y0 = 0.0;
    double win_y1 = 0.0;
};

struct SeatShapeHit {
    std::string side;
    int index = 0;
    double x = 0.0;
    double y = 0.0;
    double w = 0.0;
    double h = 0.0;
    Halo reach;
    Halo inset;
    std::vector<Comp> comps;
    double dist_key = 0.0;
};

std::vector<SeatShapeHit> seat_shape_sides(
    const Occupancy& occupancy, double anchor_x, double anchor_y,
    const std::vector<SeatShapeCand>& cands, double board_w, double board_h,
    double clear);

}  // namespace schgen
