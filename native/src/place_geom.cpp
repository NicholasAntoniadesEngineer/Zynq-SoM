#include "schgen/place_geom.hpp"

#include "schgen/quantize.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace schgen {

double next_flag_x(double fx, double flag_pitch, double prev_w, double width,
                   double unit, double extra) {
    return gceil(fx + std::max(flag_pitch, prev_w / 2.0 + width / 2.0 + extra),
                 unit);
}

std::pair<double, double> flags_row_origin(double extent_x0, double extent_y1,
                                           double unit) {
    return {gsnap(extent_x0 + 4.0 * unit, unit),
            gceil(extent_y1 + 6.0 * unit, unit)};
}

double conn_signed_ceil(int sign, double mag, double unit) {
    if (sign != 1 && sign != -1) {
        throw std::runtime_error("conn_signed_ceil: sign must be +1 or -1");
    }
    return static_cast<double>(sign) * gceil(mag, unit);
}

double conn_gnd_x(int sign, double label_edge, double mid_x,
                  double strip_reach, double extra, double unit) {
    const double inner_limit =
        std::max(label_edge, std::fabs(mid_x) + strip_reach);
    return conn_signed_ceil(sign, inner_limit + extra, unit);
}

FarmWrap farm_wrap_advance(double col_x, double max_right, bool has_cur,
                           double farm_left, double cy, double row_step,
                           double unit) {
    FarmWrap out;
    out.col_x = col_x;
    out.cy = cy;
    if (col_x > max_right && has_cur) {
        out.wrapped = true;
        out.col_x = farm_left;
        out.cy = gceil(cy + row_step, unit);
    }
    return out;
}

double conn_flag_y(double extent_y1, double unit) {
    return gceil(extent_y1 + 8.0 * unit, unit);
}

double conn_flag_x0(double flag_pitch, int rail_count, double unit) {
    if (rail_count < 1) {
        throw std::runtime_error("conn_flag_x0: rail_count required");
    }
    return gsnap(-flag_pitch * static_cast<double>(rail_count - 1) / 2.0,
                 unit);
}

}  // namespace schgen
