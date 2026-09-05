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
#include <optional>
#include <string>
#include <tuple>

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

std::optional<double> lane_in_dir(
    int sgn, double pt_x, double pt_y, double ty, double unit, double half_w,
    double y_pad, double spot_pad, double corridor_pad, double x_nudge,
    const std::vector<Box4>& parts, const std::vector<Box4>& spot_segs,
    const std::vector<Box4>& ncs, const std::vector<Box4>& corridor_boxes,
    const std::vector<Seg2>& corridor_segs) {
    const double y0 = std::min(pt_y, ty);
    const double y1 = std::max(pt_y, ty);
    const double start = pt_x + static_cast<double>(sgn) * 3.0 * unit;
    double x = sgn < 0 ? gfloor(start, unit) : gceil(start, unit);
    for (int try_index = 0; try_index < 120; ++try_index) {
        const Box4 band{x - half_w, y0 - y_pad, x + half_w, y1 + y_pad};
        if (spot_free(band, spot_pad, parts, spot_segs, ncs)
            && corridor_free(pt_y, pt_x + static_cast<double>(sgn) * x_nudge,
                             x, corridor_boxes, corridor_segs,
                             corridor_pad)) {
            return x;
        }
        x = py_round(x + static_cast<double>(sgn) * 2.0 * unit, 3);
    }
    return std::nullopt;
}

std::vector<EscapeLeg> escape_run_legs(
    double px, double py, double tx, double unit, double edge_clear,
    const std::vector<OwnedBox>& boxes, const std::vector<Box4>& parts,
    const std::vector<Box4>& spot_segs, const std::vector<Box4>& ncs,
    const std::vector<Box4>& corridor_boxes,
    const std::vector<Seg2>& corridor_segs, const std::vector<Box4>& stem_segs,
    double spot_pad, double corridor_pad, double stem_pad) {
    const double sgn = tx >= px ? 1.0 : -1.0;
    const double span_x0 = std::min(px, tx);
    const double span_x1 = std::max(px, tx);
    std::vector<Box4> blockers;
    for (std::size_t i = 0; i < boxes.size(); ++i) {
        const OwnedBox& body = boxes[i];
        if (body.kind != "body") {
            continue;
        }
        if (!(body.box.y0 - edge_clear < py && py < body.box.y1 + edge_clear)) {
            continue;
        }
        if (!(body.box.x0 < span_x1 && body.box.x1 > span_x0)) {
            continue;
        }
        Box4 owned = body.box;
        for (std::size_t j = 0; j < boxes.size(); ++j) {
            if (j == i) {
                continue;
            }
            const OwnedBox& other = boxes[j];
            if (other.owner != body.owner) {
                continue;
            }
            owned.x0 = std::min(owned.x0, other.box.x0);
            owned.y0 = std::min(owned.y0, other.box.y0);
            owned.x1 = std::max(owned.x1, other.box.x1);
            owned.y1 = std::max(owned.y1, other.box.y1);
        }
        blockers.push_back(owned);
    }
    std::vector<EscapeLeg> legs;
    if (blockers.empty()) {
        legs.push_back({{px, py}, {tx, py}});
        return legs;
    }
    std::vector<std::tuple<double, double, double, double>> spans;
    spans.reserve(blockers.size());
    for (const Box4& b : blockers) {
        spans.emplace_back(b.x0, b.x1, b.y0, b.y1);
    }
    std::sort(spans.begin(), spans.end());
    std::vector<std::tuple<double, double, double, double>> clusters;
    for (const auto& span : spans) {
        const double x0 = std::get<0>(span);
        const double x1 = std::get<1>(span);
        const double y0 = std::get<2>(span);
        const double y1 = std::get<3>(span);
        if (!clusters.empty()
            && x0 <= std::get<1>(clusters.back()) + 2.0 * unit) {
            auto& last = clusters.back();
            last = {std::min(std::get<0>(last), x0),
                    std::max(std::get<1>(last), x1),
                    std::min(std::get<2>(last), y0),
                    std::max(std::get<3>(last), y1)};
        } else {
            clusters.emplace_back(x0, x1, y0, y1);
        }
    }
    std::sort(clusters.begin(), clusters.end(),
              [sgn](const auto& a, const auto& b) {
                  return sgn < 0.0 ? std::get<0>(a) > std::get<0>(b)
                                   : std::get<0>(a) < std::get<0>(b);
              });
    double cur_x = px;
    for (const auto& cluster : clusters) {
        const double cx0 = std::get<0>(cluster);
        const double cx1 = std::get<1>(cluster);
        const double cy0 = std::get<2>(cluster);
        const double cy1 = std::get<3>(cluster);
        const double enter = sgn > 0.0 ? gfloor(cx0 - unit, unit)
                                       : gceil(cx1 + unit, unit);
        const double exitx = sgn > 0.0 ? gceil(cx1 + unit, unit)
                                       : gfloor(cx0 - unit, unit);
        const double lo = std::min(enter, exitx);
        const double hi = std::max(enter, exitx);
        std::optional<double> dy;
        for (int direction : {1, -1}) {
            const double base = direction > 0 ? gceil(cy1 + 2.0 * unit, unit)
                                              : gfloor(cy0 - 2.0 * unit, unit);
            for (int step = 0; step < 14; ++step) {
                const double cand = py_round(
                    base + static_cast<double>(direction * step) * unit, 3);
                const double ry0 = std::min(py, cand);
                const double ry1 = std::max(py, cand);
                if (corridor_free(cand, lo, hi, corridor_boxes, corridor_segs,
                                  corridor_pad)
                    && spot_free(Box4{enter - 0.1, ry0, enter + 0.1, ry1},
                                 spot_pad, parts, spot_segs, ncs)
                    && spot_free(Box4{exitx - 0.1, ry0, exitx + 0.1, ry1},
                                 spot_pad, parts, spot_segs, ncs)
                    && vband_stem_free(enter, ry0, ry1, stem_segs, stem_pad)
                    && vband_stem_free(exitx, ry0, ry1, stem_segs, stem_pad)) {
                    dy = cand;
                    break;
                }
            }
            if (dy) {
                break;
            }
        }
        if (!dy) {
            continue;
        }
        legs.push_back({{cur_x, py}, {enter, py}});
        legs.push_back({{enter, py}, {enter, *dy}});
        legs.push_back({{enter, *dy}, {exitx, *dy}});
        legs.push_back({{exitx, *dy}, {exitx, py}});
        cur_x = exitx;
    }
    legs.push_back({{cur_x, py}, {tx, py}});
    return legs;
}

std::vector<LabeledBox> pin_text_boxes(
    const std::vector<PinTextIn>& pins, double part_x, double part_y,
    int part_rot, bool pin_numbers_hidden, bool pin_names_hidden,
    double char_w, double line_h, double size) {
    std::vector<LabeledBox> out;
    for (const PinTextIn& pin : pins) {
        if (pin.hidden) {
            continue;
        }
        const auto tip = pin_page_position(pin.x, pin.y, part_x, part_y,
                                           part_rot);
        const auto dir = stem_dir(pin.rotation, part_rot);
        const double root_x = py_round(tip.first + dir.first * pin.length, 3);
        const double root_y = py_round(tip.second + dir.second * pin.length, 3);
        const double mid_x = (tip.first + root_x) / 2.0;
        const double mid_y = (tip.second + root_y) / 2.0;
        const bool horiz = dir.second == 0.0;
        if (!pin_numbers_hidden && !pin.number.empty()) {
            const auto wh = text_wh(pin.number, size, char_w, line_h);
            if (horiz) {
                out.push_back(LabeledBox{
                    Box4{mid_x - wh.first / 2.0, tip.second - 0.2 - wh.second,
                         mid_x + wh.first / 2.0, tip.second - 0.2},
                    "pin_number"});
            } else {
                out.push_back(LabeledBox{
                    Box4{tip.first - 0.2 - wh.second, mid_y - wh.first / 2.0,
                         tip.first - 0.2, mid_y + wh.first / 2.0},
                    "pin_number"});
            }
        }
        if (!pin_names_hidden && pin.name != "" && pin.name != "~") {
            auto wh = text_wh(pin.name, size, char_w, line_h);
            wh.first += 0.5;
            if (dir.first > 0.0) {
                out.push_back(LabeledBox{
                    Box4{root_x + 0.2, tip.second - wh.second / 2.0,
                         root_x + 0.2 + wh.first, tip.second + wh.second / 2.0},
                    "pin_name"});
            } else if (dir.first < 0.0) {
                out.push_back(LabeledBox{
                    Box4{root_x - 0.2 - wh.first, tip.second - wh.second / 2.0,
                         root_x - 0.2, tip.second + wh.second / 2.0},
                    "pin_name"});
            } else if (dir.second > 0.0) {
                out.push_back(LabeledBox{
                    Box4{tip.first - wh.second / 2.0, root_y + 0.2,
                         tip.first + wh.second / 2.0, root_y + 0.2 + wh.first},
                    "pin_name"});
            } else {
                out.push_back(LabeledBox{
                    Box4{tip.first - wh.second / 2.0, root_y - 0.2 - wh.first,
                         tip.first + wh.second / 2.0, root_y - 0.2},
                    "pin_name"});
            }
        }
    }
    return out;
}

}  // namespace schgen
