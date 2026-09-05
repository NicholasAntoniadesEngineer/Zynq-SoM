#pragma once

#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "schgen/occupancy.hpp"
#include "schgen/seat.hpp"

namespace schgen {

struct ShelfItem {
    std::string ref;
    Box4 halo;
    double extra = 0.0;
    bool is_cp = false;
};

struct ShelfOcc {
    Box4 box;
    double extra = 0.0;
    bool is_cp = false;
};

struct ShelfPacked {
    std::vector<std::tuple<std::string, double, double>> placed;
    double packed_w = 0.0;
    double packed_h = 0.0;
};

ShelfPacked shelf_pack(const std::vector<ShelfItem>& items, double target_w,
                       const std::vector<ShelfOcc>& blockers, double zone_pad);

struct ViaObstacle {
    double cx = 0.0;
    double cy = 0.0;
    double hx = 0.0;
    double hy = 0.0;
    std::string nname;
    double drill = 0.0;
    std::string label;
};

struct ViaSiteSpec {
    double origin_x = 0.0;
    double origin_y = 0.0;
    double board_w = 0.0;
    double board_h = 0.0;
    double edge = 0.0;
    double via_size = 0.0;
    double via_drill = 0.0;
    double via_clear = 0.0;
    double hole_samenet = 0.0;
    double via_h2h = 0.0;
    double via_spacing = 0.0;
};

struct ViaBlockHit {
    bool blocked = false;
    std::string kind;
    std::string label;
    std::string nname;
    double x = 0.0;
    double y = 0.0;
};

ViaBlockHit via_site_blocker(
    double vx, double vy, const ViaSiteSpec& spec,
    const std::vector<ViaObstacle>& obstacles,
    const std::vector<std::pair<double, double>>& chosen);

std::vector<std::pair<double, double>> fallback_via_sites(
    double x0, double y0, double x1, double y1, double via_size,
    double pitch);

std::pair<Halo, Halo> zone_fanout_reach(
    double zw, double zh,
    const std::vector<std::tuple<double, double, double, double, int, double>>&
        members,
    int min_subject_pins);

}  // namespace schgen
