#include "schgen/seat.hpp"
#include "schgen/occupancy.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <stdexcept>
#include <utility>

namespace schgen {
namespace {

constexpr double kUnreachable = 1e9;

Box4 union_boxes(const std::vector<Box4>& boxes) {
    Box4 u{boxes[0].x0, boxes[0].y0, boxes[0].x1, boxes[0].y1};
    for (const Box4& b : boxes) {
        u.x0 = std::min(u.x0, b.x0);
        u.y0 = std::min(u.y0, b.y0);
        u.x1 = std::max(u.x1, b.x1);
        u.y1 = std::max(u.y1, b.y1);
    }
    return u;
}

}  // namespace

double box_gap(const Box4& a, const Box4& b) {
    double dx = a.x0 - b.x1;
    const double qx = b.x0 - a.x1;
    if (qx > dx) {
        dx = qx;
    }
    if (dx < 0.0) {
        dx = 0.0;
    }
    double dy = a.y0 - b.y1;
    const double qy = b.y0 - a.y1;
    if (qy > dy) {
        dy = qy;
    }
    if (dy < 0.0) {
        dy = 0.0;
    }
    return std::hypot(dx, dy);
}

bool boxes_overlap(const Box4& a, const Box4& b, double halo) {
    return a.x0 - halo < b.x1 && a.x1 + halo > b.x0
        && a.y0 - halo < b.y1 && a.y1 + halo > b.y0;
}

bool spot_free(const Box4& bx, double pad,
               const std::vector<Box4>& parts,
               const std::vector<Box4>& segs,
               const std::vector<Box4>& ncs) {
    for (const Box4& b : parts) {
        if (bx.x0 - pad < b.x1 && bx.x1 + pad > b.x0
            && bx.y0 - pad < b.y1 && bx.y1 + pad > b.y0) {
            return false;
        }
    }
    for (const Box4& s : segs) {
        if (bx.x0 < s.x1 && bx.x1 > s.x0 && bx.y0 < s.y1 && bx.y1 > s.y0) {
            return false;
        }
    }
    for (const Box4& n : ncs) {
        if (bx.x0 - pad < n.x1 && bx.x1 + pad > n.x0
            && bx.y0 - pad < n.y1 && bx.y1 + pad > n.y0) {
            return false;
        }
    }
    return true;
}

SeatList seat_scan(
    double tcx, double tcy, int n, double step, double halo, double net_w,
    int cap,
    const std::vector<Box4>& placed,
    const std::vector<Box4>& forbid,
    const std::vector<Subject>& subjects,
    const std::vector<BoundGroup>& attract,
    const std::vector<BoundGroup>& repulse,
    const std::vector<double>& rots,
    const std::vector<std::vector<Box4>>& rel_pads,
    const std::vector<Box4>& body,
    const std::vector<std::vector<AlignTerm>>& align) {
    if (rots.size() != rel_pads.size() || rots.size() != body.size()
        || rots.size() != align.size()) {
        throw std::runtime_error("seat_scan: rotation tables are different lengths");
    }
    std::vector<double> xs;
    std::vector<double> ys;
    xs.reserve(static_cast<std::size_t>(2 * n + 1));
    ys.reserve(static_cast<std::size_t>(2 * n + 1));
    for (int g = -n; g <= n; ++g) {
        xs.push_back(py_round(tcx + g * step, 4));
        ys.push_back(py_round(tcy + g * step, 4));
    }

    struct Att3 {
        const BoundGroup* g;
        bool has_u;
        Box4 u;
    };
    std::vector<Att3> att3;
    att3.reserve(attract.size());
    for (const BoundGroup& g : attract) {
        if (g.boxes.empty()) {
            att3.push_back(Att3{&g, false, Box4{}});
        } else {
            att3.push_back(Att3{&g, true, union_boxes(g.boxes)});
        }
    }
    std::vector<Att3> rep3;
    rep3.reserve(repulse.size());
    for (const BoundGroup& g : repulse) {
        if (g.boxes.empty()) {
            rep3.push_back(Att3{&g, false, Box4{}});
        } else {
            rep3.push_back(Att3{&g, true, union_boxes(g.boxes)});
        }
    }

    std::vector<SeatHit> scored;
    for (std::size_t ri = 0; ri < rots.size(); ++ri) {
        const double rot = rots[ri];
        const std::vector<Box4>& rel = rel_pads[ri];
        const Box4 rb = body[ri];
        const std::vector<AlignTerm>& arr = align[ri];
        bool has_ru = !rel.empty();
        Box4 ru{};
        if (has_ru) {
            ru = union_boxes(rel);
        }
        for (const double cx : xs) {
            const double b0 = cx + rb.x0;
            const double b2 = cx + rb.x1;
            const double h0 = b0 - halo;
            const double h2 = b2 + halo;
            const double cu0 = cx + ru.x0;
            const double cu2 = cx + ru.x1;
            for (const double cy : ys) {
                const double b1 = cy + rb.y0;
                const double b3 = cy + rb.y1;
                const double h1 = b1 - halo;
                const double h3 = b3 + halo;
                bool ok = true;
                for (const Box4& q : placed) {
                    if (h0 < q.x1 && h2 > q.x0 && h1 < q.y1 && h3 > q.y0) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) {
                    continue;
                }
                for (const Box4& f : forbid) {
                    if (h0 < f.x1 && h2 > f.x0 && h1 < f.y1 && h3 > f.y0) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) {
                    continue;
                }
                const double cu1 = cy + ru.y0;
                const double cu3 = cy + ru.y1;
                double dsum = 0.0;
                std::vector<Box4> rel_off;
                bool have_off = false;
                for (const Att3& a : att3) {
                    if (!a.has_u || !has_ru) {
                        if (kUnreachable > a.g->limit) {
                            ok = false;
                            break;
                        }
                        dsum += kUnreachable;
                        continue;
                    }
                    double dx = a.u.x0 - cu2;
                    const double qx = cu0 - a.u.x1;
                    if (qx > dx) {
                        dx = qx;
                    }
                    if (dx < 0.0) {
                        dx = 0.0;
                    }
                    double dy = a.u.y0 - cu3;
                    const double qy = cu1 - a.u.y1;
                    if (qy > dy) {
                        dy = qy;
                    }
                    if (dy < 0.0) {
                        dy = 0.0;
                    }
                    const double lb = std::hypot(dx, dy);
                    if (lb > a.g->limit) {
                        ok = false;
                        break;
                    }
                    if (!have_off) {
                        rel_off.reserve(rel.size());
                        for (const Box4& rb_i : rel) {
                            rel_off.push_back(Box4{cx + rb_i.x0, cy + rb_i.y0,
                                                   cx + rb_i.x1, cy + rb_i.y1});
                        }
                        have_off = true;
                    }
                    double best = kUnreachable;
                    for (const Box4& tb : a.g->boxes) {
                        for (const Box4& ro : rel_off) {
                            const double g = box_gap(tb, ro);
                            if (g < best) {
                                best = g;
                            }
                        }
                    }
                    if (best < lb) {
                        throw std::runtime_error(
                            "seat LB TRIPWIRE: exact attractor gap below union bound");
                    }
                    if (best > a.g->limit) {
                        ok = false;
                        break;
                    }
                    dsum += best;
                }
                if (!ok) {
                    continue;
                }
                for (const Att3& a : rep3) {
                    if (!a.has_u || !has_ru) {
                        if (kUnreachable < a.g->limit) {
                            ok = false;
                            break;
                        }
                        continue;
                    }
                    double dx = a.u.x0 - cu2;
                    const double qx = cu0 - a.u.x1;
                    if (qx > dx) {
                        dx = qx;
                    }
                    if (dx < 0.0) {
                        dx = 0.0;
                    }
                    double dy = a.u.y0 - cu3;
                    const double qy = cu1 - a.u.y1;
                    if (qy > dy) {
                        dy = qy;
                    }
                    if (dy < 0.0) {
                        dy = 0.0;
                    }
                    const double lb = std::hypot(dx, dy);
                    if (lb >= a.g->limit) {
                        continue;
                    }
                    if (!have_off) {
                        rel_off.reserve(rel.size());
                        for (const Box4& rb_i : rel) {
                            rel_off.push_back(Box4{cx + rb_i.x0, cy + rb_i.y0,
                                                   cx + rb_i.x1, cy + rb_i.y1});
                        }
                        have_off = true;
                    }
                    double best = kUnreachable;
                    for (const Box4& tb : a.g->boxes) {
                        for (const Box4& ro : rel_off) {
                            const double g = box_gap(tb, ro);
                            if (g < best) {
                                best = g;
                            }
                        }
                    }
                    if (best < lb) {
                        throw std::runtime_error(
                            "seat LB TRIPWIRE: exact repulsor gap below union bound");
                    }
                    if (best < a.g->limit) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) {
                    continue;
                }
                for (const Subject& sb : subjects) {
                    if (b0 - sb.need < sb.box.x1 && b2 + sb.need > sb.box.x0
                        && b1 - sb.need < sb.box.y1 && b3 + sb.need > sb.box.y0) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) {
                    continue;
                }
                double dis = 0.0;
                for (const AlignTerm& t : arr) {
                    const double px = cx + t.rxc;
                    const double py = cy + t.ryc;
                    double best = kUnreachable;
                    for (const auto& [qx, qy] : t.pts) {
                        const double man = std::abs(px - qx) + std::abs(py - qy);
                        if (man < best) {
                            best = man;
                        }
                    }
                    dis += best;
                }
                scored.push_back(SeatHit{
                    py_round(dsum + net_w * dis, 4),
                    std::abs(cx), std::abs(cy), rot, cx, cy});
            }
        }
    }
    std::stable_sort(scored.begin(), scored.end(),
                     [](const SeatHit& a, const SeatHit& b) {
                         if (a.score != b.score) return a.score < b.score;
                         if (a.abs_x != b.abs_x) return a.abs_x < b.abs_x;
                         if (a.abs_y != b.abs_y) return a.abs_y < b.abs_y;
                         return a.rot < b.rot;
                     });
    SeatList out;
    out.truncated = cap >= 0 && static_cast<int>(scored.size()) > cap;
    if (out.truncated) {
        scored.resize(static_cast<std::size_t>(cap));
    }
    out.hits = std::move(scored);
    return out;
}

namespace {

double pins_to_target(double cx, double cy, const std::vector<Box4>& pads,
                      const std::vector<Box4>& targets) {
    double best = kUnreachable;
    for (const Box4& tb : targets) {
        for (const Box4& rb : pads) {
            const Box4 qb{cx + rb.x0, cy + rb.y0, cx + rb.x1, cy + rb.y1};
            const double g = box_gap(tb, qb);
            if (g < best) {
                best = g;
            }
        }
    }
    return best;
}

}  // namespace

CandList seat_candidates(
    double tcx, double tcy, int n, double step, double halo,
    double bound_eff, double keep_min, bool forbid_plus_x, int cap,
    const Box4& icb,
    const std::vector<Box4>& skeleton,
    const std::vector<double>& rots,
    const std::vector<Box4>& bodies,
    const std::vector<std::vector<Box4>>& rel_pads,
    const std::vector<Box4>& target_pins,
    const std::vector<Box4>& keep_pins) {
    if (rots.size() != bodies.size() || rots.size() != rel_pads.size()) {
        throw std::runtime_error(
            "seat_candidates: rotation tables are different lengths");
    }
    std::vector<double> xs;
    std::vector<double> ys;
    xs.reserve(static_cast<std::size_t>(2 * n + 1));
    ys.reserve(static_cast<std::size_t>(2 * n + 1));
    for (int g = -n; g <= n; ++g) {
        xs.push_back(py_round(tcx + g * step, 4));
        ys.push_back(py_round(tcy + g * step, 4));
    }
    std::vector<CandHit> scored;
    for (std::size_t ri = 0; ri < rots.size(); ++ri) {
        const double rot = rots[ri];
        const Box4 rb = bodies[ri];
        const std::vector<Box4>& pads = rel_pads[ri];
        for (const double cx : xs) {
            for (const double cy : ys) {
                const Box4 b{cx + rb.x0, cy + rb.y0, cx + rb.x1, cy + rb.y1};
                if (forbid_plus_x && b.x1 + halo > icb.x1) {
                    continue;
                }
                if (boxes_overlap(b, icb, halo)) {
                    continue;
                }
                bool skel_hit = false;
                for (const Box4& s : skeleton) {
                    if (boxes_overlap(b, s, halo)) {
                        skel_hit = true;
                        break;
                    }
                }
                if (skel_hit) {
                    continue;
                }
                const double dist = pins_to_target(cx, cy, pads, target_pins);
                if (dist > bound_eff) {
                    continue;
                }
                if (!keep_pins.empty()
                    && pins_to_target(cx, cy, pads, keep_pins) < keep_min) {
                    continue;
                }
                scored.push_back(CandHit{
                    py_round(dist, 4), std::abs(cx), std::abs(cy), rot, cx, cy,
                    b});
            }
        }
    }
    std::stable_sort(scored.begin(), scored.end(),
                     [](const CandHit& a, const CandHit& b) {
                         if (a.dist != b.dist) return a.dist < b.dist;
                         if (a.abs_x != b.abs_x) return a.abs_x < b.abs_x;
                         if (a.abs_y != b.abs_y) return a.abs_y < b.abs_y;
                         return a.rot < b.rot;
                     });
    CandList out;
    out.truncated = cap >= 0 && static_cast<int>(scored.size()) > cap;
    if (out.truncated) {
        scored.resize(static_cast<std::size_t>(cap));
    }
    out.hits = std::move(scored);
    return out;
}

DfsResult seat_dfs(const std::vector<std::vector<Box4>>& cand_boxes,
                   const std::vector<Box4>& skeleton,
                   double halo, int node_budget) {
    for (const auto& row : cand_boxes) {
        for (const Box4& b : row) {
            for (const Box4& q : skeleton) {
                if (boxes_overlap(b, q, halo)) {
                    throw std::runtime_error(
                        "seat DFS TRIPWIRE: candidate conflicts with the "
                        "skeleton under halo — _candidates no longer "
                        "pre-clears the skeleton, or the expanded-box kernel "
                        "drifted from boxes_overlap");
                }
            }
        }
    }
    DfsResult out;
    const int n_ord = static_cast<int>(cand_boxes.size());
    out.pick.assign(static_cast<std::size_t>(n_ord), -1);
    std::vector<Box4> stack;
    std::function<bool(int)> bt = [&](int i) -> bool {
        if (i == n_ord) {
            return true;
        }
        out.nodes += 1;
        if (out.nodes > node_budget) {
            out.budget_hit = true;
            return false;
        }
        for (std::size_t k = 0; k < cand_boxes[static_cast<std::size_t>(i)].size();
             ++k) {
            const Box4& b = cand_boxes[static_cast<std::size_t>(i)][k];
            const double e0 = b.x0 - halo;
            const double e1 = b.y0 - halo;
            const double e2 = b.x1 + halo;
            const double e3 = b.y1 + halo;
            bool hit = false;
            for (const Box4& q : stack) {
                if (e0 < q.x1 && e2 > q.x0 && e1 < q.y1 && e3 > q.y0) {
                    hit = true;
                    break;
                }
            }
            if (hit) {
                continue;
            }
            out.pick[static_cast<std::size_t>(i)] = static_cast<int>(k);
            stack.push_back(b);
            if (bt(i + 1)) {
                return true;
            }
            stack.pop_back();
            out.pick[static_cast<std::size_t>(i)] = -1;
        }
        return false;
    };
    out.solved = bt(0);
    return out;
}

bool corridor_free(double y, double xa, double xb,
                   const std::vector<Box4>& boxes,
                   const std::vector<Seg2>& segs, double seg_pad) {
    const double x0 = std::min(xa, xb);
    const double x1 = std::max(xa, xb);
    for (const Box4& b : boxes) {
        if (b.y0 + 1e-6 < y && y < b.y1 - 1e-6 && b.x0 < x1 && b.x1 > x0) {
            return false;
        }
    }
    for (const Seg2& s : segs) {
        const double sx0 = std::min(s.x0, s.x1);
        const double sx1 = std::max(s.x0, s.x1);
        const double sy0 = std::min(s.y0, s.y1);
        const double sy1 = std::max(s.y0, s.y1);
        if (sy0 - seg_pad <= y && y <= sy1 + seg_pad
            && sx0 - seg_pad <= x1 && sx1 + seg_pad >= x0) {
            return false;
        }
    }
    return true;
}

bool corridor_clear_vert(double x, double y_pin, double ty,
                         const std::vector<Box4>& boxes,
                         const std::vector<Seg2>& segs, double seg_pad) {
    const double y0 = std::min(y_pin, ty);
    const double y1 = std::max(y_pin, ty);
    for (const Box4& b : boxes) {
        if (b.x0 - 0.2 < x && x < b.x1 + 0.2
            && b.y0 < y1 - 1e-6 && b.y1 > y0 + 1e-6
            && !(std::abs(b.y0 - y_pin) < 1e-6 || std::abs(b.y1 - y_pin) < 1e-6)) {
            return false;
        }
    }
    for (const Seg2& s : segs) {
        const double sx0 = std::min(s.x0, s.x1);
        const double sx1 = std::max(s.x0, s.x1);
        const double sy0 = std::min(s.y0, s.y1);
        const double sy1 = std::max(s.y0, s.y1);
        if (sx0 - 0.2 <= x && x <= sx1 + 0.2
            && sy0 - 0.2 <= y1 && sy1 + 0.2 >= y0
            && !(sy0 == sy1 && std::abs(sy0 - y_pin) < 1e-6)) {
            return false;
        }
    }
    (void)seg_pad;
    return true;
}

bool cell_free_point(double x, double y,
                     const std::vector<Box4>& boxes,
                     const std::vector<Seg2>& segs, double seg_pad) {
    for (const Box4& b : boxes) {
        if (b.x0 + 1e-6 < x && x < b.x1 - 1e-6
            && b.y0 + 1e-6 < y && y < b.y1 - 1e-6) {
            return false;
        }
    }
    for (const Seg2& s : segs) {
        const double sx0 = std::min(s.x0, s.x1);
        const double sx1 = std::max(s.x0, s.x1);
        const double sy0 = std::min(s.y0, s.y1);
        const double sy1 = std::max(s.y0, s.y1);
        if (sx0 - seg_pad <= x && x <= sx1 + seg_pad
            && sy0 - seg_pad <= y && y <= sy1 + seg_pad) {
            return false;
        }
    }
    return true;
}

}  // namespace schgen
