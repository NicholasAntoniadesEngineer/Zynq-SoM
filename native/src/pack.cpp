#include "schgen/pack.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <limits>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>

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

}  // namespace schgen
