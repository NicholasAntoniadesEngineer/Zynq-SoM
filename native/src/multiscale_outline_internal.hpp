#pragma once
#include <array>
#include <stdexcept>
#include <utility>

namespace schgen::floorplan_detail {
// Visit returns true only when that point becomes the feasible incumbent.
// No feasibility monotonicity is assumed: failures do not prune smaller points.
// Indices advance within a finite window. Each successful round increases at
// least one index, so there are at most 2*span successful rounds in total.
template<class Visit> void multiscale_outline_indices(int span,Visit&& visit) {
    if(span<0)throw std::invalid_argument("negative outline refinement span");
    int best_i=0,best_j=0;
    visit(0,0);
    int stride=1;
    while(stride<=span/2)stride*=2;
    for(;stride>0;stride/=2) {
        bool improved=true;
        while(improved) {
            const int i=best_i,j=best_j;
            for(const auto& [di,dj]:std::array<std::pair<int,int>,3>{{{stride,0},{0,stride},{stride,stride}}})
                if(di<=span-i&&dj<=span-j&&visit(i+di,j+dj)) {best_i=i+di;best_j=j+dj;}
            improved=best_i!=i||best_j!=j;
        }
    }
}
}
