#pragma once
#include "schgen/occupancy.hpp"
#include "schgen/legalize.hpp"
#include "schgen/pack_precision.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace schgen::floorplan_detail {
struct EdgeTranslationResult {
    std::vector<EdgeFanoutBlock> blocks;
    std::size_t candidates = 0;
    bool valid = false;
    char moved_edge = '\0';
    double shift = 0;
};

// Bounded repair of edge-run translations only: no reassignment, rotation,
// footprint changes or clearance relaxation. Caller decides whether to opt in.
inline EdgeTranslationResult translate_edge_runs(
    const std::vector<EdgeFanoutBlock>& original,const std::vector<Box4>& keepouts,
    double width,double height,double margin,double clear,QuantizationCounts* counts=nullptr) {
    for(double v:{width,height,margin,clear})
        if(!std::isfinite(v)||v<0)throw std::invalid_argument("edge translation: invalid dimensions");
    if(width==0||height==0)throw std::invalid_argument("edge translation: empty outline");
    for(const auto& b:original) {
        if(b.edge!='N'&&b.edge!='E'&&b.edge!='S'&&b.edge!='W')
            throw std::invalid_argument("edge translation: invalid edge");
        for(double v:{b.x,b.y,b.w,b.h,b.reach.w,b.reach.e,b.reach.n,b.reach.s,
                      b.inset.w,b.inset.e,b.inset.n,b.inset.s})
            if(!std::isfinite(v))throw std::invalid_argument("edge translation: nonfinite geometry");
        if(b.w<0||b.h<0)throw std::invalid_argument("edge translation: negative body");
    }
    for(const auto& box:keepouts) {
        for(double v:{box.x0,box.y0,box.x1,box.y1})
            if(!std::isfinite(v))throw std::invalid_argument("edge translation: nonfinite keepout");
        if(box.x1<box.x0||box.y1<box.y0)throw std::invalid_argument("edge translation: inverted keepout");
    }
    const auto valid=[&](const auto& blocks) {
        std::vector<Box4> boxes;
        for(const auto& b:blocks) {
            const bool horizontal=b.edge=='N'||b.edge=='S';
            const double near=horizontal?b.x:b.y,span=horizontal?b.w:b.h,dim=horizontal?width:height;
            const double low=horizontal?b.reach.w:b.reach.n,high=horizontal?b.reach.e:b.reach.s;
            if(near<margin+low||near+span>dim-margin-high)return false;
            if(!edge_run_margin_ok(b.edge,b.x,b.y,b.w,b.h,width,height,margin,0))return false;
            boxes.push_back({b.x,b.y,b.x+b.w,b.y+b.h});
        }
        for(std::size_t i=0;i<blocks.size();++i)for(std::size_t j=i+1;j<blocks.size();++j) {
            const auto& a=blocks[i];const auto& b=blocks[j];
            if(a.edge!=b.edge)continue;
            const double gx=std::max(clear,fanout_sep(a.reach,a.inset,b.reach,b.inset,a.x<=b.x?'E':'W'));
            const double gy=std::max(clear,fanout_sep(a.reach,a.inset,b.reach,b.inset,a.y<=b.y?'S':'N'));
            if(!boxes_separated(a.x,a.y,a.w,a.h,b.x,b.y,b.w,b.h,gx,gy))return false;
            // Preserve the original run's possibly larger cable/access gaps,
            // including after coordinate quantization. Never shrink a gap.
            const auto& oa=original[i];const auto& ob=original[j];
            if(a.edge=='N'||a.edge=='S') {
                if(oa.x<=ob.x ? b.x-(a.x+a.w)<ob.x-(oa.x+oa.w) : a.x-(b.x+b.w)<oa.x-(ob.x+ob.w))return false;
            } else if(oa.y<=ob.y ? b.y-(a.y+a.h)<ob.y-(oa.y+oa.h) : a.y-(b.y+b.h)<oa.y-(ob.y+ob.h))return false;
        }
        return !rects_overlap_any(boxes,keepouts,1e-6)&&cross_edge_fanout_hold(blocks,clear);
    };
    EdgeTranslationResult result{original};
    if(valid(original)){result.valid=true;return result;}
    for(char edge:{'N','E','S','W'}) {
        bool present=false;for(const auto& b:original)present=present||b.edge==edge;
        if(!present)continue;
        for(double shift:{-.25,.25,-.5,.5,-1.,1.,-2.,2.}) {
            auto candidate=original;
            ++result.candidates;
            for(auto& b:candidate)if(b.edge==edge) {
                auto& coordinate=(edge=='N'||edge=='S')?b.x:b.y;
                coordinate=pack_edge_pose_precision4dp(coordinate+shift,counts);
            }
            if(valid(candidate)) {
                result.blocks=std::move(candidate);result.valid=true;result.moved_edge=edge;result.shift=shift;
                return result;
            }
        }
    }
    return result; // Exact original geometry on failure; actual counts retained.
}
} // namespace schgen::floorplan_detail
