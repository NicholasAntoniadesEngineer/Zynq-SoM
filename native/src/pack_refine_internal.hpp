#pragma once
#include "schgen/pack_refine.hpp"
#include <cstdint>
#include <cstring>
#include <cmath>

namespace schgen::floorplan_detail {
// This is cache eligibility, NOT replacement validation. Unusual inputs still
// execute the original query and retain its validation/failed-prefix behavior.
inline bool cacheable_query_geometry(const SeatShapeCand& c) {
    for (double v:{c.w,c.h,c.reach.w,c.reach.e,c.reach.n,c.reach.s,
                   c.inset.w,c.inset.e,c.inset.n,c.inset.s,
                   c.win_x0,c.win_x1,c.win_y0,c.win_y1})
        if (!std::isfinite(v)) return false;
    if (c.w<=0||c.h<=0||c.mask<=0||c.win_x0>c.win_x1||c.win_y0>c.win_y1) return false;
    for (const auto& p:c.comps) {
        for (double v:{p.reach.w,p.reach.e,p.reach.n,p.reach.s,p.inset.w,p.inset.e,p.inset.n,p.inset.s})
            if (!std::isfinite(v)) return false;
        if (!std::isfinite(p.dx)||!std::isfinite(p.dy)||!std::isfinite(p.w)||!std::isfinite(p.h)
            ||p.w<=0||p.h<=0||p.mask<=0) return false;
    }
    return true;
}
// Exact scalar bits, including signed zero. No rounding or primary-box-only
// equivalence: child reservation order and all query geometry are significant.
inline bool same_query_scalar(double a, double b) {
    std::uint64_t x, y;
    static_assert(sizeof(x)==sizeof(a));
    std::memcpy(&x,&a,sizeof(x)); std::memcpy(&y,&b,sizeof(y));
    return x==y;
}
inline bool same_query_geometry(const SeatShapeCand& a, const SeatShapeCand& b) {
    const auto eq=same_query_scalar;
    const auto halo=[&](const Halo& x,const Halo& y) {
        return eq(x.w,y.w)&&eq(x.e,y.e)&&eq(x.n,y.n)&&eq(x.s,y.s);
    };
    if (!eq(a.w,b.w)||!eq(a.h,b.h)||!halo(a.reach,b.reach)||!halo(a.inset,b.inset)
        ||a.mask!=b.mask||!eq(a.win_x0,b.win_x0)||!eq(a.win_x1,b.win_x1)
        ||!eq(a.win_y0,b.win_y0)||!eq(a.win_y1,b.win_y1)||a.comps.size()!=b.comps.size()) return false;
    for (std::size_t i=0;i<a.comps.size();++i) {
        const auto& x=a.comps[i]; const auto& y=b.comps[i];
        if (!eq(x.dx,y.dx)||!eq(x.dy,y.dy)||!eq(x.w,y.w)||!eq(x.h,y.h)||x.mask!=y.mask
            ||!halo(x.reach,y.reach)||!halo(x.inset,y.inset)) return false;
    }
    return true;
}
// Synchronous read-only search. Caller must supply the dimensions with which
// occupancy was constructed; public adapters retain their resizing semantics.
std::vector<SeatShapeHit> seat_shape_candidates_on_current_board(const Occupancy&,
    double, double, const std::vector<SeatShapeCand>&, double, double, double,
    QuantizationCounts*);
}
