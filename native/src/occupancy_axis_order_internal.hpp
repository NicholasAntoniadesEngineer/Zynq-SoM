#pragma once
#include <algorithm>
#include <utility>
#include <vector>

namespace schgen::occupancy_detail {
// Input coordinates are increasing and absolute-distance costs are unimodal.
// Preserve the exact (cost, coordinate) order, including rounded cost plateaus.
inline void order_axis(std::vector<std::pair<double,double>>& axis) {
    const auto pivot=std::min_element(axis.begin(),axis.end());
    std::reverse(axis.begin(),pivot);
    for(auto first=axis.begin();first!=pivot;) {
        auto last=first+1;
        while(last!=pivot&&last->first==first->first)++last;
        std::reverse(first,last);
        first=last;
    }
    std::inplace_merge(axis.begin(),pivot,axis.end());
}
}
