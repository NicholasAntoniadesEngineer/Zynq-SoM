#include "schgen/pcb_owned_groups.hpp"
#include "schgen/placement_precision.hpp"
#include <algorithm>
#include <cmath>
#include <tuple>

namespace schgen {
namespace {
void demand(bool value, const char* message) {
    if (!value) throw std::invalid_argument(message);
}
bool finite_box(const Box4& b) {
    return std::isfinite(b.x0)&&std::isfinite(b.y0)&&std::isfinite(b.x1)&&
        std::isfinite(b.y1)&&b.x0<=b.x1&&b.y0<=b.y1;
}
Box4 shifted(Box4 b, double x, double y) {
    b.x0+=x;b.x1+=x;b.y0+=y;b.y1+=y;return b;
}
double gap(const Box4& a,const Box4& b) {
    return std::hypot(std::max({0.,a.x0-b.x1,b.x0-a.x1}),
                      std::max({0.,a.y0-b.y1,b.y0-a.y1}));
}
bool collision(const Box4& a,const Box4& b,double clearance) {
    return a.x0 < b.x1+clearance && b.x0 < a.x1+clearance &&
           a.y0 < b.y1+clearance && b.y0 < a.y1+clearance;
}
struct Geometry {
    Box4 occupied;
    std::map<std::string,Box4> pads;
    bool thru=false;
};
}
OwnedGroupResult construct_owned_group_candidates(const PcbCheckModel& original,
    const std::vector<OwnedCapPlacement>& input,const OwnedGroupOptions& options) {
    OwnedGroupResult result;
    if (!options.compact || input.empty()) return result;
    try {
        demand(std::isfinite(options.clearance)&&options.clearance>=0,"invalid clearance");
        demand(original.insts.size()<=256&&input.size()<=64,"owned-group search bound exceeded");
        demand(original.copper.empty()&&!original.escape_plan&&!original.som_core,
            "owned grouping requires a local pre-routing zone");
        const Box4 bounds{original.origin_x,original.origin_y,
            original.origin_x+original.board_w,original.origin_y+original.board_h};
        demand(finite_box(bounds)&&original.board_w>0&&original.board_h>0,"invalid zone extent");
        std::map<std::string,std::size_t> indices;
        std::vector<Geometry> geometry;
        const PcbCheckInput prepared(original);
        for(std::size_t i=0;i<original.insts.size();++i) {
            const auto& p=original.insts[i];
            demand(!p.ref.empty()&&indices.emplace(p.ref,i).second,"duplicate/empty reference");
            demand(p.mod&&std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.rotation),"invalid pose/footprint");
            demand(p.side=="top"||p.side=="bottom","invalid side");
            auto court=prepared.courtyard_at(i);
            const auto pads=prepared.pad_bbox_at(i);
            demand(finite_box(court)&&finite_box(pads),"invalid occupied geometry");
            court={std::min(court.x0,pads.x0),std::min(court.y0,pads.y0),
                   std::max(court.x1,pads.x1),std::max(court.y1,pads.y1)};
            geometry.push_back({shifted(court,-p.x,-p.y),{},has_thru_pads_from_text(p.mod->bytes)});
            for(const auto& [pin,b]:prepared.geometry_at(i).pad_boxes) {
                demand(finite_box(b),"invalid pad geometry");
                geometry.back().pads.emplace(pin,shifted(b,-p.x,-p.y));
            }
        }
        auto rows=input;
        std::sort(rows.begin(),rows.end(),[](const auto& a,const auto& b){
            return std::tie(a.owner,a.owner_pin,a.cap)<std::tie(b.owner,b.owner_pin,b.cap);
        });
        std::set<std::string> caps,owners;
        for(const auto& r:rows) {
            demand(indices.count(r.owner)&&indices.count(r.cap)&&r.owner!=r.cap,"missing/invalid ownership reference");
            demand(caps.insert(r.cap).second,"duplicate capacitor ownership");owners.insert(r.owner);
            demand(r.role==OwnedCapRole::Bypass||r.role==OwnedCapRole::OutputBulk,"unknown ownership role");
            demand(!r.rail.empty()&&!r.return_net.empty()&&r.rail!=r.return_net&&r.cap_pin!=r.return_pin,"invalid supply/return declaration");
            const auto validate=[&](const std::string& ref,const std::string& pin,const std::string& net) {
                auto i=indices.at(ref);const auto& p=original.insts[i];
                auto n=p.pad_nets.find(pin);auto id=original.net_numbers.find(net);
                demand(n!=p.pad_nets.end()&&id!=original.net_numbers.end()&&id->second>0&&
                    n->second==std::make_pair(id->second,net),"owned pin/net identity mismatch");
                demand(geometry[i].pads.count(pin),"missing owned physical pad");
            };
            validate(r.owner,r.owner_pin,r.rail);validate(r.cap,r.cap_pin,r.rail);
            validate(r.cap,r.return_pin,r.return_net);
            demand(original.net_numbers.at(r.rail)!=original.net_numbers.at(r.return_net),"aliased supply/return net ids");
        }
        for(const auto& c:caps)demand(!owners.count(c),"capacitor is also an owner");
        for(const auto& c:options.movable_caps)demand(caps.count(c),"movement permission for unowned member");
        for(const auto& f:options.fixed_refs)demand(indices.count(f),"unknown fixed reference");
        for(const auto& f:options.top_refs)
            demand(indices.count(f)&&original.insts[indices.at(f)].side=="top","required top access violated");
        const auto occupied=[&](const PcbCheckModel& m,std::size_t i) {
            return shifted(geometry[i].occupied,m.insts[i].x,m.insts[i].y);
        };
        const auto distance=[&](const PcbCheckModel& m,const OwnedCapPlacement& r) {
            auto a=indices.at(r.owner),b=indices.at(r.cap);
            return gap(shifted(geometry[a].pads.at(r.owner_pin),m.insts[a].x,m.insts[a].y),
                       shifted(geometry[b].pads.at(r.cap_pin),m.insts[b].x,m.insts[b].y));
        };
        const auto valid_pose=[&](const PcbCheckModel& m,std::size_t i) {
            const auto a=occupied(m,i);
            if(!finite_box(a)||a.x0<bounds.x0||a.y0<bounds.y0||a.x1>bounds.x1||a.y1>bounds.y1)return false;
            for(std::size_t j=0;j<m.insts.size();++j) if(j!=i &&
                (m.insts[i].side==m.insts[j].side||geometry[i].thru||geometry[j].thru))
                if(collision(a,occupied(m,j),options.clearance))return false;
            return true;
        };
        // Opposite iteration orders give bounded alternatives for shared owners.
        // They do not replace any pre-existing packing alternative.
        for(int order=0;order<2;++order) {
            auto sequence=rows;if(order)std::reverse(sequence.begin(),sequence.end());
            PcbCheckModel model=original;
            for(const auto& r:sequence) {
                if(r.role==OwnedCapRole::OutputBulk||!options.movable_caps.count(r.cap)||options.fixed_refs.count(r.cap))continue;
                const auto i=indices.at(r.cap),o=indices.at(r.owner);
                const auto local=geometry[i].occupied;
                const auto pin=geometry[i].pads.at(r.cap_pin);
                const auto owner=shifted(geometry[o].pads.at(r.owner_pin),model.insts[o].x,model.insts[o].y);
                const double tx=owner.x0+(owner.x1-owner.x0)/2-(pin.x0+(pin.x1-pin.x0)/2);
                const double ty=owner.y0+(owner.y1-owner.y0)/2-(pin.y0+(pin.y1-pin.y0)/2);
                std::set<std::pair<double,double>> trials;
                const auto add=[&](double x,double y) {
                    if(!std::isfinite(x)||!std::isfinite(y))return;
                    x=placement_member_pose_precision4dp(x,&result.quantization);
                    y=placement_member_pose_precision4dp(y,&result.quantization);
                    trials.emplace(x,y);
                };
                add(tx,ty);
                // Contact-line trials use actual occupied boundaries, not a
                // fabricated proximity radius or a nearest-owner assignment.
                for(std::size_t j=0;j<model.insts.size();++j) if(j!=i) {
                    const auto b=occupied(model,j);
                    const double xs[]={b.x0-options.clearance-local.x1,b.x1+options.clearance-local.x0};
                    const double ys[]={b.y0-options.clearance-local.y1,b.y1+options.clearance-local.y0};
                    for(double x:xs)for(double y:{ty,b.y0-local.y0,b.y1-local.y1})add(x,y);
                    for(double y:ys)for(double x:{tx,b.x0-local.x0,b.x1-local.x1})add(x,y);
                }
                const auto before=distance(model,r);double best=before;
                auto best_pose=std::make_pair(model.insts[i].x,model.insts[i].y);
                std::vector<std::tuple<double,double,double>> ranked;
                for(const auto& [x,y]:trials)ranked.emplace_back(gap(owner,shifted(pin,x,y)),x,y);
                std::sort(ranked.begin(),ranked.end());
                std::size_t attempted=0;
                for(const auto& [d,x,y]:ranked) {
                    if(!(d<best)||attempted++==256)break;
                    model.insts[i].x=x;model.insts[i].y=y;
                    if(valid_pose(model,i)){best=d;best_pose={x,y};break;}
                }
                model.insts[i].x=best_pose.first;model.insts[i].y=best_pose.second;
            }
            bool improved=false,valid=true;
            OwnedGroupCandidate candidate;candidate.model=model;
            candidate.tag=order?"owned-pins-reverse":"owned-pins-forward";
            for(std::size_t i=0;i<model.insts.size();++i)valid&=valid_pose(model,i);
            // Re-prepare the actual rounded poses: pad-bbox/courtyard consumers
            // have their own established precision. A translated cache alone
            // must not certify their final occupancy at a rounding boundary.
            const PcbCheckInput final_geometry(model);
            std::vector<Box4> final_boxes;
            for(std::size_t i=0;i<model.insts.size();++i) {
                const auto c=final_geometry.courtyard_at(i),p=final_geometry.pad_bbox_at(i);
                final_boxes.push_back({std::min(c.x0,p.x0),std::min(c.y0,p.y0),
                                       std::max(c.x1,p.x1),std::max(c.y1,p.y1)});
                const auto a=final_boxes.back();
                valid&=finite_box(a)&&a.x0>=bounds.x0&&a.y0>=bounds.y0&&a.x1<=bounds.x1&&a.y1<=bounds.y1;
                for(std::size_t j=0;j<i;++j)
                    if(model.insts[i].side==model.insts[j].side||geometry[i].thru||geometry[j].thru)
                        valid&=!collision(a,final_boxes[j],options.clearance);
            }
            // Ranking may use translated local boxes, but acceptance and the
            // published quality metrics must use the actual final pad geometry.
            // Its established rounding can differ from a translated cache.
            for(const auto& r:rows) {
                const auto owner=indices.at(r.owner),cap=indices.at(r.cap);
                const double before=gap(prepared.geometry_at(owner).pad_boxes.at(r.owner_pin),
                                        prepared.geometry_at(cap).pad_boxes.at(r.cap_pin));
                const double after=gap(final_geometry.geometry_at(owner).pad_boxes.at(r.owner_pin),
                                       final_geometry.geometry_at(cap).pad_boxes.at(r.cap_pin));
                demand(std::isfinite(after)&&std::isfinite(before),"nonfinite owned distance");
                candidate.owned_pad_gaps[r.cap]=after;
                if(r.role==OwnedCapRole::Bypass){valid&=after<=before;improved|=after<before;}
            }
            const auto same=[&](const auto& prior) {
                for(std::size_t i=0;i<model.insts.size();++i)
                    if(prior.model.insts[i].x!=model.insts[i].x||prior.model.insts[i].y!=model.insts[i].y)return false;
                return true;
            };
            // Keep every fixed/local pose and the incumbent trailing margins;
            // only reduce unused far-edge extent. Never translate the group or
            // increase zone size to manufacture a proximity improvement.
            double old_x=bounds.x0,old_y=bounds.y0,new_x=bounds.x0,new_y=bounds.y0;
            for(std::size_t i=0;i<model.insts.size();++i) {
                const auto old=occupied(original,i);
                old_x=std::max(old_x,old.x1);old_y=std::max(old_y,old.y1);
                new_x=std::max(new_x,final_boxes[i].x1);new_y=std::max(new_y,final_boxes[i].y1);
            }
            candidate.model.board_w=std::min(original.board_w,new_x-bounds.x0+std::max(0.,bounds.x1-old_x));
            candidate.model.board_h=std::min(original.board_h,new_y-bounds.y0+std::max(0.,bounds.y1-old_y));
            if(valid&&improved&&std::none_of(result.alternatives.begin(),result.alternatives.end(),same))
                result.alternatives.push_back(std::move(candidate));
        }
        result.diagnostics.push_back("UNVERIFIED qualitative proximity/access; no side or movement permission added");
    } catch(const std::exception& e) {
        result.alternatives.clear();result.diagnostics.push_back(std::string("REJECTED owned-group input: ")+e.what());
    }
    return result;
}
} // namespace schgen
