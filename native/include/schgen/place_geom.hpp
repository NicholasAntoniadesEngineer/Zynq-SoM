#pragma once

#include <utility>

namespace schgen {

double next_flag_x(double fx, double flag_pitch, double prev_w, double width,
                   double unit, double extra);

std::pair<double, double> flags_row_origin(double extent_x0, double extent_y1,
                                           double unit);

double conn_signed_ceil(int sign, double mag, double unit);

double conn_gnd_x(int sign, double label_edge, double mid_x,
                  double strip_reach, double extra, double unit);

struct FarmWrap {
    bool wrapped = false;
    double col_x = 0.0;
    double cy = 0.0;
};

FarmWrap farm_wrap_advance(double col_x, double max_right, bool has_cur,
                           double farm_left, double cy, double row_step,
                           double unit);

double conn_flag_y(double extent_y1, double unit);

double conn_flag_x0(double flag_pitch, int rail_count, double unit);

}  // namespace schgen
