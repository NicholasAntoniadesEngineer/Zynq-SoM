#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <tuple>
#include <unordered_map>
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

double overlap_area(const Box4& a, const Box4& b);
Box4 text_box(const std::string& txt, double x, double y, double size,
              double margin);
double point_box_dist(double x, double y, const Box4& box);
double seg_box_dist(double x1, double y1, double x2, double y2,
                    const Box4& box);
std::vector<std::vector<std::pair<double, std::string>>> band_cover(
    const std::vector<std::pair<double, std::string>>& points, double reach);
std::pair<bool, double> coverage_ok(
    double u, double v, const std::vector<std::pair<double, double>>& members,
    double bound);
bool point_on_seg(double px, double py, double x0, double y0, double x1,
                  double y1, bool interior_only);

class SilkBoxIndex {
public:
    explicit SilkBoxIndex(double cell);
    void add(const Box4& box);
    double pen(const Box4& gb) const;
    bool hits(const Box4& gb) const;
    const std::vector<Box4>& boxes() const { return boxes_; }

private:
    int cell_of(double value) const;
    std::uint64_t key(int gx, int gy) const;
    std::vector<int> near(const Box4& box) const;

    double cell_ = 8.0;
    std::vector<Box4> boxes_;
    std::unordered_map<std::uint64_t, std::vector<int>> cells_;
};

class BreatheGrid {
public:
    BreatheGrid(double board_w, double board_h, double cell, double origin_x,
                double origin_y);
    void stamp(const Box4& box, int val);
    bool free(const Box4& box) const;

private:
    int nx_ = 0;
    int ny_ = 0;
    double cell_ = 0.0;
    double origin_x_ = 0.0;
    double origin_y_ = 0.0;
    std::vector<std::uint8_t> cells_;
};

struct ClearLabel {
    double x = 0.0;
    double y = 0.0;
    Box4 box;
    double extra = 0.0;
};

ClearLabel place_clear_label(double cx0, double cy0, double cx1, double cy1,
                             const std::string& label, double size,
                             const SilkBoxIndex& occupied,
                             const std::optional<Box4>& bounds);
bool segments_cross(double ax0, double ay0, double ax1, double ay1,
                    double bx0, double by0, double bx1, double by1);

std::pair<Halo, Halo> zone_fanout_reach(
    double zw, double zh,
    const std::vector<std::tuple<double, double, double, double, int, double>>&
        members,
    int min_subject_pins);

}  // namespace schgen
