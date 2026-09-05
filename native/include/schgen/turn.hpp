#pragma once

#include <utility>
#include <vector>

#include "schgen/seat.hpp"

namespace schgen {

std::pair<double, double> turn_point(double x, double y, double deg);
Box4 turn_box(const Box4& box, double deg);
std::pair<double, double> pad_half_extent(double size_w, double size_h,
                                          double deg);
std::vector<std::pair<double, double>> corners_rot(
    const Box4& rect, double rot, double inst_x, double inst_y, double lo_x,
    double lo_y, double hi_x, double hi_y, int decimals);

}  // namespace schgen
