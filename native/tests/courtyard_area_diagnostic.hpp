#pragma once
#include "schgen/pcb_checks.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace courtyard_diagnostic {
// Exact rectangle union by x slabs, not the area of a bounding box or a sum
// that double-counts overlaps. Diagnostic only: does not include fanout,
// clearance, opposite-face through-hole occupancy or mechanical access.
inline double union_area(const std::vector<schgen::Box4>& boxes) {
    std::vector<double> xs;
    for(const auto& b:boxes) {
        if(!std::isfinite(b.x0)||!std::isfinite(b.y0)||!std::isfinite(b.x1)||!std::isfinite(b.y1)||
           b.x1<b.x0||b.y1<b.y0)throw std::invalid_argument("invalid courtyard area rectangle");
        if(b.x0==b.x1||b.y0==b.y1)continue;
        xs.push_back(b.x0);xs.push_back(b.x1);
    }
    std::sort(xs.begin(),xs.end());xs.erase(std::unique(xs.begin(),xs.end()),xs.end());
    double area=0;
    for(std::size_t i=1;i<xs.size();++i) {
        std::vector<std::pair<double,double>> ys;
        for(const auto& b:boxes)
            if(b.x1>b.x0&&b.x0<xs[i]&&b.x1>xs[i-1]&&b.y1>b.y0)ys.emplace_back(b.y0,b.y1);
        std::sort(ys.begin(),ys.end());
        double length=0, end=0;bool first=true;
        for(const auto& y:ys) {
            if(first||y.first>end){length+=y.second-y.first;end=y.second;first=false;}
            else if(y.second>end){length+=y.second-end;end=y.second;}
        }
        area+=(xs[i]-xs[i-1])*length;
    }
    if(!std::isfinite(area))throw std::overflow_error("courtyard union area overflow");
    return area;
}
} // namespace courtyard_diagnostic
