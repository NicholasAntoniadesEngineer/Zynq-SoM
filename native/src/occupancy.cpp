#include "schgen/occupancy.hpp"

#include "schgen/quantize.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <queue>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_set>
#include <utility>

namespace schgen {
namespace {

int axis_ia(char axis) {
    switch (axis) {
        case 'W': return 0;
        case 'E': return 1;
        case 'N': return 2;
        case 'S': return 3;
        default:
            throw std::runtime_error("occupancy: unknown fanout axis");
    }
}

int axis_ib(char axis) {
    switch (axis) {
        case 'W': return 1;
        case 'E': return 0;
        case 'N': return 3;
        case 'S': return 2;
        default:
            throw std::runtime_error("occupancy: unknown fanout axis");
    }
}

double halo_at(const Halo& h, int i) {
    switch (i) {
        case 0: return h.w;
        case 1: return h.e;
        case 2: return h.n;
        case 3: return h.s;
        default:
            throw std::runtime_error("occupancy: halo index");
    }
}

int cell_div(double v, double b) {
    return static_cast<int>(std::floor(v / b));
}

bool rect_eq(const Rect& a, const Rect& b) {
    return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h
        && a.reach.w == b.reach.w && a.reach.e == b.reach.e
        && a.reach.n == b.reach.n && a.reach.s == b.reach.s
        && a.inset.w == b.inset.w && a.inset.e == b.inset.e
        && a.inset.n == b.inset.n && a.inset.s == b.inset.s
        && a.mask == b.mask && a.pmask == b.pmask && a.main == b.main;
}

struct HeapNode {
    double d;
    int i;
    int j;
    bool operator>(const HeapNode& o) const {
        if (d != o.d) return d > o.d;
        if (i != o.i) return i > o.i;
        return j > o.j;
    }
};

struct PairHash {
    std::size_t operator()(const std::pair<int, int>& p) const {
        return (static_cast<std::size_t>(static_cast<uint32_t>(p.first)) << 32)
            ^ static_cast<uint32_t>(p.second);
    }
};

}  // namespace

double py_round(double value, int digits) {
    // CPython 3.11+ round(x, ndigits) uses dtoa mode-3 then strtod:
    // quantize the exact binary value onto 10**-ndigits, half toward even.
    // Binary `value * 10**n` is not that — 11.24955 * 10000 looks like a
    // halfway case in IEEE but the real number sits below the decimal halfway.
    if (digits < 0) {
        throw std::runtime_error("py_round: digits must be >= 0");
    }
    if (!std::isfinite(value) || value == 0.0) {
        return value;
    }
    const bool negative = std::signbit(value);
    const double magnitude = std::fabs(value);
    int exp2 = 0;
    const double frac = std::frexp(magnitude, &exp2);
    const int64_t mantissa =
        static_cast<int64_t>(std::llrint(std::ldexp(frac, 53)));
    const int binary_exp = exp2 - 53;

    __int128 scaled = mantissa;
    for (int i = 0; i < digits; ++i) {
        scaled *= 5;
    }
    const int two_exp = binary_exp + digits;
    __int128 quantized = 0;
    if (two_exp >= 0) {
        if (two_exp >= 70) {
            throw std::runtime_error("py_round: magnitude exceeds kernel range");
        }
        quantized = scaled << two_exp;
    } else {
        const int shift = -two_exp;
        if (shift >= 120) {
            quantized = 0;
        } else {
            const __int128 whole = scaled >> shift;
            const __int128 remainder = scaled - (whole << shift);
            const __int128 half = (__int128)1 << (shift - 1);
            if (remainder > half || (remainder == half && (whole & 1))) {
                quantized = whole + 1;
            } else {
                quantized = whole;
            }
        }
    }
    double scale = 1.0;
    for (int i = 0; i < digits; ++i) {
        scale *= 10.0;
    }
    const double out =
        static_cast<double>(static_cast<int64_t>(quantized)) / scale;
    return negative ? -out : out;
}

Halo halo4(const Halo& reach, const Halo& inset) {
    return Halo{
        std::max(reach.w, std::max(-inset.w, 0.0)),
        std::max(reach.e, std::max(-inset.e, 0.0)),
        std::max(reach.n, std::max(-inset.n, 0.0)),
        std::max(reach.s, std::max(-inset.s, 0.0)),
    };
}

bool occ_pair_active(int a_mask, int a_pmask, bool a_main,
                     int b_mask, int b_pmask, bool b_main) {
    if ((a_mask & b_mask) == 0) {
        return false;
    }
    if (a_main && b_main) {
        return true;
    }
    return (a_pmask & b_pmask) == 0;
}

std::pair<double, double> spatial_bounds(double far_ceil, double max_reach,
                                         double clear, double place_clear,
                                         double cable_gap, double need_ceil) {
    const double reach_floor = py_round(quant_credit(need_ceil), 4);
    const double reach_bound = std::max(reach_floor, max_reach);
    const double envelope = std::max({clear, place_clear, 2.0 * reach_bound,
                                      cable_gap, far_ceil});
    return {reach_bound, envelope};
}

double fanout_sep(const Halo& a_reach, const Halo& a_inset,
                  const Halo& b_reach, const Halo& b_inset, char axis) {
    const int ia = axis_ia(axis);
    const int ib = axis_ib(axis);
    const double ar = halo_at(a_reach, ia);
    const double br = halo_at(b_reach, ib);
    const double sa = ar > 0.0 ? ar - halo_at(b_inset, ib) : 0.0;
    const double sb = br > 0.0 ? br - halo_at(a_inset, ia) : 0.0;
    return std::max(sa, sb);
}

bool boxes_separated(double ax, double ay, double aw, double ah,
                     double bx, double by, double bw, double bh,
                     double gx, double gy) {
    return ax + aw + gx <= bx || bx + bw + gx <= ax
        || ay + ah + gy <= by || by + bh + gy <= ay;
}

bool cross_edge_fanout_hold(const std::vector<EdgeFanoutBlock>& blocks,
                            double clear) {
    for (std::size_t i = 0; i < blocks.size(); ++i) {
        const EdgeFanoutBlock& a = blocks[i];
        if (a.edge != 'N' && a.edge != 'E' && a.edge != 'S' && a.edge != 'W') {
            throw std::runtime_error(
                "cross_edge_fanout_hold: edge must be N/E/S/W");
        }
        for (std::size_t j = i + 1; j < blocks.size(); ++j) {
            const EdgeFanoutBlock& b = blocks[j];
            if (b.edge != 'N' && b.edge != 'E' && b.edge != 'S'
                && b.edge != 'W') {
                throw std::runtime_error(
                    "cross_edge_fanout_hold: edge must be N/E/S/W");
            }
            if (a.edge == b.edge) {
                continue;
            }
            const double gap_x = std::max(
                clear, fanout_sep(a.reach, a.inset, b.reach, b.inset,
                                  a.x <= b.x ? 'E' : 'W'));
            const double gap_y = std::max(
                clear, fanout_sep(a.reach, a.inset, b.reach, b.inset,
                                  a.y <= b.y ? 'S' : 'N'));
            if (!boxes_separated(a.x, a.y, a.w, a.h, b.x, b.y, b.w, b.h,
                                 gap_x, gap_y)) {
                return false;
            }
        }
    }
    return true;
}

bool edge_run_margin_ok(char edge, double x, double y, double w, double h,
                        double board_w, double board_h, double edge_margin,
                        double overflow_tol) {
    if (edge != 'N' && edge != 'E' && edge != 'S' && edge != 'W') {
        throw std::runtime_error("edge_run_margin_ok: edge must be N/E/S/W");
    }
    const bool vertical = (edge == 'W' || edge == 'E');
    const double near = vertical ? y : x;
    const double span = vertical ? h : w;
    const double dim = vertical ? board_h : board_w;
    return !(near < edge_margin - overflow_tol
             || near + span > dim - edge_margin + overflow_tol);
}

bool edge_runs_margin_ok(
    const std::vector<std::tuple<char, double, double, double, double>>&
        blocks,
    double board_w, double board_h, double edge_margin, double overflow_tol) {
    for (const auto& block : blocks) {
        if (!edge_run_margin_ok(std::get<0>(block), std::get<1>(block),
                                std::get<2>(block), std::get<3>(block),
                                std::get<4>(block), board_w, board_h,
                                edge_margin, overflow_tol)) {
            return false;
        }
    }
    return true;
}

bool pairs_hold(const std::vector<std::vector<Rect>>& groups,
                std::size_t subject_count, double clear) {
    if (subject_count > groups.size()) {
        throw std::runtime_error("pairs_hold: subject_count exceeds groups");
    }
    for (std::size_t i = 0; i < subject_count; ++i) {
        for (std::size_t j = i + 1; j < groups.size(); ++j) {
            for (const Rect& a : groups[i]) {
                for (const Rect& b : groups[j]) {
                    if (!occ_pair_active(a.mask, a.pmask, a.main,
                                         b.mask, b.pmask, b.main)) {
                        continue;
                    }
                    const char ax = a.x <= b.x ? 'E' : 'W';
                    const char ay = a.y <= b.y ? 'S' : 'N';
                    const double gx = std::max(
                        clear, fanout_sep(a.reach, a.inset, b.reach, b.inset,
                                          ax));
                    const double gy = std::max(
                        clear, fanout_sep(a.reach, a.inset, b.reach, b.inset,
                                          ay));
                    if (!boxes_separated(a.x, a.y, a.w, a.h, b.x, b.y, b.w,
                                         b.h, gx, gy)) {
                        return false;
                    }
                }
            }
        }
    }
    return true;
}

bool quads_overlap(const std::vector<std::pair<double, double>>& a,
                   const std::vector<std::pair<double, double>>& b) {
    if (a.size() < 3 || b.size() < 3) {
        throw std::runtime_error("quads_overlap: each polygon needs 3 points");
    }
    const std::vector<std::pair<double, double>>* polys[2] = {&a, &b};
    for (const auto* poly : polys) {
        const std::size_t n = poly->size();
        for (std::size_t i = 0; i < n; ++i) {
            const double x0 = (*poly)[i].first;
            const double y0 = (*poly)[i].second;
            const double x1 = (*poly)[(i + 1) % n].first;
            const double y1 = (*poly)[(i + 1) % n].second;
            const double nx = y1 - y0;
            const double ny = x0 - x1;
            double pa_min = 0.0;
            double pa_max = 0.0;
            double pb_min = 0.0;
            double pb_max = 0.0;
            for (std::size_t k = 0; k < a.size(); ++k) {
                const double d = a[k].first * nx + a[k].second * ny;
                if (k == 0) {
                    pa_min = pa_max = d;
                } else {
                    pa_min = std::min(pa_min, d);
                    pa_max = std::max(pa_max, d);
                }
            }
            for (std::size_t k = 0; k < b.size(); ++k) {
                const double d = b[k].first * nx + b[k].second * ny;
                if (k == 0) {
                    pb_min = pb_max = d;
                } else {
                    pb_min = std::min(pb_min, d);
                    pb_max = std::max(pb_max, d);
                }
            }
            if (pa_max <= pb_min + 1e-9 || pb_max <= pa_min + 1e-9) {
                return false;
            }
        }
    }
    return true;
}

Occupancy::Occupancy(double board_w, double board_h, double clear,
                     double bucket, double reach_bound, double step,
                     double frontier_half)
    : board_w_(board_w),
      board_h_(board_h),
      clear_(clear),
      bucket_(bucket),
      reach_bound_(reach_bound),
      step_(step),
      frontier_half_(frontier_half) {}

void Occupancy::set_board(double board_w, double board_h) {
    board_w_ = board_w;
    board_h_ = board_h;
}

void Occupancy::add_one(double x, double y, double w, double h,
                        const Halo& reach, const Halo& inset, int mask,
                        int pmask, bool main) {
    const Halo h4 = halo4(reach, inset);
    for (const double c : {h4.w, h4.e, h4.n, h4.s}) {
        if (c > reach_bound_) {
            throw std::runtime_error(
                "spatial index: fan-out halo component exceeds the static "
                "reach bound");
        }
    }
    const Rect rect{x, y, w, h, reach, inset, mask, pmask, main};
    rects_.push_back(rect);
    const double b = bucket_;
    const int iy0 = cell_div(y - h4.n - clear_, b);
    const int iy1 = cell_div(y + h + h4.s + clear_, b);
    const int ix0 = cell_div(x - h4.w - clear_, b);
    const int ix1 = cell_div(x + w + h4.e + clear_, b);
    for (int ix = ix0; ix <= ix1; ++ix) {
        for (int iy = iy0; iy <= iy1; ++iy) {
            cells_[CellKey{ix, iy}].push_back(rect);
        }
    }
}

void Occupancy::remove_one(double x, double y, double w, double h,
                           const Halo& reach, const Halo& inset, int mask,
                           int pmask, bool main) {
    const Rect want{x, y, w, h, reach, inset, mask, pmask, main};
    auto it = std::find_if(rects_.begin(), rects_.end(),
                           [&](const Rect& r) { return rect_eq(r, want); });
    if (it == rects_.end()) {
        return;
    }
    rects_.erase(it);
    const Halo h4 = halo4(reach, inset);
    const double b = bucket_;
    const int iy0 = cell_div(y - h4.n - clear_, b);
    const int iy1 = cell_div(y + h + h4.s + clear_, b);
    const int ix0 = cell_div(x - h4.w - clear_, b);
    const int ix1 = cell_div(x + w + h4.e + clear_, b);
    for (int ix = ix0; ix <= ix1; ++ix) {
        for (int iy = iy0; iy <= iy1; ++iy) {
            auto cit = cells_.find(CellKey{ix, iy});
            if (cit == cells_.end()) {
                continue;
            }
            auto& lst = cit->second;
            auto lit = std::find_if(lst.begin(), lst.end(),
                                    [&](const Rect& r) { return rect_eq(r, want); });
            if (lit != lst.end()) {
                lst.erase(lit);
            }
        }
    }
}

void Occupancy::add(double x, double y, double w, double h, const Halo& reach,
                    const Halo& inset, int mask, const std::vector<Comp>& comps) {
    add_one(x, y, w, h, reach, inset, mask, mask, true);
    const Halo zero{};
    for (const Comp& c : comps) {
        add_one(py_round(x + c.dx, 4), py_round(y + c.dy, 4), c.w, c.h,
                zero, zero, c.mask, mask, false);
    }
}

void Occupancy::remove(double x, double y, double w, double h,
                       const Halo& reach, const Halo& inset, int mask,
                       const std::vector<Comp>& comps) {
    remove_one(x, y, w, h, reach, inset, mask, mask, true);
    const Halo zero{};
    for (const Comp& c : comps) {
        remove_one(py_round(x + c.dx, 4), py_round(y + c.dy, 4), c.w, c.h,
                   zero, zero, c.mask, mask, false);
    }
}

bool Occupancy::body_clear(double x, double y, double w, double h,
                           const Halo& reach, const Halo& inset, int qmask,
                           int qpmask, bool qmain, bool hashed) const {
    if (hashed) {
        const Halo qh = halo4(reach, inset);
        return query_hashed_cells(x, y, w, h, qh, reach, inset, qmask, qpmask,
                                  qmain);
    }
    for (const Rect& r : rects_) {
        if (!occ_pair_active(qmask, qpmask, qmain, r.mask, r.pmask, r.main)) {
            continue;
        }
        const char ax = x <= r.x ? 'E' : 'W';
        const char ay = y <= r.y ? 'S' : 'N';
        const double gx = std::max(clear_,
            fanout_sep(reach, inset, r.reach, r.inset, ax));
        const double gy = std::max(clear_,
            fanout_sep(reach, inset, r.reach, r.inset, ay));
        if (!boxes_separated(x, y, w, h, r.x, r.y, r.w, r.h, gx, gy)) {
            return false;
        }
    }
    return true;
}

bool Occupancy::query_hashed_cells(double x, double y, double w, double h,
                                   const Halo& qh, const Halo& reach,
                                   const Halo& inset, int qmask, int qpmask,
                                   bool qmain) const {
    const double b = bucket_;
    const int iy0 = cell_div(y - qh.n, b);
    const int iy1 = cell_div(y + h + qh.s, b);
    const int ix0 = cell_div(x - qh.w, b);
    const int ix1 = cell_div(x + w + qh.e, b);
    for (int ix = ix0; ix <= ix1; ++ix) {
        for (int iy = iy0; iy <= iy1; ++iy) {
            auto it = cells_.find(CellKey{ix, iy});
            if (it == cells_.end()) {
                continue;
            }
            for (const Rect& r : it->second) {
                if (!occ_pair_active(qmask, qpmask, qmain,
                                     r.mask, r.pmask, r.main)) {
                    continue;
                }
                const char ax = x <= r.x ? 'E' : 'W';
                const char ay = y <= r.y ? 'S' : 'N';
                const double gx = std::max(clear_,
                    fanout_sep(reach, inset, r.reach, r.inset, ax));
                const double gy = std::max(clear_,
                    fanout_sep(reach, inset, r.reach, r.inset, ay));
                if (!boxes_separated(x, y, w, h, r.x, r.y, r.w, r.h, gx, gy)) {
                    return false;
                }
            }
        }
    }
    return true;
}

bool Occupancy::fits_exhaustive(double x, double y, double w, double h,
                                const Halo& reach, const Halo& inset, int mask,
                                const std::vector<Comp>& comps) const {
    if (x < clear_ || y < clear_ || x + w > board_w_ - clear_
        || y + h > board_h_ - clear_) {
        return false;
    }
    if (!body_clear(x, y, w, h, reach, inset, mask, mask, true, false)) {
        return false;
    }
    const Halo zero{};
    for (const Comp& c : comps) {
        const double cx0 = x + c.dx;
        const double cy0 = y + c.dy;
        if (!body_clear(cx0, cy0, c.w, c.h, zero, zero, c.mask, mask, false,
                        false)) {
            return false;
        }
    }
    return true;
}

bool Occupancy::fits_hashed(double x, double y, double w, double h,
                            const Halo& reach, const Halo& inset, int mask,
                            const std::vector<Comp>& comps) const {
    if (x < clear_ || y < clear_ || x + w > board_w_ - clear_
        || y + h > board_h_ - clear_) {
        return false;
    }
    if (!body_clear(x, y, w, h, reach, inset, mask, mask, true, true)) {
        return false;
    }
    const Halo zero{};
    const Halo z4{};
    for (const Comp& c : comps) {
        const double cx0 = x + c.dx;
        const double cy0 = y + c.dy;
        if (!query_hashed_cells(cx0, cy0, c.w, c.h, z4, zero, zero, c.mask,
                                mask, false)) {
            return false;
        }
    }
    return true;
}

std::optional<Pose> Occupancy::place_near(
    double ax, double ay, double w, double h, const Halo& reach,
    const Halo& inset, int mask, const std::vector<Comp>& comps,
    double win_x0, double win_x1, double win_y0, double win_y1) const {
    const double s = step_;
    const int nx = static_cast<int>(board_w_ / s) + 1;
    const int ny = static_cast<int>(board_h_ / s) + 1;
    const double hw = w / 2.0;
    const double hh = h / 2.0;
    std::vector<std::pair<double, double>> xs;
    std::vector<std::pair<double, double>> ys;
    xs.reserve(static_cast<std::size_t>(nx));
    ys.reserve(static_cast<std::size_t>(ny));
    for (int ix = 0; ix < nx; ++ix) {
        const double xv = ix * s;
        if (win_x0 <= xv && xv <= win_x1) {
            xs.emplace_back(std::abs(xv + hw - ax), xv);
        }
    }
    for (int iy = 0; iy < ny; ++iy) {
        const double yv = iy * s;
        if (win_y0 <= yv && yv <= win_y1) {
            ys.emplace_back(std::abs(yv + hh - ay), yv);
        }
    }
    std::sort(xs.begin(), xs.end());
    std::sort(ys.begin(), ys.end());
    if (xs.empty() || ys.empty()) {
        return std::nullopt;
    }
    std::priority_queue<HeapNode, std::vector<HeapNode>, std::greater<HeapNode>> heap;
    heap.push(HeapNode{xs[0].first + ys[0].first, 0, 0});
    std::unordered_set<std::pair<int, int>, PairHash> seen;
    seen.emplace(0, 0);
    std::unordered_map<double, std::vector<std::pair<double, double>>> buckets;
    std::priority_queue<double, std::vector<double>, std::greater<double>> bkeys;

    auto flush = [&](double thresh) -> std::optional<Pose> {
        while (!bkeys.empty() && bkeys.top() <= thresh) {
            const double key = bkeys.top();
            bkeys.pop();
            auto it = buckets.find(key);
            if (it == buckets.end()) {
                continue;
            }
            std::vector<std::pair<double, double>> cell = std::move(it->second);
            buckets.erase(it);
            std::sort(cell.begin(), cell.end());
            for (const auto& [x, y] : cell) {
                if (fits_hashed(x, y, w, h, reach, inset, mask, comps)) {
                    return Pose{x, y, w, h};
                }
            }
        }
        return std::nullopt;
    };

    while (!heap.empty()) {
        const HeapNode node = heap.top();
        heap.pop();
        const double xcost = xs[static_cast<std::size_t>(node.i)].first;
        const double ycost = ys[static_cast<std::size_t>(node.j)].first;
        const double x = xs[static_cast<std::size_t>(node.i)].second;
        const double y = ys[static_cast<std::size_t>(node.j)].second;
        const double key = py_round(xcost + ycost, 1);
        auto bit = buckets.find(key);
        if (bit == buckets.end()) {
            buckets.emplace(key, std::vector<std::pair<double, double>>{{x, y}});
            bkeys.push(key);
        } else {
            bit->second.emplace_back(x, y);
        }
        if (node.i + 1 < static_cast<int>(xs.size())
            && seen.emplace(node.i + 1, node.j).second) {
            heap.push(HeapNode{xs[static_cast<std::size_t>(node.i + 1)].first
                                   + ys[static_cast<std::size_t>(node.j)].first,
                               node.i + 1, node.j});
        }
        if (node.j + 1 < static_cast<int>(ys.size())
            && seen.emplace(node.i, node.j + 1).second) {
            heap.push(HeapNode{xs[static_cast<std::size_t>(node.i)].first
                                   + ys[static_cast<std::size_t>(node.j + 1)].first,
                               node.i, node.j + 1});
        }
        const double frontier = heap.empty() ? INFINITY : heap.top().d;
        if (auto hit = flush(frontier - frontier_half_)) {
            return hit;
        }
    }
    if (auto hit = flush(INFINITY)) {
        return hit;
    }
    return std::nullopt;
}

std::tuple<double, double, double, double> evict_window(
    double ex, double ey, double ew, double eh, const Halo& e_reach,
    const Halo& e_inset, const std::vector<Comp>& e_comps, double w, double h,
    const Halo& rch, const Halo& ins, const std::vector<Comp>& cc,
    double clear) {
    struct ERect {
        double x = 0.0;
        double y = 0.0;
        double ww = 0.0;
        double hh = 0.0;
        Halo reach;
        Halo inset;
    };
    std::vector<ERect> erects;
    erects.push_back(ERect{ex, ey, ew, eh, e_reach, e_inset});
    const Halo zero{};
    for (const Comp& c : e_comps) {
        erects.push_back(ERect{ex + c.dx, ey + c.dy, c.w, c.h, zero, zero});
    }
    double g = clear;
    const Halo reaches[2] = {rch, zero};
    const Halo insets[2] = {ins, zero};
    const char axes[4] = {'E', 'W', 'N', 'S'};
    for (const ERect& r : erects) {
        for (int k = 0; k < 2; ++k) {
            for (char axis : axes) {
                g = std::max(g, fanout_sep(reaches[k], insets[k], r.reach,
                                           r.inset, axis));
            }
        }
    }
    double ex_lo = w;
    double ex_hi = 0.0;
    double ey_lo = h;
    double ey_hi = 0.0;
    for (const Comp& c : cc) {
        ex_lo = std::max(ex_lo, c.dx + c.w);
        ex_hi = std::min(ex_hi, c.dx);
        ey_lo = std::max(ey_lo, c.dy + c.h);
        ey_hi = std::min(ey_hi, c.dy);
    }
    double x0 = erects[0].x;
    double x1 = erects[0].x + erects[0].ww;
    double y0 = erects[0].y;
    double y1 = erects[0].y + erects[0].hh;
    for (const ERect& r : erects) {
        x0 = std::min(x0, r.x);
        x1 = std::max(x1, r.x + r.ww);
        y0 = std::min(y0, r.y);
        y1 = std::max(y1, r.y + r.hh);
    }
    return {x0 - ex_lo - g, x1 + g - ex_hi, y0 - ey_lo - g, y1 + g - ey_hi};
}

}  // namespace schgen
