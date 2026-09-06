#pragma once

#include <utility>
#include <vector>

#include "schgen/seat.hpp"

namespace schgen {

std::pair<double, double> turn_point(double x, double y, double deg);
std::pair<double, double> world_turned_point(double inst_x, double inst_y,
                                             double lx, double ly, double rot,
                                             int decimals);
Box4 turn_box(const Box4& box, double deg);
std::pair<double, double> pad_half_extent(double size_w, double size_h,
                                          double deg);
double rotate_pad_angle(double current_deg, double footprint_deg);
std::pair<double, double> sch_xform(double x, double y, double ax, double ay,
                                    int rot);
std::pair<double, double> pin_page_position(double pin_x, double pin_y,
                                            double anchor_x, double anchor_y,
                                            int rotation);
std::pair<double, double> stem_dir(int pin_rot, int part_rot);

std::vector<std::pair<double, double>> corners_rot(
    const Box4& rect, double rot, double inst_x, double inst_y, double lo_x,
    double lo_y, double hi_x, double hi_y, int decimals);

}  // namespace schgen
