#pragma once
#include "schgen/seat.hpp"
#include <cmath>
#include <stdexcept>

namespace schgen::floorplan_detail {
// Necessary AABB translation domain for a maximum rectangle gap. Corners may
// still violate Euclidean distance; this is a search filter, not acceptance.
// search_guard is the existing occupancy cell in production. It protects
// closed grid boundaries from cancellation; it does not relax the final gate.
inline Box4 near_translation_domain(const Box4& moving,const Box4& fixed,double distance,double search_guard) {
    const auto valid=[](const Box4& b){return std::isfinite(b.x0)&&std::isfinite(b.y0)&&
        std::isfinite(b.x1)&&std::isfinite(b.y1)&&b.x0<=b.x1&&b.y0<=b.y1;};
    if(!valid(moving)||!valid(fixed)||!std::isfinite(distance)||distance<0||!std::isfinite(search_guard)||search_guard<0)
        throw std::invalid_argument("near translation domain requires finite ordered geometry and nonnegative distance");
    const double reach=distance+search_guard;
    const Box4 result{fixed.x0-reach-moving.x1,fixed.y0-reach-moving.y1,
                      fixed.x1+reach-moving.x0,fixed.y1+reach-moving.y0};
    if(!valid(result))throw std::overflow_error("near translation domain is not finite");
    return result;
}
}
