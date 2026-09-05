#include "schgen/place_search.hpp"

#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/quantize.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>

namespace schgen {
namespace {

bool value_hits_nc(const std::string& text, double px, double py, double size,
                   double char_w, double line_h,
                   const std::vector<Box4>& nc_boxes, double nc_pad) {
    const Box4 bx = centered_box(text, px, py, size, char_w, line_h, false);
    for (const Box4& nc : nc_boxes) {
        if (bx.x0 - nc_pad < nc.x1 && bx.x1 + nc_pad > nc.x0
            && bx.y0 - nc_pad < nc.y1 && bx.y1 + nc_pad > nc.y0) {
            return true;
        }
    }
    return false;
}

}  // namespace

std::pair<double, double> dodge_value_off_nc(
    const std::string& text, double vp_x, double vp_y, double ax, double ay,
    double unit, double char_w, double line_h, double size,
    const std::vector<Box4>& nc_boxes, double nc_pad) {
    if (!value_hits_nc(text, vp_x, vp_y, size, char_w, line_h, nc_boxes,
                       nc_pad)) {
        return {vp_x, vp_y};
    }
    const double dx = vp_x - ax;
    const double dy = vp_y - ay;
    double step_x = 0.0;
    double step_y = 0.0;
    if (std::fabs(dy) >= std::fabs(dx)) {
        step_y = dy >= 0.0 ? unit : -unit;
    } else {
        step_x = dx >= 0.0 ? unit : -unit;
    }
    double px = vp_x;
    double py = vp_y;
    for (int step_index = 0; step_index < 8; ++step_index) {
        px = py_round(px + step_x, 3);
        py = py_round(py + step_y, 3);
        if (!value_hits_nc(text, px, py, size, char_w, line_h, nc_boxes,
                           nc_pad)) {
            return {px, py};
        }
    }
    return {vp_x, vp_y};
}

bool vband_stem_free(double x, double y0, double y1,
                     const std::vector<Box4>& segs, double pad) {
    for (const Box4& seg : segs) {
        const double a = std::min(seg.x0, seg.x1);
        const double b = std::max(seg.x0, seg.x1);
        const double c = std::min(seg.y0, seg.y1);
        const double d = std::max(seg.y0, seg.y1);
        if (a - pad <= x && x <= b + pad && c - pad <= y1 && d + pad >= y0) {
            return false;
        }
    }
    return true;
}

std::optional<double> lane_x(int sgn, double y0, double y1, double start,
                             double unit, double half_w, double y_pad,
                             double spot_pad, const std::vector<Box4>& parts,
                             const std::vector<Box4>& segs,
                             const std::vector<Box4>& ncs) {
    double x = sgn < 0 ? gfloor(start, unit) : gceil(start, unit);
    for (int try_index = 0; try_index < 120; ++try_index) {
        const Box4 band{x - half_w, y0 - y_pad, x + half_w, y1 + y_pad};
        if (spot_free(band, spot_pad, parts, segs, ncs)) {
            return x;
        }
        x = py_round(x + static_cast<double>(sgn) * 2.0 * unit, 3);
    }
    return std::nullopt;
}

bool foreign_rows_clear(const Box4& box,
                        const std::vector<double>& foreign_ys, double eps) {
    const double y0 = box.y0;
    const double y1 = box.y1;
    for (double row_y : foreign_ys) {
        if (y0 - eps < row_y && row_y < y1 + eps) {
            return false;
        }
    }
    return true;
}

double cell_floor(double x0, double x1, const std::vector<Box4>& boxes,
                  const std::vector<Box4>& segs) {
    double floor_y = 0.0;
    for (const Box4& box : boxes) {
        if (box.x0 < x1 && box.x1 > x0) {
            floor_y = std::max(floor_y, box.y1);
        }
    }
    for (const Box4& seg : segs) {
        if (seg.x0 < x1 && seg.x1 > x0) {
            floor_y = std::max(floor_y, seg.y1);
        }
    }
    return floor_y;
}

NearRectGap nearest_rect_gap(const Box4& subject,
                             const std::vector<Box4>& others,
                             double touch_eps) {
    double best_gap = std::numeric_limits<double>::infinity();
    int best_index = -1;
    for (std::size_t other_index = 0; other_index < others.size();
         ++other_index) {
        const double gap = rect_gap(subject, others[other_index]);
        if (gap < best_gap) {
            best_gap = gap;
            best_index = static_cast<int>(other_index);
        }
    }
    const double clearance = best_gap < touch_eps ? 0.0 : best_gap;
    return NearRectGap{clearance, best_index};
}

Box4 body_box(double x0, double y0, double x1, double y1, double ax,
              double ay, int rot) {
    const double xs[2] = {x0, x1};
    const double ys[2] = {y0, y1};
    Box4 out{};
    bool first = true;
    for (double px : xs) {
        for (double py : ys) {
            const auto p = sch_xform(px, py, ax, ay, rot);
            if (first) {
                out = Box4{p.first, p.second, p.first, p.second};
                first = false;
            } else {
                out.x0 = std::min(out.x0, p.first);
                out.y0 = std::min(out.y0, p.second);
                out.x1 = std::max(out.x1, p.first);
                out.y1 = std::max(out.y1, p.second);
            }
        }
    }
    return out;
}

Box4 boxes_paths_extent(const std::vector<Box4>& boxes,
                        const std::vector<std::pair<double, double>>& pts) {
    Box4 out{};
    bool any = false;
    auto absorb = [&](double x, double y) {
        if (!any) {
            out = Box4{x, y, x, y};
            any = true;
            return;
        }
        out.x0 = std::min(out.x0, x);
        out.y0 = std::min(out.y0, y);
        out.x1 = std::max(out.x1, x);
        out.y1 = std::max(out.y1, y);
    };
    for (const Box4& box : boxes) {
        absorb(box.x0, box.y0);
        absorb(box.x1, box.y1);
    }
    for (const auto& p : pts) {
        absorb(p.first, p.second);
    }
    if (!any) {
        return Box4{0.0, 0.0, 0.0, 0.0};
    }
    return out;
}

double band_edge(double y0, double y1, int side, double default_edge,
                 const std::vector<Box4>& boxes,
                 const std::vector<Box4>& segs) {
    double edge = default_edge;
    for (const Box4& box : boxes) {
        if (box.y0 < y1 && box.y1 > y0) {
            edge = side < 0 ? std::min(edge, box.x0) : std::max(edge, box.x1);
        }
    }
    for (const Box4& seg : segs) {
        if (seg.y0 < y1 && seg.y1 > y0) {
            edge = side < 0 ? std::min(edge, seg.x0) : std::max(edge, seg.x1);
        }
    }
    return edge;
}

}  // namespace schgen
