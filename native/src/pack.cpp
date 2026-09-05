#include "schgen/pack.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <set>
#include <stdexcept>

namespace schgen {
namespace {

double occ_gap(bool is_cp, double extra, bool r_cp, double r_extra) {
    const double a = is_cp ? 0.0 : r_extra;
    const double b = r_cp ? 0.0 : extra;
    return std::max(a, b);
}

bool shelf_free(double x0, double y0, double x1, double y1, double w_lim,
                double extra, bool is_cp, double zone_pad,
                const std::vector<ShelfOcc>& occ) {
    if (x1 > zone_pad + w_lim + 1e-6) {
        return false;
    }
    for (const ShelfOcc& r : occ) {
        const double g = occ_gap(is_cp, extra, r.is_cp, r.extra);
        if (!(x1 + g <= r.box.x0 || r.box.x1 + g <= x0
              || y1 + g <= r.box.y0 || r.box.y1 + g <= y0)) {
            return false;
        }
    }
    return true;
}

}  // namespace

ShelfPacked shelf_pack(const std::vector<ShelfItem>& items, double target_w,
                       const std::vector<ShelfOcc>& blockers, double zone_pad) {
    std::vector<ShelfItem> order = items;
    std::stable_sort(order.begin(), order.end(),
                     [](const ShelfItem& a, const ShelfItem& b) {
                         const double ah = a.halo.y1 - a.halo.y0;
                         const double bh = b.halo.y1 - b.halo.y0;
                         if (ah != bh) {
                             return ah > bh;
                         }
                         const double aw = a.halo.x1 - a.halo.x0;
                         const double bw = b.halo.x1 - b.halo.x0;
                         if (aw != bw) {
                             return aw > bw;
                         }
                         return a.ref < b.ref;
                     });
    std::vector<ShelfOcc> occ = blockers;
    std::vector<std::tuple<std::string, double, double>> placed;
    placed.reserve(order.size());
    double used_w = zone_pad;
    double used_h = zone_pad;
    for (const ShelfItem& it : order) {
        const double hw = it.halo.x1 - it.halo.x0;
        const double hh = it.halo.y1 - it.halo.y0;
        const double w_lim = std::max(target_w, hw);
        std::vector<double> xs;
        std::vector<double> ys;
        xs.push_back(zone_pad);
        ys.push_back(zone_pad);
        for (const ShelfOcc& r : occ) {
            const double g = occ_gap(it.is_cp, it.extra, r.is_cp, r.extra);
            xs.push_back(r.box.x1 + g);
            ys.push_back(r.box.y1 + g);
        }
        std::sort(xs.begin(), xs.end());
        xs.erase(std::unique(xs.begin(), xs.end()), xs.end());
        std::sort(ys.begin(), ys.end());
        ys.erase(std::unique(ys.begin(), ys.end()), ys.end());
        std::vector<double> xcand;
        for (double x : xs) {
            if (x + hw <= zone_pad + w_lim + 1e-6) {
                xcand.push_back(x);
            }
        }
        bool have = false;
        double sx = 0.0;
        double sy = 0.0;
        for (double y : ys) {
            for (double x : xcand) {
                if (shelf_free(x, y, x + hw, y + hh, w_lim, it.extra, it.is_cp,
                               zone_pad, occ)) {
                    sx = x;
                    sy = y;
                    have = true;
                    break;
                }
            }
            if (have) {
                break;
            }
        }
        if (!have) {
            throw std::runtime_error(
                "shelf_pack: no free slot for " + it.ref);
        }
        occ.push_back(ShelfOcc{
            Box4{sx, sy, sx + hw, sy + hh}, it.extra, it.is_cp});
        placed.emplace_back(it.ref, py_round(sx - it.halo.x0, 4),
                            py_round(sy - it.halo.y0, 4));
        used_w = std::max(used_w, sx + hw);
        used_h = std::max(used_h, sy + hh);
    }
    return ShelfPacked{
        std::move(placed),
        py_round(std::max(used_w, zone_pad) + zone_pad, 4),
        py_round(std::max(used_h, zone_pad) + zone_pad, 4)};
}

ViaBlockHit via_site_blocker(
    double vx, double vy, const ViaSiteSpec& spec,
    const std::vector<ViaObstacle>& obstacles,
    const std::vector<std::pair<double, double>>& chosen) {
    if (!(spec.origin_x + spec.edge <= vx
          && vx <= spec.origin_x + spec.board_w - spec.edge
          && spec.origin_y + spec.edge <= vy
          && vy <= spec.origin_y + spec.board_h - spec.edge)) {
        return ViaBlockHit{true, "edge", "", "", 0.0, 0.0};
    }
    const double vr = spec.via_size / 2.0;
    const double hr = spec.via_drill / 2.0;
    for (const ViaObstacle& o : obstacles) {
        const double dx = std::max(0.0, std::fabs(vx - o.cx) - o.hx);
        const double dy = std::max(0.0, std::fabs(vy - o.cy) - o.hy);
        const double gap = std::hypot(dx, dy);
        if (o.nname != "GND" && gap < vr + spec.via_clear) {
            return ViaBlockHit{true, "obs", o.label, o.nname, o.cx, o.cy};
        }
        if (o.nname == "GND" && gap < hr + spec.hole_samenet) {
            return ViaBlockHit{true, "obs", o.label, o.nname, o.cx, o.cy};
        }
        if (o.drill > 0.0
            && std::hypot(vx - o.cx, vy - o.cy)
                < hr + o.drill / 2.0 + spec.via_h2h) {
            return ViaBlockHit{true, "obs", o.label, o.nname, o.cx, o.cy};
        }
    }
    for (const auto& c : chosen) {
        if (std::hypot(vx - c.first, vy - c.second) < spec.via_spacing) {
            return ViaBlockHit{true, "thermal", "", "", c.first, c.second};
        }
    }
    return ViaBlockHit{};
}

std::vector<std::pair<double, double>> fallback_via_sites(
    double x0, double y0, double x1, double y1, double via_size,
    double pitch) {
    if (pitch <= 0.0) {
        throw std::runtime_error("fallback_via_sites: pitch required");
    }
    const double m = via_size / 2.0;
    x0 += m;
    y0 += m;
    x1 -= m;
    y1 -= m;
    const int ni = static_cast<int>((x1 - x0) / pitch) + 1;
    const int nj = static_cast<int>((y1 - y0) / pitch) + 1;
    std::vector<std::tuple<double, double, double>> ranked;
    ranked.reserve(static_cast<std::size_t>(std::max(0, ni) * std::max(0, nj)));
    for (int i = 0; i < ni; ++i) {
        for (int j = 0; j < nj; ++j) {
            const double sx = py_round(x0 + static_cast<double>(i) * pitch, 3);
            const double sy = py_round(y0 + static_cast<double>(j) * pitch, 3);
            ranked.emplace_back(py_round(std::hypot(sx, sy), 4), sy, sx);
        }
    }
    std::stable_sort(ranked.begin(), ranked.end());
    std::vector<std::pair<double, double>> out;
    out.reserve(ranked.size());
    for (const auto& row : ranked) {
        out.emplace_back(std::get<2>(row), std::get<1>(row));
    }
    return out;
}

std::pair<Halo, Halo> zone_fanout_reach(
    double zw, double zh,
    const std::vector<std::tuple<double, double, double, double, int, double>>&
        members,
    int min_subject_pins) {
    double rw = 0.0;
    double re = 0.0;
    double rn = 0.0;
    double rs = 0.0;
    double iw = std::numeric_limits<double>::infinity();
    double ie = std::numeric_limits<double>::infinity();
    double in_n = std::numeric_limits<double>::infinity();
    double is_s = std::numeric_limits<double>::infinity();
    for (const auto& m : members) {
        const double cx0 = std::get<0>(m);
        const double cy0 = std::get<1>(m);
        const double cx1 = std::get<2>(m);
        const double cy1 = std::get<3>(m);
        const int pins = std::get<4>(m);
        const double lim = std::get<5>(m);
        const double mw = cx0;
        const double me = zw - cx1;
        const double mn = cy0;
        const double ms = zh - cy1;
        iw = std::min(iw, mw);
        ie = std::min(ie, me);
        in_n = std::min(in_n, mn);
        is_s = std::min(is_s, ms);
        if (pins < min_subject_pins) {
            continue;
        }
        if (mw <= lim) {
            rw = std::max(rw, lim - mw);
        }
        if (me <= lim) {
            re = std::max(re, lim - me);
        }
        if (mn <= lim) {
            rn = std::max(rn, lim - mn);
        }
        if (ms <= lim) {
            rs = std::max(rs, lim - ms);
        }
    }
    if (iw == std::numeric_limits<double>::infinity()) {
        iw = 0.0;
        ie = 0.0;
        in_n = 0.0;
        is_s = 0.0;
    }
    return {
        Halo{py_round(rw, 4), py_round(re, 4), py_round(rn, 4),
             py_round(rs, 4)},
        Halo{py_round(iw, 4), py_round(ie, 4), py_round(in_n, 4),
             py_round(is_s, 4)}};
}

double overlap_area(const Box4& a, const Box4& b) {
    const double dx = std::min(a.x1, b.x1) - std::max(a.x0, b.x0);
    const double dy = std::min(a.y1, b.y1) - std::max(a.y0, b.y0);
    if (dx > 0.0 && dy > 0.0) {
        return dx * dy;
    }
    return 0.0;
}

Box4 text_box(const std::string& txt, double x, double y, double size,
              double margin) {
    const double thick = std::max(0.12, size * 0.15);
    const double n = static_cast<double>(std::max<std::size_t>(txt.size(), 1));
    const double w = n * size + thick;
    const double h = size + thick;
    return Box4{x - w / 2.0 - margin, y - h / 2.0 - margin,
                x + w / 2.0 + margin, y + h / 2.0 + margin};
}

double point_box_dist(double x, double y, const Box4& box) {
    const double dx = std::max(std::max(box.x0 - x, x - box.x1), 0.0);
    const double dy = std::max(std::max(box.y0 - y, y - box.y1), 0.0);
    return std::hypot(dx, dy);
}

double seg_box_dist(double x1, double y1, double x2, double y2,
                    const Box4& box) {
    const double lo_x = std::min(x1, x2);
    const double hi_x = std::max(x1, x2);
    const double lo_y = std::min(y1, y2);
    const double hi_y = std::max(y1, y2);
    const double dx = std::max(std::max(box.x0 - hi_x, lo_x - box.x1), 0.0);
    const double dy = std::max(std::max(box.y0 - hi_y, lo_y - box.y1), 0.0);
    return std::hypot(dx, dy);
}

std::vector<std::vector<std::pair<double, std::string>>> band_cover(
    const std::vector<std::pair<double, std::string>>& points, double reach) {
    std::vector<std::pair<double, std::string>> pts = points;
    std::stable_sort(pts.begin(), pts.end(),
                     [](const std::pair<double, std::string>& a,
                        const std::pair<double, std::string>& b) {
                         const double au = py_round(a.first, 4);
                         const double bu = py_round(b.first, 4);
                         if (au != bu) {
                             return au < bu;
                         }
                         return std::stoi(a.second) < std::stoi(b.second);
                     });
    std::vector<std::vector<std::pair<double, std::string>>> bands;
    std::size_t i = 0;
    while (i < pts.size()) {
        const double u0 = pts[i].first;
        std::size_t j = i;
        while (j < pts.size() && pts[j].first <= u0 + 2.0 * reach) {
            ++j;
        }
        bands.emplace_back(pts.begin() + static_cast<std::ptrdiff_t>(i),
                           pts.begin() + static_cast<std::ptrdiff_t>(j));
        i = j;
    }
    return bands;
}

std::pair<bool, double> coverage_ok(
    double u, double v, const std::vector<std::pair<double, double>>& members,
    double bound) {
    double worst = 0.0;
    for (const auto& m : members) {
        const double d = std::hypot(u - m.first, v - m.second);
        worst = std::max(worst, d);
        if (d > bound) {
            return {false, worst};
        }
    }
    return {true, worst};
}

SilkBoxIndex::SilkBoxIndex(double cell) : cell_(cell) {
    if (cell <= 0.0) {
        throw std::runtime_error("SilkBoxIndex: cell required");
    }
}

int SilkBoxIndex::cell_of(double value) const {
    return static_cast<int>(std::floor(value / cell_));
}

std::uint64_t SilkBoxIndex::key(int gx, int gy) const {
    return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(gx)) << 32)
        | static_cast<std::uint32_t>(gy);
}

void SilkBoxIndex::add(const Box4& box) {
    const int i = static_cast<int>(boxes_.size());
    boxes_.push_back(box);
    const int gx0 = cell_of(box.x0);
    const int gy0 = cell_of(box.y0);
    const int gx1 = cell_of(box.x1);
    const int gy1 = cell_of(box.y1);
    for (int gx = gx0; gx <= gx1; ++gx) {
        for (int gy = gy0; gy <= gy1; ++gy) {
            cells_[key(gx, gy)].push_back(i);
        }
    }
}

std::vector<int> SilkBoxIndex::near(const Box4& box) const {
    const int gx0 = cell_of(box.x0);
    const int gy0 = cell_of(box.y0);
    const int gx1 = cell_of(box.x1);
    const int gy1 = cell_of(box.y1);
    if (gx0 == gx1 && gy0 == gy1) {
        auto it = cells_.find(key(gx0, gy0));
        if (it == cells_.end()) {
            return {};
        }
        return it->second;
    }
    std::set<int> uniq;
    for (int gx = gx0; gx <= gx1; ++gx) {
        for (int gy = gy0; gy <= gy1; ++gy) {
            auto it = cells_.find(key(gx, gy));
            if (it == cells_.end()) {
                continue;
            }
            uniq.insert(it->second.begin(), it->second.end());
        }
    }
    return {uniq.begin(), uniq.end()};
}

double SilkBoxIndex::pen(const Box4& gb) const {
    double acc = 0.0;
    for (int i : near(gb)) {
        acc += overlap_area(gb, boxes_[static_cast<std::size_t>(i)]);
    }
    return acc;
}

bool SilkBoxIndex::hits(const Box4& gb) const {
    for (int i : near(gb)) {
        if (overlap_area(gb, boxes_[static_cast<std::size_t>(i)]) > 0.0) {
            return true;
        }
    }
    return false;
}

BreatheGrid::BreatheGrid(double board_w, double board_h, double cell,
                         double origin_x, double origin_y)
    : cell_(cell), origin_x_(origin_x), origin_y_(origin_y) {
    if (cell <= 0.0) {
        throw std::runtime_error("BreatheGrid: cell required");
    }
    nx_ = static_cast<int>(board_w / cell) + 2;
    ny_ = static_cast<int>(board_h / cell) + 2;
    if (nx_ <= 0 || ny_ <= 0) {
        throw std::runtime_error("BreatheGrid: board extent required");
    }
    cells_.assign(static_cast<std::size_t>(nx_) * static_cast<std::size_t>(ny_),
                  0);
}

void BreatheGrid::stamp(const Box4& box, int val) {
    const int c0 = static_cast<int>((box.x0 - origin_x_) / cell_);
    const int r0 = static_cast<int>((box.y0 - origin_y_) / cell_);
    const int c1 = static_cast<int>((box.x1 - origin_x_) / cell_);
    const int r1 = static_cast<int>((box.y1 - origin_y_) / cell_);
    if (c1 < 0 || r1 < 0 || c0 >= nx_ || r0 >= ny_) {
        return;
    }
    const int cc0 = std::max(0, c0);
    const int rr0 = std::max(0, r0);
    const int cc1 = std::min(nx_ - 1, c1);
    const int rr1 = std::min(ny_ - 1, r1);
    const std::uint8_t v = val ? 1 : 0;
    for (int r = rr0; r <= rr1; ++r) {
        const int base = r * nx_;
        for (int c = cc0; c <= cc1; ++c) {
            cells_[static_cast<std::size_t>(base + c)] = v;
        }
    }
}

bool BreatheGrid::free(const Box4& box) const {
    const double c0f = (box.x0 - origin_x_) / cell_;
    const double r0f = (box.y0 - origin_y_) / cell_;
    const double c1f = (box.x1 - origin_x_) / cell_;
    const double r1f = (box.y1 - origin_y_) / cell_;
    if (c0f < 0.0 || r0f < 0.0 || c1f >= static_cast<double>(nx_)
        || r1f >= static_cast<double>(ny_)) {
        return false;
    }
    const int c0 = static_cast<int>(c0f);
    const int r0 = static_cast<int>(r0f);
    const int c1 = static_cast<int>(c1f);
    const int r1 = static_cast<int>(r1f);
    for (int r = r0; r <= r1; ++r) {
        const int base = r * nx_;
        for (int c = c0; c <= c1; ++c) {
            if (cells_[static_cast<std::size_t>(base + c)]) {
                return false;
            }
        }
    }
    return true;
}

bool point_on_seg(double px, double py, double x0, double y0, double x1,
                  double y1, bool interior_only) {
    const double eps = 1e-6;
    const bool horizontal = std::fabs(y0 - y1) < eps;
    const bool vertical = std::fabs(x0 - x1) < eps;
    double lo = 0.0;
    double hi = 0.0;
    double coord = 0.0;
    if (horizontal) {
        if (std::fabs(py - y0) > eps) {
            return false;
        }
        lo = std::min(x0, x1);
        hi = std::max(x0, x1);
        coord = px;
    } else if (vertical) {
        if (std::fabs(px - x0) > eps) {
            return false;
        }
        lo = std::min(y0, y1);
        hi = std::max(y0, y1);
        coord = py;
    } else {
        return false;
    }
    if (interior_only) {
        return lo + eps < coord && coord < hi - eps;
    }
    return lo - eps <= coord && coord <= hi + eps;
}

namespace {

bool onboard_box(const Box4& box, const std::optional<Box4>& bounds) {
    if (!bounds.has_value()) {
        return true;
    }
    return box.x0 >= bounds->x0 && box.y0 >= bounds->y0
        && box.x1 <= bounds->x1 && box.y1 <= bounds->y1;
}

}  // namespace

ClearLabel place_clear_label(double cx0, double cy0, double cx1, double cy1,
                             const std::string& label, double size,
                             const SilkBoxIndex& occupied,
                             const SilkBoxIndex* placed,
                             const std::optional<Box4>& bounds) {
    const double midx = (cx0 + cx1) / 2.0;
    const double midy = (cy0 + cy1) / 2.0;
    const double thick = std::max(0.12, size * 0.15);
    const double n = static_cast<double>(std::max<std::size_t>(label.size(), 1));
    const double w = n * size + thick;
    const double h = size + thick;
    const double g = 0.9;
    bool have_best = false;
    bool have_any = false;
    double best_pen = 0.0;
    double best_any_pen = 0.0;
    ClearLabel best;
    ClearLabel best_any;
    static const double kRing[] = {0.0, 2.2, 4.4, 6.6, 9.0, 12.0, 15.0, 18.0};
    for (double extra : kRing) {
        const double dy = g + extra + h / 2.0;
        const double dx = g + extra + w / 2.0;
        const double cands[8][2] = {
            {midx, cy1 + dy},
            {midx, cy0 - dy},
            {cx1 + dx, midy},
            {cx0 - dx, midy},
            {cx1 + dx, cy1 + dy},
            {cx0 - dx, cy1 + dy},
            {cx1 + dx, cy0 - dy},
            {cx0 - dx, cy0 - dy},
        };
        for (const auto& cand : cands) {
            const Box4 box = text_box(label, cand[0], cand[1], size, 0.15);
            const Box4 gb{box.x0 - 0.02, box.y0 - 0.02, box.x1 + 0.02,
                          box.y1 + 0.02};
            const double pen = occupied.pen(gb)
                + (placed == nullptr ? 0.0 : placed->pen(gb));
            const bool onboard = onboard_box(box, bounds);
            const ClearLabel hit{cand[0], cand[1], box, extra};
            if (onboard) {
                if (pen == 0.0) {
                    return hit;
                }
                if (!have_best || pen < best_pen) {
                    best_pen = pen;
                    best = hit;
                    have_best = true;
                }
            }
            if (!have_any || pen < best_any_pen) {
                best_any_pen = pen;
                best_any = hit;
                have_any = true;
            }
        }
    }
    static const double kOrbit[] = {2.2, 4.4, 6.6, 9.0, 12.0, 15.0, 18.0, 21.0,
                                    24.0, 28.0, 32.0};
    static const double kTau = 6.283185307179586;
    for (double extra : kOrbit) {
        const double rx = (cx1 - cx0) / 2.0 + g + extra + w / 2.0;
        const double ry = (cy1 - cy0) / 2.0 + g + extra + h / 2.0;
        for (int k = 0; k < 16; ++k) {
            const double a = kTau * static_cast<double>(k) / 16.0;
            const double tx = midx + rx * std::cos(a);
            const double ty = midy + ry * std::sin(a);
            const Box4 box = text_box(label, tx, ty, size, 0.15);
            if (!onboard_box(box, bounds)) {
                continue;
            }
            const Box4 gb{box.x0 - 0.02, box.y0 - 0.02, box.x1 + 0.02,
                          box.y1 + 0.02};
            const double pen = occupied.pen(gb)
                + (placed == nullptr ? 0.0 : placed->pen(gb));
            const ClearLabel hit{tx, ty, box, extra};
            if (pen == 0.0) {
                return hit;
            }
            if (!have_best || pen < best_pen) {
                best_pen = pen;
                best = hit;
                have_best = true;
            }
        }
    }
    return have_best ? best : best_any;
}

bool segments_cross(double ax0, double ay0, double ax1, double ay1,
                    double bx0, double by0, double bx1, double by1) {
    const double eps = 1e-9;
    if ((ax0 == bx0 && ay0 == by0) || (ax0 == bx1 && ay0 == by1)
        || (ax1 == bx0 && ay1 == by0) || (ax1 == bx1 && ay1 == by1)) {
        return false;
    }
    const auto cross = [](double ox, double oy, double ax, double ay,
                          double bx, double by) {
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox);
    };
    const double d1 = cross(bx0, by0, bx1, by1, ax0, ay0);
    const double d2 = cross(bx0, by0, bx1, by1, ax1, ay1);
    const double d3 = cross(ax0, ay0, ax1, ay1, bx0, by0);
    const double d4 = cross(ax0, ay0, ax1, ay1, bx1, by1);
    return (((d1 > eps && d2 < -eps) || (d1 < -eps && d2 > eps))
            && ((d3 > eps && d4 < -eps) || (d3 < -eps && d4 > eps)));
}

}  // namespace schgen
