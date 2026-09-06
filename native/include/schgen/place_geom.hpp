#pragma once

#include <utility>
#include <vector>

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

std::pair<double, double> rail_decouple_origin(double extent_x0,
                                               double extent_y1, double unit);

double farm_compact_col(double col_x, double body_x0, double span,
                        double hang_stub, double unit);

double farm_compact_cy(double ay, double cluster_dy, double body_y1,
                       double hang_stub, double unit);

double farm_lift_cy(double cy, double floor, double hang_stub, double unit);

double farm_run_ry(double run_cy, double drop);

double farm_run_mid(double first, double last, double unit);

double block_area(double w, double h);

std::pair<double, double> box_center(double x, double y, double w, double h);

double port_label_x(double pin_x, double run, double sign);

std::vector<double> buck_cin_cols(double pv_x, double cluster_dx,
                                  double cap_pitch, int n, double unit);

double template_clear_pad(double clear, double margin, double pad);

double relax_pad(int scale, double step);

}  // namespace schgen
