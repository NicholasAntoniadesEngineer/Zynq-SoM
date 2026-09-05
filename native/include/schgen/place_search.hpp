#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "schgen/seat.hpp"

namespace schgen {

struct NearRectGap {
    double gap = 0.0;
    int index = -1;
};

std::pair<double, double> dodge_value_off_nc(
    const std::string& text, double vp_x, double vp_y, double ax, double ay,
    double unit, double char_w, double line_h, double size,
    const std::vector<Box4>& nc_boxes, double nc_pad);

bool vband_stem_free(double x, double y0, double y1,
                     const std::vector<Box4>& segs, double pad);

std::optional<double> lane_x(int sgn, double y0, double y1, double start,
                             double unit, double half_w, double y_pad,
                             double spot_pad, const std::vector<Box4>& parts,
                             const std::vector<Box4>& segs,
                             const std::vector<Box4>& ncs);

bool foreign_rows_clear(const Box4& box,
                        const std::vector<double>& foreign_ys, double eps);

double cell_floor(double x0, double x1, const std::vector<Box4>& boxes,
                  const std::vector<Box4>& segs);

NearRectGap nearest_rect_gap(const Box4& subject,
                             const std::vector<Box4>& others,
                             double touch_eps);

Box4 body_box(double x0, double y0, double x1, double y1, double ax,
              double ay, int rot);
Box4 boxes_paths_extent(const std::vector<Box4>& boxes,
                        const std::vector<std::pair<double, double>>& pts);
double band_edge(double y0, double y1, int side, double default_edge,
                 const std::vector<Box4>& boxes,
                 const std::vector<Box4>& segs);

}  // namespace schgen
