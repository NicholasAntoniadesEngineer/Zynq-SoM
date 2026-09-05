#include "schgen/pack.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
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

}  // namespace schgen
