#include "schgen/pack.hpp"

#include "schgen/quantize.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>

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

namespace {

int pos_mod(int value, int modulus) {
    int rem = value % modulus;
    if (rem < 0) {
        rem += modulus;
    }
    return rem;
}

std::string markup_visible(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (std::size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '~' && i + 1 < text.size() && text[i + 1] == '{') {
            const std::size_t end = text.find('}', i + 2);
            if (end != std::string::npos) {
                out.append(text, i + 2, end - (i + 2));
                i = end;
                continue;
            }
        }
        out.push_back(text[i]);
    }
    return out;
}

}  // namespace

std::optional<Box4> boxes_union(const std::vector<Box4>& boxes) {
    if (boxes.empty()) {
        return std::nullopt;
    }
    Box4 acc = boxes[0];
    for (std::size_t i = 1; i < boxes.size(); ++i) {
        acc.x0 = std::min(acc.x0, boxes[i].x0);
        acc.y0 = std::min(acc.y0, boxes[i].y0);
        acc.x1 = std::max(acc.x1, boxes[i].x1);
        acc.y1 = std::max(acc.y1, boxes[i].y1);
    }
    return acc;
}

std::pair<double, double> text_wh(const std::string& text, double size,
                                  double char_w, double line_h) {
    const std::string visible = markup_visible(text);
    const double n = static_cast<double>(std::max<std::size_t>(visible.size(), 1));
    return {n * char_w * size, line_h * size};
}

Box4 centered_box(const std::string& text, double cx, double cy, double size,
                  double char_w, double line_h, bool vertical) {
    auto wh = text_wh(text, size, char_w, line_h);
    double w = wh.first;
    double h = wh.second;
    if (vertical) {
        std::swap(w, h);
    }
    return Box4{cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0};
}

Box4 llabel_box(const std::string& text, double x, double y, int rotation,
                double size, double char_w, double line_h, double width_pad,
                double gap) {
    auto wh = text_wh(text, size, char_w, line_h);
    const double w = wh.first + width_pad;
    const double h = wh.second;
    const int r = pos_mod(rotation, 360);
    if (r == 0) {
        return Box4{x, y - gap - h, x + w, y - gap};
    }
    if (r == 180) {
        return Box4{x - w, y - gap - h, x, y - gap};
    }
    throw std::runtime_error("llabel_box: unsupported local-label rotation");
}

Box4 glabel_box(const std::string& text, double x, double y, int rotation,
                double size, double char_w, double line_h, double pad_len,
                double glabel_h, double inset) {
    auto wh = text_wh(text, size, char_w, line_h);
    const double length = wh.first + pad_len * size;
    const double half_h = glabel_h * size / 2.0;
    const int r = pos_mod(rotation, 360);
    if (r == 0) {
        return Box4{x + inset, y - half_h, x + length, y + half_h};
    }
    if (r == 180) {
        return Box4{x - length, y - half_h, x - inset, y + half_h};
    }
    if (r == 90) {
        return Box4{x - half_h, y - length, x + half_h, y - inset};
    }
    if (r == 270) {
        return Box4{x - half_h, y + inset, x + half_h, y + length};
    }
    throw std::runtime_error("glabel_box: unsupported label rotation");
}

std::optional<Box4> silk_gfx_extent(
    const std::vector<std::pair<double, double>>& pts, double fx, double fy,
    double ca, double sa, double hw) {
    if (pts.empty()) {
        return std::nullopt;
    }
    double min_x = 0.0;
    double min_y = 0.0;
    double max_x = 0.0;
    double max_y = 0.0;
    bool any = false;
    for (const auto& p : pts) {
        const double bx = fx + p.first * ca + p.second * sa;
        const double by = fy - p.first * sa + p.second * ca;
        if (!any) {
            min_x = max_x = bx;
            min_y = max_y = by;
            any = true;
        } else {
            min_x = std::min(min_x, bx);
            min_y = std::min(min_y, by);
            max_x = std::max(max_x, bx);
            max_y = std::max(max_y, by);
        }
    }
    return Box4{min_x - hw, min_y - hw, max_x + hw, max_y + hw};
}

double pair_gap(const Halo& a_reach, const Halo& a_inset, const Halo& b_reach,
                const Halo& b_inset, char axis, double floor) {
    return py_round(std::max(floor, fanout_sep(a_reach, a_inset, b_reach,
                                               b_inset, axis)),
                    4);
}

std::vector<Comp> edge_components(char edge, double block_x, double block_y,
                                  double board_w, double board_h,
                                  int punch_mask,
                                  const std::vector<Comp>& comps) {
    std::vector<Comp> out;
    out.reserve(comps.size());
    for (Comp c : comps) {
        if (c.mask == punch_mask) {
            if (edge == 'N') {
                c.h = block_y + c.dy + c.h;
                c.dy = -block_y;
            } else if (edge == 'S') {
                c.h = board_h - block_y - c.dy;
            } else if (edge == 'W') {
                c.w = block_x + c.dx + c.w;
                c.dx = -block_x;
            } else if (edge == 'E') {
                c.w = board_w - block_x - c.dx;
            }
        }
        out.push_back(Comp{py_round(c.dx, 4), py_round(c.dy, 4),
                           py_round(c.w, 4), py_round(c.h, 4), c.mask});
    }
    return out;
}

std::tuple<double, double, int, int> som_decoupling_grid(double som_w,
                                                         double som_h, int n,
                                                         double inset) {
    const double rw = std::max(1.0, som_w - 2.0 * inset);
    const double rh = std::max(1.0, som_h - 2.0 * inset);
    int cols = 1;
    int rows = 1;
    if (n != 0) {
        const double raw =
            py_round(std::sqrt(static_cast<double>(n) * rw / rh), 0);
        cols = std::max(1, static_cast<int>(
                               std::min(static_cast<double>(n), raw)));
        rows = std::max(1, (n + cols - 1) / cols);
    }
    return {rw, rh, cols, rows};
}

std::vector<std::pair<double, double>> som_decoupling_cells(
    double som_x, double som_y, double som_w, double som_h, int n,
    double inset) {
    if (n <= 0) {
        return {};
    }
    const double rx0 = som_x + inset;
    const double ry0 = som_y + inset;
    const auto grid = som_decoupling_grid(som_w, som_h, n, inset);
    const double rw = std::get<0>(grid);
    const double rh = std::get<1>(grid);
    const int cols = std::get<2>(grid);
    const int rows = std::get<3>(grid);
    std::vector<std::pair<double, double>> out;
    out.reserve(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) {
        out.emplace_back(
            py_round(rx0 + rw * (static_cast<double>(i % cols) + 0.5)
                         / static_cast<double>(cols),
                     4),
            py_round(ry0 + rh * (static_cast<double>(i / cols) + 0.5)
                         / static_cast<double>(rows),
                     4));
    }
    return out;
}

std::vector<Comp> som_components(
    double origin_x, double origin_y, double radius,
    const std::vector<std::pair<double, double>>& cells,
    const std::vector<Box4>& bands, int bottom_mask, int punch_mask) {
    std::vector<Comp> out;
    out.reserve(cells.size() + bands.size());
    const double diam = py_round(2.0 * radius, 4);
    for (const auto& cell : cells) {
        out.push_back(Comp{py_round(cell.first - radius - origin_x, 4),
                           py_round(cell.second - radius - origin_y, 4), diam,
                           diam, bottom_mask});
    }
    for (const Box4& band : bands) {
        out.push_back(Comp{py_round(band.x0 - origin_x, 4),
                           py_round(band.y0 - origin_y, 4),
                           py_round(band.x1 - band.x0, 4),
                           py_round(band.y1 - band.y0, 4), punch_mask});
    }
    return out;
}

bool any_boxes_overlap(const std::vector<Box4>& boxes, double halo) {
    for (std::size_t i = 0; i < boxes.size(); ++i) {
        for (std::size_t j = i + 1; j < boxes.size(); ++j) {
            if (boxes_overlap(boxes[i], boxes[j], halo)) {
                return true;
            }
        }
    }
    return false;
}

std::vector<int> pack_interior_order(const std::vector<std::string>& names,
                                     const std::vector<int>& tiers,
                                     const std::vector<double>& conn,
                                     const std::vector<double>& area) {
    if (names.size() != tiers.size() || names.size() != conn.size()
        || names.size() != area.size()) {
        throw std::runtime_error(
            "pack_interior_order: names/tiers/conn/area required same length");
    }
    std::vector<int> order(static_cast<int>(names.size()));
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int left, int right) {
        const std::size_t i = static_cast<std::size_t>(left);
        const std::size_t j = static_cast<std::size_t>(right);
        if (tiers[i] != tiers[j]) {
            return tiers[i] < tiers[j];
        }
        if (conn[i] != conn[j]) {
            return conn[i] > conn[j];
        }
        if (area[i] != area[j]) {
            return area[i] > area[j];
        }
        return names[i] < names[j];
    });
    return order;
}

double pack_conn_weight(const std::vector<double>& aff_weights,
                        double som_pull) {
    double total = 0.0;
    for (double weight : aff_weights) {
        total += weight;
    }
    return total + 3.0 * som_pull;
}

std::vector<std::pair<std::string, std::vector<std::string>>> nets_by_sheet(
    const std::vector<std::pair<std::string, std::vector<std::string>>>&
        net_sheets) {
    std::vector<std::pair<std::string, std::vector<std::string>>> ordered =
        net_sheets;
    std::sort(ordered.begin(), ordered.end(),
              [](const auto& left, const auto& right) {
                  return left.first < right.first;
              });
    std::vector<std::pair<std::string, std::vector<std::string>>> out;
    std::unordered_map<std::string, std::size_t> index;
    for (auto& row : ordered) {
        std::vector<std::string> sheets = row.second;
        std::sort(sheets.begin(), sheets.end());
        sheets.erase(std::unique(sheets.begin(), sheets.end()), sheets.end());
        for (const auto& sheet : sheets) {
            const auto found = index.find(sheet);
            if (found == index.end()) {
                index.emplace(sheet, out.size());
                out.emplace_back(sheet, std::vector<std::string>{row.first});
            } else {
                out[found->second].second.push_back(row.first);
            }
        }
    }
    return out;
}

int obstacle_bucket(double region_u0, double region_v0, double region_u1,
                    double region_v1, double box_u0, double box_v0,
                    double box_u1, double box_v1, bool same_ref, bool net_gnd,
                    bool side_top) {
    if (box_u1 < region_u0 || box_u0 > region_u1 || box_v1 < region_v0
        || box_v0 > region_v1) {
        return 0;
    }
    if (same_ref && net_gnd) {
        return 1;
    }
    if (side_top || same_ref) {
        return 2;
    }
    return 3;
}

std::tuple<double, double, double> obstacle_hole(double box_u0, double box_v0,
                                                 double box_u1, double box_v1) {
    return {(box_u0 + box_u1) / 2.0, (box_v0 + box_v1) / 2.0,
            std::max(box_u1 - box_u0, box_v1 - box_v0) / 2.0};
}

double net_clearance_rule(bool power) {
    return power ? 0.2 : 0.15;
}

std::vector<std::pair<double, double>> cout_column_centers(
    const Box4& inductor_out, double pad, double cout_gap,
    double template_clear, const std::vector<std::pair<double, double>>& halves) {
    std::vector<std::pair<double, double>> out;
    if (halves.empty()) {
        return out;
    }
    double hx = halves[0].first;
    for (const auto& half : halves) {
        hx = std::max(hx, half.first);
    }
    const double col_x = py_round(inductor_out.x1 + cout_gap + pad + hx, 4);
    const double pad_cy = (inductor_out.y0 + inductor_out.y1) / 2.0;
    const double step = template_clear + pad;
    double total = 0.0;
    for (const auto& half : halves) {
        total += 2.0 * half.second;
    }
    total += step * static_cast<double>(halves.size() - 1);
    double y = pad_cy - total / 2.0;
    out.reserve(halves.size());
    for (const auto& half : halves) {
        const double cy = y + half.second;
        out.emplace_back(col_x, py_round(cy, 4));
        y += 2.0 * half.second + step;
    }
    return out;
}

std::pair<double, double> bulk_cap_pose(
    double hf_ox, const Box4& hf_box, const std::string& direction, double gap,
    double hx, double hy, double inductor_left, double template_clear) {
    const double cy = direction == "D" ? (hf_box.y1 + gap + hy)
                                       : (hf_box.y0 - gap - hy);
    const double ox = std::min(hf_ox, inductor_left - template_clear - hx);
    return {py_round(ox, 4), py_round(cy, 4)};
}

RefdesMove place_refdes(
    const Box4& court, const std::string& ref, double size, const Box4& box,
    const SilkBoxIndex& occupied, const SilkBoxIndex& placed,
    const Box4& bounds, double fx, double fy, double ca, double sa,
    double min_size, double box_pad, double far_off, double pen_eps,
    double off_improve, const std::vector<double>& shrinks) {
    const Box4 padded{box.x0 - box_pad, box.y0 - box_pad, box.x1 + box_pad,
                      box.y1 + box_pad};
    if (!occupied.hits(padded) && !placed.hits(padded)) {
        return RefdesMove{false, 0.0, 0.0, size, box};
    }
    const std::optional<Box4> bound_opt{bounds};
    ClearLabel hit = place_clear_label(court.x0, court.y0, court.x1, court.y1,
                                       ref, size, occupied, &placed,
                                       bound_opt);
    double tx = hit.x;
    double ty = hit.y;
    Box4 nbox = hit.box;
    double off = hit.extra;
    double new_size = size;
    double cur_pen = occupied.pen(nbox) + placed.pen(nbox);
    if (off > far_off || cur_pen > 0.0) {
        std::set<double> tried;
        tried.insert(py_round(size, 3));
        for (double shrink : shrinks) {
            const double s2 = std::max(py_round(size * shrink, 3), min_size);
            if (tried.count(s2) != 0 || s2 >= size) {
                continue;
            }
            tried.insert(s2);
            ClearLabel alt = place_clear_label(
                court.x0, court.y0, court.x1, court.y1, ref, s2, occupied,
                &placed, bound_opt);
            const double pen2 = occupied.pen(alt.box) + placed.pen(alt.box);
            if ((pen2 < cur_pen - pen_eps)
                || (cur_pen <= 0.0 && alt.extra < off - off_improve)) {
                tx = alt.x;
                ty = alt.y;
                nbox = alt.box;
                off = alt.extra;
                new_size = s2;
                cur_pen = pen2;
                if (cur_pen <= 0.0 && off <= far_off) {
                    break;
                }
            }
        }
    }
    const double dx = tx - fx;
    const double dy = ty - fy;
    return RefdesMove{true, py_round(dx * ca - dy * sa, 4),
                      py_round(dx * sa + dy * ca, 4), new_size, nbox};
}

std::vector<Box4> som_keepout_rects(
    double som_x, double som_y, double som_w, double som_h, double occ_pad,
    const std::vector<std::tuple<double, double, double, double>>& connectors,
    double seat_band) {
    std::vector<Box4> out;
    out.push_back(Box4{som_x - occ_pad, som_y - occ_pad,
                       som_x + som_w + occ_pad, som_y + som_h + occ_pad});
    for (const auto& row : connectors) {
        const double jx = std::get<0>(row);
        const double jy = std::get<1>(row);
        const double jw = std::get<2>(row);
        const double jh = std::get<3>(row);
        out.push_back(Box4{som_x + jx - jw / 2.0 - seat_band,
                           som_y + jy - jh / 2.0 - seat_band,
                           som_x + jx + jw / 2.0 + seat_band,
                           som_y + jy + jh / 2.0 + seat_band});
    }
    return out;
}

std::vector<Comp> zone_components_assemble(
    const std::vector<Box4>& minor_boxes, const std::vector<Box4>& punch_boxes,
    int minor_mask, int punch_mask) {
    std::vector<Comp> out;
    if (!minor_boxes.empty()) {
        double x0 = minor_boxes[0].x0;
        double y0 = minor_boxes[0].y0;
        double x1 = minor_boxes[0].x1;
        double y1 = minor_boxes[0].y1;
        for (const auto& box : minor_boxes) {
            x0 = std::min(x0, box.x0);
            y0 = std::min(y0, box.y0);
            x1 = std::max(x1, box.x1);
            y1 = std::max(y1, box.y1);
        }
        out.push_back(Comp{py_round(x0, 4), py_round(y0, 4),
                           py_round(x1 - x0, 4), py_round(y1 - y0, 4),
                           minor_mask});
    }
    for (const auto& box : punch_boxes) {
        out.push_back(Comp{py_round(box.x0, 4), py_round(box.y0, 4),
                           py_round(box.x1 - box.x0, 4),
                           py_round(box.y1 - box.y0, 4), punch_mask});
    }
    return out;
}

namespace {

bool parse_plain_number(const std::string& text, std::size_t start,
                        std::size_t* end, double* value) {
    if (start >= text.size()
        || !std::isdigit(static_cast<unsigned char>(text[start]))) {
        return false;
    }
    std::size_t i = start + 1;
    while (i < text.size()
           && std::isdigit(static_cast<unsigned char>(text[i]))) {
        ++i;
    }
    if (i < text.size() && text[i] == '.' && i + 1 < text.size()
        && std::isdigit(static_cast<unsigned char>(text[i + 1]))) {
        i += 2;
        while (i < text.size()
               && std::isdigit(static_cast<unsigned char>(text[i]))) {
            ++i;
        }
    }
    *end = i;
    *value = std::stod(text.substr(start, i - start));
    return true;
}

}  // namespace

std::pair<double, double> part_dims_from_name(
    const std::string& name,
    const std::vector<std::tuple<std::string, double, double>>& fixed_dims,
    double default_w, double default_h) {
    for (const auto& row : fixed_dims) {
        if (name.find(std::get<0>(row)) != std::string::npos) {
            return {std::get<1>(row), std::get<2>(row)};
        }
    }
    for (std::size_t i = 0; i + 3 < name.size(); ++i) {
        if (name[i] != '_') {
            continue;
        }
        std::size_t after_w = 0;
        double width = 0.0;
        if (!parse_plain_number(name, i + 1, &after_w, &width)) {
            continue;
        }
        if (after_w >= name.size() || name[after_w] != 'x') {
            continue;
        }
        std::size_t after_h = 0;
        double height = 0.0;
        if (!parse_plain_number(name, after_w + 1, &after_h, &height)) {
            continue;
        }
        if (after_h + 1 < name.size() && name.compare(after_h, 2, "mm") == 0) {
            return {width, height};
        }
    }
    for (std::size_t i = 0; i + 11 <= name.size(); ++i) {
        if (name[i] != '_') {
            continue;
        }
        bool digits = true;
        for (std::size_t k = 1; k <= 4; ++k) {
            if (!std::isdigit(static_cast<unsigned char>(name[i + k]))) {
                digits = false;
                break;
            }
        }
        if (!digits || name.compare(i + 5, 6, "Metric") != 0) {
            continue;
        }
        const int a = (name[i + 1] - '0') * 10 + (name[i + 2] - '0');
        const int b = (name[i + 3] - '0') * 10 + (name[i + 4] - '0');
        return {static_cast<double>(a) / 10.0, static_cast<double>(b) / 10.0};
    }
    return {default_w, default_h};
}

std::string ref_prefix(const std::string& ref) {
    std::size_t i = 0;
    while (i < ref.size()) {
        const unsigned char ch = static_cast<unsigned char>(ref[i]);
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z'))) {
            break;
        }
        ++i;
    }
    if (i == 0) {
        return ref;
    }
    return ref.substr(0, i);
}

bool is_testpoint_ref(const std::string& ref) {
    return ref_prefix(ref) == "TP";
}

bool is_cluster_passive(
    const std::string& ref, int pins,
    const std::vector<std::string>& not_plain,
    const std::vector<std::string>& prefixes) {
    if (pins > 2) {
        return false;
    }
    for (const auto& token : not_plain) {
        if (ref.size() >= token.size()
            && ref.compare(0, token.size(), token) == 0) {
            return false;
        }
    }
    const std::string prefix = ref_prefix(ref);
    for (const auto& token : prefixes) {
        if (prefix == token) {
            return true;
        }
    }
    return false;
}

std::pair<double, std::string> intelligent_need(
    int pins,
    const std::vector<std::tuple<int, double, std::string>>& tiers,
    double top_need, const std::string& top_basis) {
    for (const auto& row : tiers) {
        if (pins <= std::get<0>(row)) {
            return {std::get<1>(row), std::get<2>(row)};
        }
    }
    return {top_need, top_basis};
}

namespace {

double intelligent_need_mm(
    int pins, const std::vector<std::tuple<int, double>>& need_tiers,
    double top_need) {
    for (const auto& row : need_tiers) {
        if (pins <= std::get<0>(row)) {
            return std::get<1>(row);
        }
    }
    return top_need;
}

}  // namespace

std::vector<std::tuple<double, double, double, double, int, double>>
zone_fanout_members_rows(
    const std::vector<std::tuple<double, double, double, double, double, double,
                                 double, int>>& rows,
    int min_subject_pins,
    const std::vector<std::tuple<int, double>>& need_tiers, double top_need) {
    std::vector<std::tuple<double, double, double, double, int, double>> out;
    out.reserve(rows.size());
    for (const auto& row : rows) {
        const double ox = std::get<0>(row);
        const double oy = std::get<1>(row);
        const Box4 rb = turn_box(Box4{std::get<2>(row), std::get<3>(row),
                                      std::get<4>(row), std::get<5>(row)},
                                 std::get<6>(row));
        const int pins = std::get<7>(row);
        const double lim = pins >= min_subject_pins
            ? quant_credit(intelligent_need_mm(pins, need_tiers, top_need))
            : 0.0;
        out.emplace_back(ox + rb.x0, oy + rb.y0, ox + rb.x1, oy + rb.y1, pins,
                         lim);
    }
    return out;
}

namespace {

int fan_cross_count(const std::vector<std::vector<std::vector<Seg2>>>& segs,
                    const std::vector<int>& assign) {
    std::vector<Seg2> flat;
    for (std::size_t i = 0; i < assign.size(); ++i) {
        const int slot = assign[i];
        if (slot < 0
            || static_cast<std::size_t>(slot) >= segs[i].size()) {
            throw std::runtime_error("reorder_cluster_assign: slot");
        }
        const auto& row = segs[i][static_cast<std::size_t>(slot)];
        flat.insert(flat.end(), row.begin(), row.end());
    }
    int n = 0;
    for (std::size_t a = 0; a < flat.size(); ++a) {
        for (std::size_t b = a + 1; b < flat.size(); ++b) {
            if (segments_cross(flat[a].x0, flat[a].y0, flat[a].x1, flat[a].y1,
                               flat[b].x0, flat[b].y0, flat[b].x1,
                               flat[b].y1)) {
                ++n;
            }
        }
    }
    return n;
}

}  // namespace

ReorderAssign reorder_cluster_assign(
    const std::vector<std::vector<std::vector<Seg2>>>& segs,
    const std::vector<int>& assign0, int sweeps) {
    if (sweeps < 0) {
        throw std::runtime_error("reorder_cluster_assign: sweeps required");
    }
    if (segs.size() != assign0.size()) {
        throw std::runtime_error("reorder_cluster_assign: assign size");
    }
    std::vector<int> assign = assign0;
    const int before = fan_cross_count(segs, assign);
    ReorderAssign out;
    out.before = before;
    out.best = before;
    out.assign = assign;
    if (before == 0) {
        return out;
    }
    for (int sweep = 0; sweep < sweeps; ++sweep) {
        bool improved = false;
        for (std::size_t a = 0; a < assign.size(); ++a) {
            for (std::size_t b = a + 1; b < assign.size(); ++b) {
                std::swap(assign[a], assign[b]);
                const int trial = fan_cross_count(segs, assign);
                if (trial < out.best) {
                    out.best = trial;
                    improved = true;
                } else {
                    std::swap(assign[a], assign[b]);
                }
            }
        }
        if (!improved) {
            break;
        }
    }
    out.assign = assign;
    return out;
}

bool visual_hv_cross(double ax0, double ay0, double ax1, double ay1,
                     double bx0, double by0, double bx1, double by1) {
    const double eps = 1e-6;
    const bool a_h = std::fabs(ay0 - ay1) < eps;
    const bool a_v = std::fabs(ax0 - ax1) < eps;
    const bool b_h = std::fabs(by0 - by1) < eps;
    const bool b_v = std::fabs(bx0 - bx1) < eps;
    double hx0 = 0.0;
    double hx1 = 0.0;
    double hy = 0.0;
    double vx = 0.0;
    double vy0 = 0.0;
    double vy1 = 0.0;
    if (a_h && b_v) {
        hx0 = ax0;
        hx1 = ax1;
        hy = ay0;
        vx = bx0;
        vy0 = by0;
        vy1 = by1;
    } else if (a_v && b_h) {
        hx0 = bx0;
        hx1 = bx1;
        hy = by0;
        vx = ax0;
        vy0 = ay0;
        vy1 = ay1;
    } else {
        return false;
    }
    if (hx0 > hx1) {
        std::swap(hx0, hx1);
    }
    if (vy0 > vy1) {
        std::swap(vy0, vy1);
    }
    return (hx0 + eps < vx && vx < hx1 - eps)
        && (vy0 + eps < hy && hy < vy1 - eps);
}

bool collinear_overlap(double ax0, double ay0, double ax1, double ay1,
                       double bx0, double by0, double bx1, double by1) {
    const double eps = 1e-6;
    const bool a_h = std::fabs(ay0 - ay1) < eps;
    const bool b_h = std::fabs(by0 - by1) < eps;
    const bool a_v = std::fabs(ax0 - ax1) < eps;
    const bool b_v = std::fabs(bx0 - bx1) < eps;
    if (a_h && b_h && std::fabs(ay0 - by0) < eps) {
        double a0 = ax0;
        double a1 = ax1;
        double b0 = bx0;
        double b1 = bx1;
        if (a0 > a1) {
            std::swap(a0, a1);
        }
        if (b0 > b1) {
            std::swap(b0, b1);
        }
        return std::min(a1, b1) - std::max(a0, b0) > eps;
    }
    if (a_v && b_v && std::fabs(ax0 - bx0) < eps) {
        double a0 = ay0;
        double a1 = ay1;
        double b0 = by0;
        double b1 = by1;
        if (a0 > a1) {
            std::swap(a0, a1);
        }
        if (b0 > b1) {
            std::swap(b0, b1);
        }
        return std::min(a1, b1) - std::max(a0, b0) > eps;
    }
    return false;
}

Box4 som_core_rect(double som_x, double som_y, double som_w, double som_h,
                   double origin_x, double origin_y, double clearance) {
    const double ccx = som_w * clearance / 2.0;
    const double ccy = som_h * clearance / 2.0;
    return Box4{origin_x + som_x - ccx, origin_y + som_y - ccy,
                origin_x + som_x + som_w + ccx,
                origin_y + som_y + som_h + ccy};
}

std::vector<std::tuple<std::string, double, double>> rotate_offsets_90(
    const std::vector<std::tuple<std::string, double, double>>& offs,
    double zone_w) {
    std::vector<std::tuple<std::string, double, double>> out;
    out.reserve(offs.size());
    for (const auto& row : offs) {
        out.emplace_back(std::get<0>(row), py_round(std::get<2>(row), 4),
                         py_round(zone_w - std::get<1>(row), 4));
    }
    return out;
}

std::vector<std::tuple<std::string, std::vector<std::string>>>
cluster_interchangeable_rows(
    const std::vector<std::tuple<std::string, double, double>>& members,
    double tol_x, double tol_y) {
    std::vector<std::tuple<std::string, double, double>> by_y = members;
    std::stable_sort(by_y.begin(), by_y.end(),
                     [](const auto& a, const auto& b) {
                         if (std::get<2>(a) != std::get<2>(b)) {
                             return std::get<2>(a) < std::get<2>(b);
                         }
                         if (std::get<1>(a) != std::get<1>(b)) {
                             return std::get<1>(a) < std::get<1>(b);
                         }
                         return std::get<0>(a) < std::get<0>(b);
                     });
    std::vector<std::tuple<std::string, std::vector<std::string>>> clusters;
    std::vector<std::tuple<std::string, double, double>> rest;
    std::vector<std::tuple<std::string, double, double>> row;
    for (const auto& m : by_y) {
        if (!row.empty()
            && std::fabs(std::get<2>(m) - std::get<2>(row[0])) > tol_y) {
            if (row.size() > 1) {
                std::vector<std::string> refs;
                refs.reserve(row.size());
                for (const auto& r : row) {
                    refs.push_back(std::get<0>(r));
                }
                clusters.emplace_back("x", std::move(refs));
            } else {
                rest.insert(rest.end(), row.begin(), row.end());
            }
            row.clear();
        }
        row.push_back(m);
    }
    if (row.size() > 1) {
        std::vector<std::string> refs;
        refs.reserve(row.size());
        for (const auto& r : row) {
            refs.push_back(std::get<0>(r));
        }
        clusters.emplace_back("x", std::move(refs));
    } else if (!row.empty()) {
        rest.insert(rest.end(), row.begin(), row.end());
    }
    std::stable_sort(rest.begin(), rest.end(),
                     [](const auto& a, const auto& b) {
                         if (std::get<1>(a) != std::get<1>(b)) {
                             return std::get<1>(a) < std::get<1>(b);
                         }
                         if (std::get<2>(a) != std::get<2>(b)) {
                             return std::get<2>(a) < std::get<2>(b);
                         }
                         return std::get<0>(a) < std::get<0>(b);
                     });
    std::vector<std::tuple<std::string, double, double>> col;
    for (const auto& m : rest) {
        if (!col.empty()
            && std::fabs(std::get<1>(m) - std::get<1>(col[0])) > tol_x) {
            if (col.size() > 1) {
                std::vector<std::string> refs;
                refs.reserve(col.size());
                for (const auto& r : col) {
                    refs.push_back(std::get<0>(r));
                }
                clusters.emplace_back("y", std::move(refs));
            }
            col.clear();
        }
        col.push_back(m);
    }
    if (col.size() > 1) {
        std::vector<std::string> refs;
        refs.reserve(col.size());
        for (const auto& r : col) {
            refs.push_back(std::get<0>(r));
        }
        clusters.emplace_back("y", std::move(refs));
    }
    return clusters;
}

std::pair<double, double> nearest_manhattan(
    double px, double py, const std::vector<std::pair<double, double>>& pts) {
    if (pts.empty()) {
        throw std::runtime_error("nearest_manhattan: pts required");
    }
    std::size_t best = 0;
    double best_d = std::fabs(pts[0].first - px) + std::fabs(pts[0].second - py);
    for (std::size_t i = 1; i < pts.size(); ++i) {
        const double d =
            std::fabs(pts[i].first - px) + std::fabs(pts[i].second - py);
        if (d < best_d
            || (d == best_d
                && (pts[i].first < pts[best].first
                    || (pts[i].first == pts[best].first
                        && pts[i].second < pts[best].second)))) {
            best = i;
            best_d = d;
        }
    }
    return pts[best];
}

double overlap_1d(double a0, double a1, double b0, double b1) {
    return std::max(0.0, std::min(a1, b1) - std::max(a0, b0));
}

std::optional<std::pair<std::string, double>> same_edge_gap(
    const Box4& a, const Box4& b, double band_frac) {
    const double ox = overlap_1d(a.x0, a.x1, b.x0, b.x1);
    const double oy = overlap_1d(a.y0, a.y1, b.y0, b.y1);
    const double wx = std::min(a.x1 - a.x0, b.x1 - b.x0);
    const double hy = std::min(a.y1 - a.y0, b.y1 - b.y0);
    const bool same_x = wx > 0.0 && ox >= band_frac * wx;
    const bool same_y = hy > 0.0 && oy >= band_frac * hy;
    if (same_y && !same_x) {
        return std::make_pair(
            std::string{"x"},
            std::max(a.x0, b.x0) - std::min(a.x1, b.x1));
    }
    if (same_x && !same_y) {
        return std::make_pair(
            std::string{"y"},
            std::max(a.y0, b.y0) - std::min(a.y1, b.y1));
    }
    return std::nullopt;
}

std::optional<std::pair<double, double>> foreign_t_touch(
    double ax0, double ay0, double ax1, double ay1, double bx0, double by0,
    double bx1, double by1, bool same_net) {
    if (same_net) {
        return std::nullopt;
    }
    const double ends[4][2] = {{ax0, ay0}, {ax1, ay1}, {bx0, by0}, {bx1, by1}};
    const bool other_is_b[4] = {true, true, false, false};
    for (int i = 0; i < 4; ++i) {
        const double ox0 = other_is_b[i] ? bx0 : ax0;
        const double oy0 = other_is_b[i] ? by0 : ay0;
        const double ox1 = other_is_b[i] ? bx1 : ax1;
        const double oy1 = other_is_b[i] ? by1 : ay1;
        if (point_on_seg(ends[i][0], ends[i][1], ox0, oy0, ox1, oy1, false)) {
            return std::make_pair(ends[i][0], ends[i][1]);
        }
    }
    return std::nullopt;
}

std::tuple<double, double, double, double, double, double> refdes_hit_court(
    double fx, double fy, double ca, double sa, double lx, double ly,
    const std::optional<Box4>& court) {
    const double bx = fx + lx * ca + ly * sa;
    const double by = fy - lx * sa + ly * ca;
    if (court.has_value()) {
        return {bx, by, court->x0, court->y0, court->x1, court->y1};
    }
    return {bx, by, bx - 1.0, by - 1.0, bx + 1.0, by + 1.0};
}

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

std::pair<double, double> uv_to_board(double cx, double cy, double u, double v,
                                      double rot) {
    const double turn = rot * (M_PI / 180.0);
    const double cs = std::cos(turn);
    const double sn = std::sin(turn);
    return {cx + u * cs + v * sn, cy - u * sn + v * cs};
}

std::pair<double, double> board_to_uv(double cx, double cy, double bx,
                                      double by, double rot) {
    const double turn = rot * (M_PI / 180.0);
    const double cs = std::cos(turn);
    const double sn = std::sin(turn);
    const double qx = bx - cx;
    const double qy = by - cy;
    return {qx * cs - qy * sn, qx * sn + qy * cs};
}

Box4 corridor_local_from_uv(
    const std::vector<std::pair<double, double>>& pads, double r_construct,
    double v_margin) {
    if (pads.empty()) {
        throw std::runtime_error("corridor_local_from_uv: pads required");
    }
    double u0 = pads[0].first;
    double u1 = pads[0].first;
    double v0 = pads[0].second;
    double v1 = pads[0].second;
    for (const auto& p : pads) {
        u0 = std::min(u0, p.first);
        u1 = std::max(u1, p.first);
        v0 = std::min(v0, p.second);
        v1 = std::max(v1, p.second);
    }
    const double u_half = std::max(std::fabs(u0), std::fabs(u1)) + r_construct;
    const double v_half = std::max(std::fabs(v0), std::fabs(v1)) + v_margin;
    return Box4{-u_half, -v_half, u_half, v_half};
}

Box4 corridor_board_rect(const Box4& local, double cx, double cy, double rot) {
    const double us[2] = {local.x0, local.x1};
    const double vs[2] = {local.y0, local.y1};
    bool any = false;
    double min_x = 0.0;
    double min_y = 0.0;
    double max_x = 0.0;
    double max_y = 0.0;
    for (double u : us) {
        for (double v : vs) {
            const auto p = uv_to_board(cx, cy, u, v, rot);
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
    return Box4{py_round(min_x, 4), py_round(min_y, 4), py_round(max_x, 4),
                py_round(max_y, 4)};
}

std::pair<double, double> mirror_offset_x(double ox, double oy, const Box4& cb,
                                          double zone_w) {
    return {py_round(zone_w - ox - cb.x0 - cb.x1, 4), oy};
}

Box4 offset_turned_box(const Box4& bbox, double rot, double ox, double oy) {
    const Box4 turned = turn_box(bbox, rot);
    return Box4{ox + turned.x0, oy + turned.y0, ox + turned.x1,
                oy + turned.y1};
}

std::vector<Box4> offset_boxes(const std::vector<Box4>& boxes, double ox,
                               double oy) {
    std::vector<Box4> out;
    out.reserve(boxes.size());
    for (const auto& box : boxes) {
        out.push_back(Box4{ox + box.x0, oy + box.y0, ox + box.x1,
                           oy + box.y1});
    }
    return out;
}

GridControls grid_controls(
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        items,
    double target_w, double button_gap, double zone_pad, double place_clear) {
    if (items.empty()) {
        throw std::runtime_error("grid_controls: refs required");
    }
    double cell = 0.0;
    for (const auto& row : items) {
        const double bw = std::get<3>(row) - std::get<1>(row);
        const double bh = std::get<4>(row) - std::get<2>(row);
        cell = std::max(cell, std::max(bw + button_gap, bh + button_gap));
    }
    if (cell == 0.0) {
        throw std::runtime_error("grid_controls: cell required");
    }
    const int n = static_cast<int>(items.size());
    const int fit = static_cast<int>(target_w / cell);
    const int cols = std::max(1, std::min(n, fit == 0 ? 1 : fit));
    std::vector<std::tuple<std::string, double, double, double, double>>
        order = items;
    std::stable_sort(order.begin(), order.end(),
                     [](const auto& a, const auto& b) {
                         return std::get<0>(a) < std::get<0>(b);
                     });
    GridControls out;
    out.offs.reserve(order.size());
    out.occ.reserve(order.size());
    for (int i = 0; i < static_cast<int>(order.size()); ++i) {
        const auto& row = order[static_cast<std::size_t>(i)];
        const int cx = i % cols;
        const int cy = i / cols;
        const double x0 = zone_pad + static_cast<double>(cx) * cell;
        const double y0 = zone_pad + static_cast<double>(cy) * cell;
        const double bx0 = std::get<1>(row);
        const double by0 = std::get<2>(row);
        const double fw = (std::get<3>(row) - bx0) + place_clear;
        const double fh = (std::get<4>(row) - by0) + place_clear;
        const double ox = x0 + (cell - fw) / 2.0 - bx0 + place_clear / 2.0;
        const double oy = y0 + (cell - fh) / 2.0 - by0 + place_clear / 2.0;
        out.offs.emplace_back(std::get<0>(row), py_round(ox, 4),
                              py_round(oy, 4));
        out.occ.push_back(Box4{x0, y0, x0 + cell, y0 + cell});
    }
    const int rows = (n + cols - 1) / cols;
    out.packed_w = zone_pad + static_cast<double>(cols) * cell;
    out.packed_h = zone_pad + static_cast<double>(rows) * cell;
    return out;
}

namespace {

std::string fmt4(double value) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.4f", value);
    return buf;
}

using CuBox = std::tuple<double, double, double, double, double, std::string>;
using Hole = std::tuple<double, double, double, std::string>;

}  // namespace

ContactGeom contact_geometry(
    const std::vector<std::tuple<double, double, double, double>>& pads) {
    if (pads.empty()) {
        throw std::runtime_error("no pads — contact geometry underivable");
    }
    std::map<std::pair<double, double>, int> tally;
    double span_u = 0.0;
    for (const auto& pad : pads) {
        const double uu = std::get<0>(pad);
        const double ww = std::get<2>(pad);
        const double hh = std::get<3>(pad);
        tally[{ww, hh}] += 1;
        span_u = std::max(span_u, std::fabs(uu));
    }
    std::pair<double, double> best = tally.begin()->first;
    int best_n = -1;
    for (const auto& kv : tally) {
        if (kv.second > best_n
            || (kv.second == best_n && kv.first < best)) {
            best_n = kv.second;
            best = kv.first;
        }
    }
    std::vector<std::pair<double, double>> contacts;
    contacts.reserve(pads.size());
    for (const auto& pad : pads) {
        if (std::get<2>(pad) == best.first && std::get<3>(pad) == best.second) {
            contacts.emplace_back(std::get<0>(pad), std::get<1>(pad));
        }
    }
    std::set<double> col_set;
    double row_v = 0.0;
    for (const auto& c : contacts) {
        col_set.insert(py_round(c.first, 4));
        row_v = std::max(row_v, std::fabs(c.second));
    }
    std::vector<double> cols(col_set.begin(), col_set.end());
    if (cols.size() < 2) {
        throw std::runtime_error(std::to_string(cols.size())
                                 + " contact column(s) — pitch underivable");
    }
    std::vector<double> gaps;
    gaps.reserve(cols.size() - 1);
    for (std::size_t i = 0; i + 1 < cols.size(); ++i) {
        gaps.push_back(cols[i + 1] - cols[i]);
    }
    std::sort(gaps.begin(), gaps.end());
    ContactGeom out;
    out.row_v = row_v;
    out.half_w = best.first / 2.0;
    out.half_h = best.second / 2.0;
    out.span_u = span_u;
    out.pitch = gaps[gaps.size() / 2];
    return out;
}

std::pair<bool, std::string> via_feasible(
    double u, double v, double dia, double drill,
    const std::vector<CuBox>& front_cu, const std::vector<CuBox>& back_cu,
    const std::vector<CuBox>& samenet, const std::vector<Hole>& holes,
    const ViaClear& clear, bool want_audit) {
    const double rv = dia / 2.0;
    const double rh = drill / 2.0;
    const std::pair<const char*, const std::vector<CuBox>*> layers[2] = {
        {"F.Cu", &front_cu},
        {"B.Cu", &back_cu},
    };
    for (const auto& layer : layers) {
        for (const auto& bx : *layer.second) {
            const Box4 box{std::get<0>(bx), std::get<1>(bx), std::get<2>(bx),
                           std::get<3>(bx)};
            const double d = point_box_dist(u, v, box);
            const double need = rv + std::get<4>(bx) + clear.margin;
            if (d < need) {
                if (!want_audit) {
                    return {false, {}};
                }
                return {false, std::string(layer.first) + " " + std::get<5>(bx)
                                   + " annulus " + fmt4(d) + " < " + fmt4(need)};
            }
            if (d < rh + clear.hole_foreign) {
                if (!want_audit) {
                    return {false, {}};
                }
                return {false, std::string(layer.first) + " " + std::get<5>(bx)
                                   + " hole " + fmt4(d)};
            }
        }
    }
    for (const auto& bx : samenet) {
        const Box4 box{std::get<0>(bx), std::get<1>(bx), std::get<2>(bx),
                       std::get<3>(bx)};
        const double d = point_box_dist(u, v, box);
        if (d < rh + clear.hole_samenet) {
            if (!want_audit) {
                return {false, {}};
            }
            return {false, "same-net " + std::get<5>(bx) + " drill " + fmt4(d)
                               + " < " + fmt4(rh + clear.hole_samenet)
                               + " (via-in-pad DFM)"};
        }
    }
    for (const auto& hole : holes) {
        const double du = u - std::get<0>(hole);
        const double dv = v - std::get<1>(hole);
        const double d = std::hypot(du, dv);
        if (d < std::get<2>(hole) + rh + clear.hole_hole) {
            if (!want_audit) {
                return {false, {}};
            }
            return {false, "hole-hole " + std::get<3>(hole) + " " + fmt4(d)};
        }
    }
    return {true, {}};
}

SeatBandResult seat_band(
    const std::vector<std::tuple<std::string, double, double>>& members,
    const std::vector<CuBox>& front_cu, const std::vector<CuBox>& back_cu,
    const std::vector<CuBox>& samenet, const std::vector<Hole>& holes,
    double row_v, double half_h,
    const std::vector<std::pair<double, double>>& ladder, const ViaClear& clear,
    double via_row, double r_construct, double lattice, const std::string& conn,
    int depth) {
    if (members.empty()) {
        throw std::runtime_error("seat_band: members required");
    }
    SeatBandResult out;
    std::vector<double> us;
    us.reserve(members.size());
    for (const auto& m : members) {
        us.push_back(std::get<1>(m));
    }
    std::sort(us.begin(), us.end());
    us.erase(std::unique(us.begin(), us.end()), us.end());
    const double u_first = us.front();
    const double u_last = us.back();
    const double center = (u_first + u_last) / 2.0;
    std::vector<std::string> names;
    names.reserve(members.size());
    for (const auto& m : members) {
        names.push_back(std::get<0>(m));
    }
    std::vector<std::pair<double, double>> pts;
    pts.reserve(members.size());
    for (const auto& m : members) {
        pts.emplace_back(std::get<1>(m), std::get<2>(m));
    }
    for (const auto& rung : ladder) {
        const double dia = rung.first;
        const double drill = rung.second;
        const double rv = dia / 2.0;
        const double v_max = row_v - half_h - rv - via_row;
        const double reach =
            std::sqrt(std::max(r_construct * r_construct - row_v * row_v, 0.0));
        const double lo = u_last - reach;
        const double hi = u_first + reach;
        const long i0 =
            static_cast<long>(std::ceil(lo / lattice - 1e-9));
        const long i1 =
            static_cast<long>(std::floor(hi / lattice + 1e-9));
        std::vector<double> u_cands;
        for (long i = i0; i <= i1; ++i) {
            u_cands.push_back(
                py_round(static_cast<double>(i) * lattice, 6));
        }
        std::sort(u_cands.begin(), u_cands.end(),
                  [center](double a, double b) {
                      const double da = std::fabs(a - center);
                      const double db = std::fabs(b - center);
                      if (da != db) {
                          return da < db;
                      }
                      return -a < -b;
                  });
        const int vmax_n = static_cast<int>(v_max / lattice);
        std::vector<double> v_cands;
        for (int k = -vmax_n; k <= vmax_n; ++k) {
            v_cands.push_back(
                py_round(static_cast<double>(k) * lattice, 6));
        }
        std::sort(v_cands.begin(), v_cands.end(), [](double a, double b) {
            const double da = std::fabs(a);
            const double db = std::fabs(b);
            if (da != db) {
                return da < db;
            }
            return -a < -b;
        });
        for (double vv : v_cands) {
            for (double uu : u_cands) {
                const auto cov = coverage_ok(uu, vv, pts, r_construct);
                if (!cov.first) {
                    continue;
                }
                const auto hit = via_feasible(uu, vv, dia, drill, front_cu,
                                              back_cu, samenet, holes, clear,
                                              true);
                if (!hit.first) {
                    if (!hit.second.empty()) {
                        out.audit.push_back(hit.second);
                    }
                    continue;
                }
                SeatLedger led;
                led.kind = "seat";
                led.conn = conn;
                led.u = uu;
                led.v = vv;
                led.dia = dia;
                led.drill = drill;
                led.worst = py_round(cov.second, 4);
                led.depth = depth;
                led.members = names;
                out.ledger.push_back(std::move(led));
                SeatVia via;
                via.u = uu;
                via.v = vv;
                via.dia = dia;
                via.drill = drill;
                via.worst = cov.second;
                via.members = names;
                out.vias.push_back(std::move(via));
                return out;
            }
        }
    }
    if (us.size() > 1) {
        std::vector<std::pair<double, std::size_t>> gaps;
        for (std::size_t i = 0; i + 1 < us.size(); ++i) {
            gaps.emplace_back(us[i + 1] - us[i], i);
        }
        std::sort(gaps.begin(), gaps.end(),
                  [center, &us](const auto& a, const auto& b) {
                      if (a.first != b.first) {
                          return a.first > b.first;
                      }
                      return std::fabs(us[a.second] - center)
                          < std::fabs(us[b.second] - center);
                  });
        const double cut =
            (us[gaps[0].second] + us[gaps[0].second + 1]) / 2.0;
        SeatLedger led;
        led.kind = "split_u";
        led.conn = conn;
        led.at = py_round(cut, 4);
        led.depth = depth;
        led.members = names;
        out.ledger.push_back(std::move(led));
        std::vector<std::tuple<std::string, double, double>> left;
        std::vector<std::tuple<std::string, double, double>> right;
        for (const auto& m : members) {
            if (std::get<1>(m) < cut) {
                left.push_back(m);
            } else if (std::get<1>(m) > cut) {
                right.push_back(m);
            }
        }
        auto lhit = seat_band(left, front_cu, back_cu, samenet, holes, row_v,
                              half_h, ladder, clear, via_row, r_construct,
                              lattice, conn, depth + 1);
        out.ledger.insert(out.ledger.end(), lhit.ledger.begin(),
                          lhit.ledger.end());
        out.audit.insert(out.audit.end(), lhit.audit.begin(), lhit.audit.end());
        if (lhit.vias.empty()) {
            return out;
        }
        auto rhit = seat_band(right, front_cu, back_cu, samenet, holes, row_v,
                              half_h, ladder, clear, via_row, r_construct,
                              lattice, conn, depth + 1);
        out.ledger.insert(out.ledger.end(), rhit.ledger.begin(),
                          rhit.ledger.end());
        out.audit.insert(out.audit.end(), rhit.audit.begin(), rhit.audit.end());
        if (rhit.vias.empty()) {
            return out;
        }
        out.vias.insert(out.vias.end(), lhit.vias.begin(), lhit.vias.end());
        out.vias.insert(out.vias.end(), rhit.vias.begin(), rhit.vias.end());
        return out;
    }
    std::vector<double> rows;
    for (const auto& m : members) {
        rows.push_back(std::get<2>(m));
    }
    std::sort(rows.begin(), rows.end());
    rows.erase(std::unique(rows.begin(), rows.end()), rows.end());
    if (rows.size() > 1) {
        SeatLedger led;
        led.kind = "split_row";
        led.conn = conn;
        led.depth = depth;
        led.members = names;
        out.ledger.push_back(std::move(led));
        for (double rv : rows) {
            std::vector<std::tuple<std::string, double, double>> sub;
            for (const auto& m : members) {
                if (std::get<2>(m) == rv) {
                    sub.push_back(m);
                }
            }
            auto hit = seat_band(sub, front_cu, back_cu, samenet, holes, row_v,
                                 half_h, ladder, clear, via_row, r_construct,
                                 lattice, conn, depth + 1);
            out.ledger.insert(out.ledger.end(), hit.ledger.begin(),
                              hit.ledger.end());
            out.audit.insert(out.audit.end(), hit.audit.begin(),
                             hit.audit.end());
            if (hit.vias.empty()) {
                out.vias.clear();
                return out;
            }
            out.vias.insert(out.vias.end(), hit.vias.begin(), hit.vias.end());
        }
        return out;
    }
    return out;
}

bool is_passive_ref(const std::string& ref) {
    if (ref.empty()) {
        return false;
    }
    const char head = ref[0];
    if (head != 'R' && head != 'C' && head != 'L') {
        return false;
    }
    if (ref.size() >= 2 && ref[0] == 'R' && ref[1] == 'J') {
        return false;
    }
    if (ref.size() >= 3 && ref.compare(0, 3, "LED") == 0) {
        return false;
    }
    return true;
}

std::string classify_side(const std::string& ref, const std::string& lib,
                          const Box4& bbox, bool in_decoupling, bool two_side,
                          double top_area,
                          const std::vector<std::string>& top_always) {
    if (!two_side) {
        return "top";
    }
    for (const auto& tok : top_always) {
        if (lib.find(tok) != std::string::npos) {
            return "top";
        }
    }
    const double area = (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0);
    if (area >= top_area) {
        return "top";
    }
    if (in_decoupling) {
        return "bottom";
    }
    if (is_passive_ref(ref)) {
        return "bottom";
    }
    return "top";
}

std::vector<std::string> decoupling_caps(
    const std::vector<std::tuple<std::string, std::vector<std::string>>>&
        net_refs) {
    std::map<std::string, std::set<std::string>> cap_nets;
    for (const auto& row : net_refs) {
        const std::string& name = std::get<0>(row);
        if (name.size() >= 13 && name.compare(0, 13, "unconnected-") == 0) {
            continue;
        }
        for (const auto& ref : std::get<1>(row)) {
            if (!ref.empty() && ref[0] == 'C' && ref[0] != '#') {
                cap_nets[ref].insert(name);
            }
        }
    }
    std::vector<std::string> out;
    for (const auto& kv : cap_nets) {
        const bool has_gnd = kv.second.count("GND") != 0;
        int rails = 0;
        for (const auto& n : kv.second) {
            if (n != "GND") {
                rails += 1;
            }
        }
        if (has_gnd && rails == 1
            && static_cast<int>(kv.second.size()) == 2) {
            out.push_back(kv.first);
        }
    }
    return out;
}

double zone_target_w(double tot_area, double fill, double aspect,
                     double floor_mm) {
    return std::max(floor_mm, std::sqrt(tot_area * fill)) * aspect;
}

double connector_target_w(double row_span, double zone_pad, double tot_area,
                          double fill, double aspect) {
    return std::max(row_span - zone_pad, std::sqrt(tot_area * fill) * aspect);
}

Box4 canonical_plane_rect(double origin_x, double origin_y, double board_w,
                          double board_h, double edge_back) {
    return Box4{py_round(origin_x + edge_back, 3),
                py_round(origin_y + edge_back, 3),
                py_round(origin_x + board_w - edge_back, 3),
                py_round(origin_y + board_h - edge_back, 3)};
}

Box4 isolation_void_rect(const Box4& court, double margin) {
    return Box4{py_round(court.x0 - margin, 3), py_round(court.y0 - margin, 3),
                py_round(court.x1 + margin, 3), py_round(court.y1 + margin, 3)};
}

Box4 board_box_to_uv(double cx, double cy, double rot, const Box4& box) {
    const double xs[2] = {box.x0, box.x1};
    const double ys[2] = {box.y0, box.y1};
    bool any = false;
    double min_u = 0.0;
    double min_v = 0.0;
    double max_u = 0.0;
    double max_v = 0.0;
    for (double x : xs) {
        for (double y : ys) {
            const auto uv = board_to_uv(cx, cy, x, y, rot);
            if (!any) {
                min_u = max_u = uv.first;
                min_v = max_v = uv.second;
                any = true;
            } else {
                min_u = std::min(min_u, uv.first);
                min_v = std::min(min_v, uv.second);
                max_u = std::max(max_u, uv.first);
                max_v = std::max(max_v, uv.second);
            }
        }
    }
    return Box4{min_u, min_v, max_u, max_v};
}

std::vector<std::vector<Seg2>> cluster_slot_segs(
    const std::vector<std::tuple<std::string, double, double>>& pad_offs,
    const std::vector<std::string>& pad_nets,
    const std::vector<std::pair<double, double>>& slots,
    const std::vector<
        std::tuple<std::string, std::vector<std::pair<double, double>>>>&
        static_pts) {
    if (pad_offs.size() != pad_nets.size()) {
        throw std::runtime_error("cluster_slot_segs: pad/net size mismatch");
    }
    std::unordered_map<std::string, std::vector<std::pair<double, double>>>
        pts_of;
    for (const auto& row : static_pts) {
        pts_of[std::get<0>(row)] = std::get<1>(row);
    }
    std::vector<std::vector<Seg2>> out;
    out.reserve(slots.size());
    for (const auto& slot : slots) {
        std::vector<Seg2> segs;
        for (std::size_t i = 0; i < pad_offs.size(); ++i) {
            const std::string& net = pad_nets[i];
            if (net.empty()) {
                continue;
            }
            auto found = pts_of.find(net);
            if (found == pts_of.end() || found->second.empty()) {
                continue;
            }
            const double px = slot.first + std::get<1>(pad_offs[i]);
            const double py = slot.second + std::get<2>(pad_offs[i]);
            const auto tgt = nearest_manhattan(px, py, found->second);
            segs.push_back(Seg2{px, py, tgt.first, tgt.second});
        }
        out.push_back(std::move(segs));
    }
    return out;
}

namespace {

struct EscapeAttach {
    double u = 0.0;
    std::string kind;
    double a = 0.0;
    double b = 0.0;
    std::string pad;
};

int attach_kind_rank(const std::string& kind) {
    if (kind == "column") {
        return 0;
    }
    if (kind == "pad") {
        return 1;
    }
    if (kind == "pair") {
        return 2;
    }
    throw std::runtime_error("escape_ladder_plan: unknown attach kind");
}

bool attach_less(const EscapeAttach& left, const EscapeAttach& right) {
    if (left.u != right.u) {
        return left.u < right.u;
    }
    const int left_rank = attach_kind_rank(left.kind);
    const int right_rank = attach_kind_rank(right.kind);
    if (left_rank != right_rank) {
        return left_rank < right_rank;
    }
    if (left.kind == "column") {
        return false;
    }
    if (left.a != right.a) {
        return left.a < right.a;
    }
    if (left.b != right.b) {
        return left.b < right.b;
    }
    return left.pad < right.pad;
}

bool attach_same(const EscapeAttach& left, const EscapeAttach& right) {
    return left.u == right.u && left.kind == right.kind && left.a == right.a
        && left.b == right.b && left.pad == right.pad;
}

}

std::vector<EscapeLadderSeg> escape_ladder_plan(
    const std::vector<std::tuple<double, double, std::string>>& gnd_pads,
    const std::vector<std::pair<double, double>>& vias, double pitch,
    double pitch_tol, double row_v, double stub_w_pair,
    double stub_w_single, double spine_w) {
    if (gnd_pads.empty()) {
        throw std::runtime_error("escape_ladder_plan: GND pads required");
    }
    if (vias.empty()) {
        throw std::runtime_error("escape_ladder_plan: vias required");
    }
    if (pitch_tol < 0.0) {
        throw std::runtime_error("escape_ladder_plan: pitch_tol required");
    }
    std::vector<std::tuple<double, double, std::string>> pads = gnd_pads;
    for (auto& pad : pads) {
        std::get<0>(pad) = py_round(std::get<0>(pad), 4);
        std::get<1>(pad) = py_round(std::get<1>(pad), 4);
    }
    std::sort(pads.begin(), pads.end());
    std::map<double, std::set<double>> cols;
    for (const auto& pad : pads) {
        cols[std::get<0>(pad)].insert(std::get<1>(pad));
    }
    std::vector<double> both_rows;
    for (const auto& col : cols) {
        if (col.second.size() >= 2) {
            both_rows.push_back(col.first);
        }
    }
    std::vector<EscapeAttach> attaches;
    std::set<double> used_cols;
    for (std::size_t i = 0; i + 1 < both_rows.size(); ++i) {
        const double left_u = both_rows[i];
        const double right_u = both_rows[i + 1];
        if (std::abs(right_u - left_u - pitch) < pitch_tol) {
            EscapeAttach attach;
            attach.u = py_round((left_u + right_u) / 2.0, 4);
            attach.kind = "pair";
            attach.a = left_u;
            attach.b = right_u;
            attaches.push_back(attach);
            used_cols.insert(left_u);
            used_cols.insert(right_u);
        }
    }
    for (double col_u : both_rows) {
        if (used_cols.find(col_u) == used_cols.end()) {
            EscapeAttach attach;
            attach.u = col_u;
            attach.kind = "column";
            attach.a = col_u;
            attaches.push_back(attach);
        }
    }
    for (const auto& pad : pads) {
        const double pad_u = std::get<0>(pad);
        if (std::find(both_rows.begin(), both_rows.end(), pad_u)
            == both_rows.end()) {
            EscapeAttach attach;
            attach.u = pad_u;
            attach.kind = "pad";
            attach.a = pad_u;
            attach.b = std::get<1>(pad);
            attach.pad = std::get<2>(pad);
            attaches.push_back(attach);
        }
    }
    std::sort(attaches.begin(), attaches.end(), attach_less);
    if (attaches.empty()) {
        throw std::runtime_error("escape_ladder_plan: no GND attach options");
    }
    std::vector<std::pair<double, double>> via_rows = vias;
    std::sort(via_rows.begin(), via_rows.end(),
              [](const std::pair<double, double>& left,
                 const std::pair<double, double>& right) {
                  return left.first < right.first;
              });
    std::vector<EscapeAttach> needed;
    for (const auto& via : via_rows) {
        std::vector<EscapeAttach> left;
        std::vector<EscapeAttach> right;
        for (const auto& attach : attaches) {
            if (attach.u <= via.first) {
                left.push_back(attach);
            }
            if (attach.u >= via.first) {
                right.push_back(attach);
            }
        }
        std::vector<EscapeAttach> picks;
        if (!left.empty()) {
            picks.push_back(left.back());
        }
        if (!right.empty()) {
            picks.push_back(right.front());
        }
        if (picks.size() < 2) {
            picks = attaches;
            std::stable_sort(
                picks.begin(), picks.end(),
                [&](const EscapeAttach& left_a, const EscapeAttach& right_a) {
                    const double left_d = std::abs(left_a.u - via.first);
                    const double right_d = std::abs(right_a.u - via.first);
                    if (left_d != right_d) {
                        return left_d < right_d;
                    }
                    if (left_a.u != right_a.u) {
                        return left_a.u < right_a.u;
                    }
                    return false;
                });
            if (picks.size() > 2) {
                picks.resize(2);
            }
        }
        for (const auto& pick : picks) {
            bool seen = false;
            for (const auto& have : needed) {
                if (attach_same(have, pick)) {
                    seen = true;
                    break;
                }
            }
            if (!seen) {
                needed.push_back(pick);
            }
        }
    }
    std::sort(needed.begin(), needed.end(), attach_less);
    std::vector<EscapeLadderSeg> stub_segs;
    for (const auto& attach : needed) {
        EscapeLadderSeg seg;
        if (attach.kind == "pair") {
            seg.ax = attach.u;
            seg.ay = -row_v;
            seg.bx = attach.u;
            seg.by = row_v;
            seg.w = stub_w_pair;
            seg.role = "stub_pair";
        } else if (attach.kind == "column") {
            seg.ax = attach.u;
            seg.ay = -row_v;
            seg.bx = attach.u;
            seg.by = row_v;
            seg.w = stub_w_single;
            seg.role = "stub_column";
        } else {
            seg.ax = attach.a;
            seg.ay = std::copysign(row_v, attach.b);
            seg.bx = attach.a;
            seg.by = 0.0;
            seg.w = stub_w_single;
            seg.role = "stub_pad";
        }
        stub_segs.push_back(seg);
    }
    for (const auto& via : vias) {
        if (std::abs(via.second) > 1e-9) {
            EscapeLadderSeg seg;
            seg.ax = via.first;
            seg.ay = 0.0;
            seg.bx = via.first;
            seg.by = via.second;
            seg.w = stub_w_single;
            seg.role = "stub_via";
            stub_segs.push_back(seg);
        }
    }
    std::vector<double> attach_us;
    attach_us.reserve(needed.size() + vias.size());
    for (const auto& attach : needed) {
        attach_us.push_back(attach.u);
    }
    for (const auto& via : vias) {
        attach_us.push_back(via.first);
    }
    if (attach_us.empty()) {
        throw std::runtime_error("escape_ladder_plan: spine span required");
    }
    EscapeLadderSeg spine;
    spine.ax = *std::min_element(attach_us.begin(), attach_us.end());
    spine.ay = 0.0;
    spine.bx = *std::max_element(attach_us.begin(), attach_us.end());
    spine.by = 0.0;
    spine.w = spine_w;
    spine.role = "spine";
    std::vector<EscapeLadderSeg> segs;
    segs.reserve(1 + stub_segs.size());
    segs.push_back(spine);
    segs.insert(segs.end(), stub_segs.begin(), stub_segs.end());
    return segs;
}

namespace {

int escape_find(std::vector<int>& parent, int index) {
    while (parent[static_cast<std::size_t>(index)] != index) {
        const int grand =
            parent[static_cast<std::size_t>(
                parent[static_cast<std::size_t>(index)])];
        parent[static_cast<std::size_t>(index)] = grand;
        index = grand;
    }
    return index;
}

void escape_union(std::vector<int>& parent, int left, int right) {
    parent[static_cast<std::size_t>(escape_find(parent, left))] =
        escape_find(parent, right);
}

Box4 escape_pad_box(double pad_u, double pad_v, double half_w, double half_h) {
    return Box4{pad_u - half_w, pad_v - half_h, pad_u + half_w,
                pad_v + half_h};
}

bool escape_nodes_touch(
    int left_kind, std::size_t left_idx, int right_kind, std::size_t right_idx,
    const std::vector<std::tuple<double, double, double>>& vias,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& segs,
    const std::vector<std::pair<double, double>>& pads, double half_w,
    double half_h) {
    if (left_kind > right_kind) {
        return escape_nodes_touch(right_kind, right_idx, left_kind, left_idx,
                                  vias, segs, pads, half_w, half_h);
    }
    if (left_kind == 1 && right_kind == 1) {
        const auto& left = segs[left_idx];
        const auto& right = segs[right_idx];
        const Box4 box{
            std::min(std::get<0>(right), std::get<2>(right))
                - std::get<4>(right) / 2.0,
            std::min(std::get<1>(right), std::get<3>(right))
                - std::get<4>(right) / 2.0,
            std::max(std::get<0>(right), std::get<2>(right))
                + std::get<4>(right) / 2.0,
            std::max(std::get<1>(right), std::get<3>(right))
                + std::get<4>(right) / 2.0};
        return seg_box_dist(std::get<0>(left), std::get<1>(left),
                            std::get<2>(left), std::get<3>(left), box)
            <= std::get<4>(left) / 2.0 + 1e-9;
    }
    if (left_kind == 0 && right_kind == 1) {
        const auto& via = vias[left_idx];
        const auto& seg = segs[right_idx];
        const Box4 box{std::get<0>(via), std::get<1>(via), std::get<0>(via),
                       std::get<1>(via)};
        return seg_box_dist(std::get<0>(seg), std::get<1>(seg),
                            std::get<2>(seg), std::get<3>(seg), box)
            <= std::get<4>(seg) / 2.0 + std::get<2>(via) / 2.0 + 1e-9;
    }
    if (left_kind == 1 && right_kind == 2) {
        const auto& seg = segs[left_idx];
        const auto& pad = pads[right_idx];
        return seg_box_dist(std::get<0>(seg), std::get<1>(seg),
                            std::get<2>(seg), std::get<3>(seg),
                            escape_pad_box(pad.first, pad.second, half_w,
                                           half_h))
            <= std::get<4>(seg) / 2.0 + 1e-9;
    }
    if (left_kind == 0 && right_kind == 2) {
        const auto& via = vias[left_idx];
        const auto& pad = pads[right_idx];
        return point_box_dist(std::get<0>(via), std::get<1>(via),
                              escape_pad_box(pad.first, pad.second, half_w,
                                             half_h))
            <= std::get<2>(via) / 2.0 + 1e-9;
    }
    if (left_kind == 0 && right_kind == 0) {
        const auto& left = vias[left_idx];
        const auto& right = vias[right_idx];
        return std::hypot(std::get<0>(left) - std::get<0>(right),
                          std::get<1>(left) - std::get<1>(right))
            <= (std::get<2>(left) + std::get<2>(right)) / 2.0 + 1e-9;
    }
    return false;
}

}

EscapeLadderCheck escape_ladder_connected(
    const std::vector<std::tuple<double, double, double>>& vias,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& segs,
    const std::vector<std::pair<double, double>>& pads, double half_w,
    double half_h) {
    if (vias.empty()) {
        throw std::runtime_error("escape_ladder_connected: vias required");
    }
    const std::size_t via_count = vias.size();
    const std::size_t seg_count = segs.size();
    const std::size_t pad_count = pads.size();
    const std::size_t node_count = via_count + seg_count + pad_count;
    std::vector<int> kinds;
    std::vector<std::size_t> local;
    kinds.reserve(node_count);
    local.reserve(node_count);
    for (std::size_t i = 0; i < via_count; ++i) {
        kinds.push_back(0);
        local.push_back(i);
    }
    for (std::size_t i = 0; i < seg_count; ++i) {
        kinds.push_back(1);
        local.push_back(i);
    }
    for (std::size_t i = 0; i < pad_count; ++i) {
        kinds.push_back(2);
        local.push_back(i);
    }
    std::vector<int> parent(node_count);
    for (std::size_t i = 0; i < node_count; ++i) {
        parent[i] = static_cast<int>(i);
    }
    for (std::size_t i = 0; i < node_count; ++i) {
        for (std::size_t j = i + 1; j < node_count; ++j) {
            if (escape_nodes_touch(kinds[i], local[i], kinds[j], local[j],
                                   vias, segs, pads, half_w, half_h)) {
                escape_union(parent, static_cast<int>(i),
                             static_cast<int>(j));
            }
        }
    }
    std::set<int> via_seg_roots;
    for (std::size_t i = 0; i < via_count + seg_count; ++i) {
        via_seg_roots.insert(escape_find(parent, static_cast<int>(i)));
    }
    int pad_stubs = 0;
    for (const auto& seg : segs) {
        const std::string& role = std::get<5>(seg);
        if (role == "stub_pair" || role == "stub_column"
            || role == "stub_pad") {
            pad_stubs += 1;
        }
    }
    EscapeLadderCheck check;
    check.via_seg_components = static_cast<int>(via_seg_roots.size());
    check.pad_stubs = pad_stubs;
    return check;
}

std::optional<double> escape_redundancy_u(
    double base_u, double base_v, double dia, double drill,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& front_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& back_cu,
    const std::vector<std::tuple<double, double, double, double, double,
                                 std::string>>& samenet,
    const std::vector<std::tuple<double, double, double, std::string>>& holes,
    const ViaClear& clear, double redundancy_offset, double lattice,
    int max_steps) {
    if (max_steps < 0) {
        throw std::runtime_error("escape_redundancy_u: max_steps required");
    }
    if (lattice <= 0.0) {
        throw std::runtime_error("escape_redundancy_u: lattice required");
    }
    const double offsets[2] = {redundancy_offset, -redundancy_offset};
    const int signs[2] = {1, -1};
    for (double offset : offsets) {
        for (int step = 0; step < max_steps; ++step) {
            for (int sign : signs) {
                const double candidate = py_round(
                    base_u + offset
                        + static_cast<double>(sign * step) * lattice,
                    6);
                if (via_feasible(candidate, base_v, dia, drill, front_cu,
                                 back_cu, samenet, holes, clear, false)
                        .first) {
                    return candidate;
                }
            }
        }
    }
    return std::nullopt;
}

bool via_in_escape_region(double bx, double by, const Box4& zone,
                          double margin) {
    return zone.x0 + margin <= bx && bx <= zone.x1 - margin
        && zone.y0 + margin <= by && by <= zone.y1 - margin;
}

bool coexistence_box_hit(double inst_x, double inst_y, double rot,
                         const Box4& box, double region_u, double region_v) {
    const double xs[2] = {box.x0, box.x1};
    const double ys[2] = {box.y0, box.y1};
    double min_u = 0.0;
    double max_u = 0.0;
    double min_v = 0.0;
    double max_v = 0.0;
    bool first = true;
    for (double x : xs) {
        for (double y : ys) {
            const auto uv = board_to_uv(inst_x, inst_y, x, y, rot);
            if (first) {
                min_u = max_u = uv.first;
                min_v = max_v = uv.second;
                first = false;
            } else {
                min_u = std::min(min_u, uv.first);
                max_u = std::max(max_u, uv.first);
                min_v = std::min(min_v, uv.second);
                max_v = std::max(max_v, uv.second);
            }
        }
    }
    return max_u >= -region_u && min_u <= region_u
        && max_v >= -region_v && min_v <= region_v;
}

Box4 legalize_som_rect(double som_x, double som_y, double som_w, double som_h,
                       double pad) {
    return {som_x - pad, som_y - pad, som_x + som_w + pad,
            som_y + som_h + pad};
}

std::vector<Box4> legalize_mh_corners(double board_w, double board_h,
                                      double mh_ko) {
    if (mh_ko <= 0.0) {
        throw std::runtime_error("legalize_mh_corners: mh_ko required");
    }
    return {
        {0.0, 0.0, mh_ko, mh_ko},
        {board_w - mh_ko, 0.0, board_w, mh_ko},
        {board_w - mh_ko, board_h - mh_ko, board_w, board_h},
        {0.0, board_h - mh_ko, mh_ko, board_h},
    };
}

std::vector<std::tuple<std::string, double, double, double, double>>
som_jack_rects(
    double som_x, double som_y,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        jacks) {
    std::vector<std::tuple<std::string, double, double, double, double>> out;
    out.reserve(jacks.size());
    for (const auto& jack : jacks) {
        const std::string& ref = std::get<0>(jack);
        if (ref.size() < 2) {
            throw std::runtime_error("som_jack_rects: jack ref required");
        }
        std::string name = "som_j";
        for (std::size_t i = 1; i < ref.size(); ++i) {
            name.push_back(static_cast<char>(
                std::tolower(static_cast<unsigned char>(ref[i]))));
        }
        const double jx = std::get<1>(jack);
        const double jy = std::get<2>(jack);
        const double jw = std::get<3>(jack);
        const double jh = std::get<4>(jack);
        out.emplace_back(name, som_x + jx - jw / 2.0, som_y + jy - jh / 2.0,
                         som_x + jx + jw / 2.0, som_y + jy + jh / 2.0);
    }
    return out;
}

Box4 grow_rect(const Box4& box, double margin) {
    return {box.x0 - margin, box.y0 - margin, box.x1 + margin,
            box.y1 + margin};
}

Box4 offset_rect(const Box4& box, double dx, double dy) {
    return {box.x0 + dx, box.y0 + dy, box.x1 + dx, box.y1 + dy};
}

bool rect_covers(const Box4& outer, const Box4& inner) {
    return outer.x0 <= inner.x0 && outer.y0 <= inner.y0
        && outer.x1 >= inner.x1 && outer.y1 >= inner.y1;
}

bool rects_intersect_open(const Box4& a, const Box4& b) {
    return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
}

bool point_in_rect(double x, double y, const Box4& box) {
    return box.x0 <= x && x <= box.x1 && box.y0 <= y && y <= box.y1;
}

std::pair<double, double> rect_center(const Box4& box) {
    return {(box.x0 + box.x1) / 2.0, (box.y0 + box.y1) / 2.0};
}

std::pair<double, double> coexistence_region(double span_u, double row_v,
                                             double half_h, double lane_handle,
                                             double margin) {
    return {span_u + margin, row_v + half_h + lane_handle + margin};
}

double construct_reach(double r_construct, double row_v) {
    return std::sqrt(std::max(r_construct * r_construct - row_v * row_v, 0.0));
}

Box4 obstacle_scan_region(const std::vector<double>& us, double margin) {
    if (us.empty()) {
        throw std::runtime_error("obstacle_scan_region: us required");
    }
    double min_u = us.front();
    double max_u = us.front();
    for (double u : us) {
        min_u = std::min(min_u, u);
        max_u = std::max(max_u, u);
    }
    return {min_u - margin, -margin, max_u + margin, margin};
}

std::pair<double, double> escape_lane_extents(double row_v, double half_h,
                                              double lane_handle) {
    const double pad_outer_tip = row_v + half_h;
    return {pad_outer_tip, pad_outer_tip + lane_handle};
}

Box4 aabb_from_corners(double x0, double y0, double x1, double y1, int digits) {
    return {py_round(std::min(x0, x1), digits),
            py_round(std::min(y0, y1), digits),
            py_round(std::max(x0, x1), digits),
            py_round(std::max(y0, y1), digits)};
}

double min_hypot_to_points(
    double u, double v,
    const std::vector<std::pair<double, double>>& pts) {
    if (pts.empty()) {
        throw std::runtime_error("min_hypot_to_points: pts required");
    }
    double best = std::hypot(pts.front().first - u, pts.front().second - v);
    for (const auto& pt : pts) {
        best = std::min(best, std::hypot(pt.first - u, pt.second - v));
    }
    return best;
}

bool within_reach(double ax, double ay, double bx, double by, double reach) {
    return std::hypot(ax - bx, ay - by) <= reach;
}

int count_within_reach(
    double cx, double cy,
    const std::vector<std::pair<double, double>>& pts, double radius) {
    int n = 0;
    for (const auto& pt : pts) {
        if (std::hypot(pt.first - cx, pt.second - cy) <= radius) {
            ++n;
        }
    }
    return n;
}

std::pair<double, double> page_mid_local(const Box4& page, double origin_x,
                                         double origin_y) {
    const auto c = rect_center(page);
    return {c.first - origin_x, c.second - origin_y};
}

std::string pair_convergence(bool same_row, int delta_lane) {
    if (same_row && delta_lane == 1) {
        return "immediate";
    }
    if (same_row && delta_lane == 2) {
        return "quad";
    }
    if (same_row) {
        return "split";
    }
    return "row_wrap";
}

double signed_mag(double magnitude, double sign) {
    return std::copysign(magnitude, sign);
}

int pad_row_sign(double v, double deadband) {
    if (std::fabs(v) < deadband) {
        return 0;
    }
    return v > 0.0 ? 1 : -1;
}

int interior_tier(bool module_face, bool exclusive) {
    if (module_face) {
        return 0;
    }
    if (exclusive) {
        return 1;
    }
    return 2;
}

bool bus_lane_adjacent(const std::string& a_net, const std::string& b_net,
                       int a_lane, int b_lane) {
    return a_net == b_net && b_lane - a_lane == 1;
}

std::tuple<double, double, double, double> padded_xywh(
    double x, double y, double w, double h, double pad) {
    return {x - pad, y - pad, w + 2.0 * pad, h + 2.0 * pad};
}

std::tuple<double, double, double, double> box_to_xywh(const Box4& box) {
    return {box.x0, box.y0, box.x1 - box.x0, box.y1 - box.y0};
}

std::vector<std::pair<double, double>> rect_corners_ccw(const Box4& box) {
    return {{box.x0, box.y0}, {box.x1, box.y0}, {box.x1, box.y1},
            {box.x0, box.y1}};
}

double block_area(double w, double h) {
    return py_round(w * h, 1);
}

bool genuine_pair_ok(bool same_row, int delta_lane) {
    return same_row && delta_lane <= 2;
}

std::pair<double, double> round_xy(double x, double y, int digits) {
    return {py_round(x, digits), py_round(y, digits)};
}

Box4 round_box(const Box4& box, int digits) {
    return {py_round(box.x0, digits), py_round(box.y0, digits),
            py_round(box.x1, digits), py_round(box.y1, digits)};
}

double svg_map(double value, double origin, double scale) {
    return py_round(origin + value * scale, 1);
}

std::vector<double> rounded_unique_sorted(const std::vector<double>& vs,
                                          int digits) {
    std::set<double> uniq;
    for (double v : vs) {
        uniq.insert(py_round(v, digits));
    }
    return {uniq.begin(), uniq.end()};
}

std::vector<std::pair<double, double>> closed_rect_pts(const Box4& box,
                                                       int digits) {
    const auto corners = rect_corners_ccw(round_box(box, digits));
    std::vector<std::pair<double, double>> out = corners;
    if (!out.empty()) {
        out.push_back(out.front());
    }
    return out;
}

std::vector<std::tuple<std::string, double, double, double, double>>
offset_named_boxes(
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        boxes,
    double dx, double dy) {
    std::vector<std::tuple<std::string, double, double, double, double>> out;
    out.reserve(boxes.size());
    for (const auto& row : boxes) {
        const auto b = offset_rect(
            {std::get<1>(row), std::get<2>(row), std::get<3>(row),
             std::get<4>(row)},
            dx, dy);
        out.emplace_back(std::get<0>(row), b.x0, b.y0, b.x1, b.y1);
    }
    return out;
}

int inversion_count(
    const std::vector<std::tuple<double, double, std::string>>& pairs) {
    std::vector<std::tuple<double, double, std::string>> sorted = pairs;
    std::stable_sort(sorted.begin(), sorted.end(), [](const auto& left,
                                                      const auto& right) {
        if (std::get<0>(left) != std::get<0>(right)) {
            return std::get<0>(left) < std::get<0>(right);
        }
        return std::get<2>(left) < std::get<2>(right);
    });
    std::vector<double> seq;
    seq.reserve(sorted.size());
    for (const auto& row : sorted) {
        seq.push_back(std::get<1>(row));
    }
    int inversions = 0;
    for (std::size_t i = 0; i < seq.size(); ++i) {
        for (std::size_t j = i + 1; j < seq.size(); ++j) {
            if (seq[i] > seq[j] + 1e-9) {
                ++inversions;
            }
        }
    }
    return inversions;
}

std::pair<double, double> points_centroid(
    const std::vector<std::pair<double, double>>& pts) {
    if (pts.empty()) {
        throw std::runtime_error("points_centroid: pts required");
    }
    double sum_x = 0.0;
    double sum_y = 0.0;
    for (const auto& pt : pts) {
        sum_x += pt.first;
        sum_y += pt.second;
    }
    const double count = static_cast<double>(pts.size());
    return {sum_x / count, sum_y / count};
}

std::pair<double, double> rounded_centroid(
    const std::vector<std::pair<double, double>>& pts, int digits) {
    const auto center = points_centroid(pts);
    return {py_round(center.first, digits), py_round(center.second, digits)};
}

double hypot_xy(double ax, double ay, double bx, double by) {
    return std::hypot(ax - bx, ay - by);
}

std::pair<double, double> boxes_center(const std::vector<Box4>& boxes) {
    if (boxes.empty()) {
        throw std::runtime_error("boxes_center: boxes required");
    }
    double min_x = boxes[0].x0;
    double max_x = boxes[0].x0;
    double min_y = boxes[0].y0;
    double max_y = boxes[0].y0;
    for (const auto& box : boxes) {
        min_x = std::min(min_x, std::min(box.x0, box.x1));
        max_x = std::max(max_x, std::max(box.x0, box.x1));
        min_y = std::min(min_y, std::min(box.y0, box.y1));
        max_y = std::max(max_y, std::max(box.y0, box.y1));
    }
    return {(min_x + max_x) / 2.0, (min_y + max_y) / 2.0};
}

std::pair<double, double> row_extent(const std::vector<Box4>& boxes,
                                     double zone_pad) {
    if (boxes.empty()) {
        throw std::runtime_error("row_extent: boxes required");
    }
    double max_x1 = boxes[0].x1;
    double max_y1 = boxes[0].y1;
    for (const auto& box : boxes) {
        max_x1 = std::max(max_x1, box.x1);
        max_y1 = std::max(max_y1, box.y1);
    }
    return {py_round(max_x1 + zone_pad, 4), py_round(max_y1 + zone_pad, 4)};
}

std::vector<std::pair<std::string, double>> long_axis_coords(
    const std::vector<std::tuple<std::string, double, double>>& centers) {
    if (centers.empty()) {
        throw std::runtime_error("long_axis_coords: centers required");
    }
    double min_x = std::get<1>(centers[0]);
    double max_x = min_x;
    double min_y = std::get<2>(centers[0]);
    double max_y = min_y;
    for (const auto& row : centers) {
        min_x = std::min(min_x, std::get<1>(row));
        max_x = std::max(max_x, std::get<1>(row));
        min_y = std::min(min_y, std::get<2>(row));
        max_y = std::max(max_y, std::get<2>(row));
    }
    const bool use_x = (max_x - min_x) >= (max_y - min_y);
    std::vector<std::pair<std::string, double>> out;
    out.reserve(centers.size());
    for (const auto& row : centers) {
        out.emplace_back(std::get<0>(row),
                         use_x ? std::get<1>(row) : std::get<2>(row));
    }
    return out;
}

std::optional<std::vector<std::string>> topo_order(
    const std::vector<std::string>& parts,
    const std::vector<std::pair<std::string, std::vector<std::string>>>& deps) {
    std::set<std::string> part_set(parts.begin(), parts.end());
    std::map<std::string, std::set<std::string>> dep_map;
    for (const auto& row : deps) {
        dep_map[row.first].insert(row.second.begin(), row.second.end());
    }
    std::map<std::string, int> indeg;
    for (const auto& part : part_set) {
        const auto it = dep_map.find(part);
        indeg[part] = (it == dep_map.end())
            ? 0
            : static_cast<int>(it->second.size());
    }
    std::vector<std::string> ready;
    for (const auto& part : part_set) {
        if (indeg[part] == 0) {
            ready.push_back(part);
        }
    }
    std::sort(ready.begin(), ready.end());
    std::vector<std::string> sorted_parts(part_set.begin(), part_set.end());
    std::vector<std::string> out;
    while (!ready.empty()) {
        const std::string part = ready.front();
        ready.erase(ready.begin());
        out.push_back(part);
        for (const auto& other : sorted_parts) {
            const auto it = dep_map.find(other);
            if (it != dep_map.end() && it->second.count(part) != 0) {
                indeg[other] -= 1;
                if (indeg[other] == 0) {
                    ready.push_back(other);
                }
            }
        }
        std::sort(ready.begin(), ready.end());
    }
    if (out.size() != part_set.size()) {
        return std::nullopt;
    }
    return out;
}

}  // namespace schgen
