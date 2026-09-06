#include "schgen/turn.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include "schgen/occupancy.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>
#include <vector>

namespace schgen {
namespace {

constexpr double kTurnSign = -1.0;
constexpr double kQuadrantDeg = 90.0;
constexpr double kFullTurnDeg = 360.0;
constexpr double kPi = 3.141592653589793;

double py_mod(double value, double modulus) {
    double rem = std::fmod(value, modulus);
    if ((rem < 0.0 && modulus > 0.0) || (rem > 0.0 && modulus < 0.0)) {
        rem += modulus;
    }
    return rem;
}

std::pair<double, double> quadrant_exact_cos_sin(double deg) {
    const double wrapped = py_mod(kTurnSign * deg, kFullTurnDeg);
    const double quarters = std::floor(wrapped / kQuadrantDeg);
    const double residual_deg = wrapped - quarters * kQuadrantDeg;
    const double residual = residual_deg * (kPi / 180.0);
    double cs = std::cos(residual);
    double sn = std::sin(residual);
    const int n = static_cast<int>(quarters);
    for (int i = 0; i < n; ++i) {
        const double next_cs = -sn;
        sn = cs;
        cs = next_cs;
    }
    return {cs, sn};
}

}  // namespace

std::pair<double, double> turn_point(double x, double y, double deg) {
    const auto cs_sn = quadrant_exact_cos_sin(deg);
    const double cs = cs_sn.first;
    const double sn = cs_sn.second;
    const double xcs = x * cs;
    const double ysn = y * sn;
    const double xsn = x * sn;
    const double ycs = y * cs;
    return {xcs - ysn, xsn + ycs};
}

Box4 turn_box(const Box4& box, double deg) {
    const double xs[2] = {box.x0, box.x1};
    const double ys[2] = {box.y0, box.y1};
    bool any = false;
    double min_x = 0.0;
    double min_y = 0.0;
    double max_x = 0.0;
    double max_y = 0.0;
    for (double px : xs) {
        for (double py : ys) {
            const auto p = turn_point(px, py, deg);
            if (!any) {
                min_x = max_x = p.first;
                min_y = max_y = p.second;
                any = true;
            } else {
                min_x = std::min(min_x, p.first);
                min_y = std::min(min_y, p.second);
                max_x = std::max(max_x, p.first);
                max_y = std::max(max_y, p.second);
            }
        }
    }
    return Box4{min_x, min_y, max_x, max_y};
}

double rotate_pad_angle(double current_deg, double footprint_deg) {
    return py_round(py_mod(current_deg + footprint_deg, 360.0), 4);
}

std::pair<double, double> pad_half_extent(double size_w, double size_h,
                                          double deg) {
    const auto cs_sn = quadrant_exact_cos_sin(deg);
    const double ct = std::fabs(cs_sn.first);
    const double st = std::fabs(cs_sn.second);
    const double hw = size_w / 2.0;
    const double hh = size_h / 2.0;
    return {ct * hw + st * hh, st * hw + ct * hh};
}

std::vector<std::pair<double, double>> corners_rot(
    const Box4& rect, double rot, double inst_x, double inst_y, double lo_x,
    double lo_y, double hi_x, double hi_y, int decimals) {
    if (decimals < 0) {
        throw std::runtime_error("corners_rot: decimals required");
    }
    const double px[4] = {rect.x0, rect.x1, rect.x1, rect.x0};
    const double py[4] = {rect.y0, rect.y0, rect.y1, rect.y1};
    std::vector<std::pair<double, double>> out;
    out.reserve(4);
    for (int i = 0; i < 4; ++i) {
        const auto t = turn_point(px[i], py[i], rot);
        const double bx = inst_x + t.first;
        const double by = inst_y + t.second;
        out.emplace_back(py_round(std::min(std::max(bx, lo_x), hi_x), decimals),
                         py_round(std::min(std::max(by, lo_y), hi_y), decimals));
    }
    return out;
}

std::pair<double, double> world_turned_point(double inst_x, double inst_y,
                                             double lx, double ly, double rot,
                                             int decimals) {
    if (decimals < 0) {
        throw std::runtime_error("world_turned_point: decimals required");
    }
    const auto t = turn_point(lx, ly, rot);
    return {py_round(inst_x + t.first, decimals),
            py_round(inst_y + t.second, decimals)};
}

std::pair<double, double> sch_xform(double x, double y, double ax, double ay,
                                    int rot) {
    int deg = rot % 360;
    if (deg < 0) {
        deg += 360;
    }
    const double rad = static_cast<double>(deg) * (3.141592653589793 / 180.0);
    const double c = py_round(std::cos(rad), 0);
    const double s = py_round(std::sin(rad), 0);
    return {py_round(ax + x * c - y * s, 3),
            py_round(ay - x * s - y * c, 3)};
}

std::pair<double, double> pin_page_position(double pin_x, double pin_y,
                                            double anchor_x, double anchor_y,
                                            int rotation) {
    int deg = rotation % 360;
    if (deg < 0) {
        deg += 360;
    }
    const double rad = static_cast<double>(deg) * (3.141592653589793 / 180.0);
    const double c = py_round(std::cos(rad), 0);
    const double s = py_round(std::sin(rad), 0);
    return {py_round(anchor_x + pin_x * c - pin_y * s, 4),
            py_round(anchor_y - pin_x * s - pin_y * c, 4)};
}

std::pair<double, double> stem_dir(int pin_rot, int part_rot) {
    int deg = pin_rot % 360;
    if (deg < 0) {
        deg += 360;
    }
    double sx = 0.0;
    double sy = 0.0;
    if (deg == 0) {
        sx = 1.0;
        sy = 0.0;
    } else if (deg == 90) {
        sx = 0.0;
        sy = 1.0;
    } else if (deg == 180) {
        sx = -1.0;
        sy = 0.0;
    } else if (deg == 270) {
        sx = 0.0;
        sy = -1.0;
    } else {
        throw std::runtime_error(
            "stem_dir: pin rotation must be a cardinal angle");
    }
    int part_deg = part_rot % 360;
    if (part_deg < 0) {
        part_deg += 360;
    }
    const double rad = static_cast<double>(part_deg) * (3.141592653589793 / 180.0);
    const double c = py_round(std::cos(rad), 0);
    const double s = py_round(std::sin(rad), 0);
    return {sx * c - sy * s, -sx * s - sy * c};
}

}  // namespace schgen
