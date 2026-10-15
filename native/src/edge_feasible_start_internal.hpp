#pragma once
#include <algorithm>
#include <cmath>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>
#include "schgen/occupancy.hpp"

namespace schgen::floorplan_detail {
// Interval for the moving box's along-axis origin, not a displacement. The
// transverse separation is constant. On the moving axis the directional
// clearance changes at the obstacle origin, but nonnegative gaps and positive
// dimensions make the two colliding halves one open interval. Recheck rounded
// poses: algebraically equivalent floating-point expressions can differ.
inline std::optional<std::pair<double,double>> edge_collision_interval(
    const EdgeFanoutBlock& moving,const EdgeFanoutBlock& fixed,
    bool horizontal,double clear) {
    const auto validate=[](const EdgeFanoutBlock& b){
        for(double v:{b.x,b.y,b.w,b.h,b.reach.w,b.reach.e,b.reach.n,b.reach.s,
                      b.inset.w,b.inset.e,b.inset.n,b.inset.s})
            if(!std::isfinite(v))throw std::invalid_argument("edge collision: nonfinite geometry");
        if(b.w<=0||b.h<=0)throw std::invalid_argument("edge collision: nonpositive size");
    };
    validate(moving);validate(fixed);
    if(!std::isfinite(clear)||clear<0)throw std::invalid_argument("edge collision: invalid clearance");
    const double transverse=std::max(clear,fanout_sep(moving.reach,moving.inset,
        fixed.reach,fixed.inset,horizontal?(moving.y<=fixed.y?'S':'N'):(moving.x<=fixed.x?'E':'W')));
    const double a=horizontal?moving.y:moving.x,b=horizontal?fixed.y:fixed.x;
    const double as=horizontal?moving.h:moving.w,bs=horizontal?fixed.h:fixed.w;
    if(a+as+transverse<=b||b+bs+transverse<=a)return std::nullopt;
    const double near=std::max(clear,fanout_sep(moving.reach,moving.inset,fixed.reach,fixed.inset,horizontal?'E':'S'));
    const double far=std::max(clear,fanout_sep(moving.reach,moving.inset,fixed.reach,fixed.inset,horizontal?'W':'N'));
    const double origin=horizontal?fixed.x:fixed.y;
    const double low=origin-(horizontal?moving.w:moving.h)-near;
    const double high=origin+(horizontal?fixed.w:fixed.h)+far;
    if(!std::isfinite(low)||!std::isfinite(high))throw std::invalid_argument("edge collision: interval overflow");
    return std::pair{low,high};
}
// Closed run domain minus OPEN collision intervals: touching a clearance
// boundary is legal. Touching forbidden intervals must not be merged, since
// their common endpoint can be the only legal start. No grid or tolerance is
// introduced here; callers must validate their actual quantized geometry.
inline std::optional<double> nearest_feasible_edge_start(
    double preferred,double low,double high,
    const std::vector<std::pair<double,double>>& forbidden) {
    for(double v:{preferred,low,high})
        if(!std::isfinite(v))throw std::invalid_argument("edge start: nonfinite domain");
    if(low>high)throw std::invalid_argument("edge start: inverted domain");
    std::vector<double> candidates{low,high,std::clamp(preferred,low,high)};
    for(const auto& [a,b]:forbidden){
        if(!std::isfinite(a)||!std::isfinite(b)||a>b)
            throw std::invalid_argument("edge start: invalid collision interval");
        if(a>=low&&a<=high)candidates.push_back(a);
        if(b>=low&&b<=high)candidates.push_back(b);
    }
    std::sort(candidates.begin(),candidates.end());
    candidates.erase(std::unique(candidates.begin(),candidates.end()),candidates.end());
    std::optional<double> below,above;
    for(double point:candidates){
        if(std::any_of(forbidden.begin(),forbidden.end(),[&](const auto& gap){
            return gap.first<point&&point<gap.second;
        }))continue;
        if(point<=preferred)below=point;
        else{above=point;break;}
    }
    if(!below)return above;
    if(!above)return below;
    // The target is bracketed. At most one distance can overflow; that side
    // is necessarily farther. Equal distances deterministically choose low.
    return preferred-*below<=*above-preferred?below:above;
}
}
