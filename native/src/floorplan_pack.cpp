#include "floorplan_internal.hpp"
#include "native_audit_quantize_internal.hpp"

#include <algorithm>
#include <cmath>
#include <unordered_map>
#include "pack_refine_internal.hpp"
#include "constraint_order_internal.hpp"
#include "edge_translation_internal.hpp"
#include "near_translation_domain_internal.hpp"

namespace schgen::floorplan_detail {
namespace {
template<class Map> const typename Map::mapped_type& get(const Map& map, const typename Map::key_type& key) {
    const auto it = map.find(key);
    static const typename Map::mapped_type empty{};
    return it == map.end() ? empty : it->second;
}
char edge_char(const std::string& edge) { return edge.empty() ? '\0' : edge.front(); }
void pose(FloorplanBlock& b, const Pose& p) { b.x=p.x; b.y=p.y; b.w=p.w; b.h=p.h; }
template<class Map> auto save_entry(const Map& map,const typename Map::key_type& key) {
    const auto it=map.find(key);
    return it==map.end() ? std::optional<typename Map::mapped_type>{}
                        : std::optional<typename Map::mapped_type>{it->second};
}
template<class Map> void restore_entry(Map& map,const typename Map::key_type& key,
                                      const std::optional<typename Map::mapped_type>& saved) {
    if(saved)map.insert_or_assign(key,*saved);
    else map.erase(key);
}
}  // namespace

PackAnchorIn Engine::anchor_row(const FloorplanBlock& b,
                                const std::map<std::string,FloorplanPoint>& centers) const {
    PackAnchorIn a;
    for (const auto& [name,face]:in.project.module_face_anchors) if (name==b.name && (offset.first || offset.second)) {
        a.face_override=true; a.face=edge_char(face); break;
    }
    a.som_x=plan.som_x; a.som_y=plan.som_y; a.som_w=plan.som.w; a.som_h=plan.som.h;
    a.som_halo=som_halo; a.block_w=b.w; a.block_h=b.h;
    const auto eb=std::find_if(plan.edge_blocks.begin(),plan.edge_blocks.end(),[&](const auto& e){return b.zone=="@"+e.name;});
    if (eb!=plan.edge_blocks.end()) {
        a.zone_is_at_edge=true; a.zone_ax=eb->cx(); a.zone_ay=eb->cy();
        a.eb_x=eb->x; a.eb_y=eb->y; a.eb_w=eb->w; a.eb_h=eb->h;
        a.eb_cx=eb->cx(); a.eb_cy=eb->cy(); a.edge=edge_char(eb->edge);
    } else {
        const char z=b.zone=="N" || b.zone=="E" || b.zone=="S" || b.zone=="W" ? b.zone.front() : 'E';
        std::tie(a.zone_ax,a.zone_ay)=zone_anchor(z,plan.som_x,plan.som_y,plan.som.w,plan.som.h,plan.board_w,plan.board_h);
        // SoM connectors are not edge blocks. Honour their explicit near
        // anchors using the actual connector rectangle, not the E fallback.
        for(const auto& jack:plan.som.js)
            if(!jack.ref.empty()&&jack.ref.front()=='J'&&b.zone=="@som_j"+jack.ref.substr(1)) {
                a.zone_ax=plan.som_x+jack.x+jack.w/2;
                a.zone_ay=plan.som_y+jack.y+jack.h/2;
                break;
            }
    }
    if (b.pull) {
        a.exclusive=b.pull->exclusive; a.inboard=b.pull->face=="inboard"; a.pull_weight=b.pull->weight;
        const auto pt=centers.find(b.pull->to);
        if (!a.exclusive && pt!=centers.end()) { a.has_soft_pull=true; a.pull_x=pt->second.first; a.pull_y=pt->second.second; }
    }
    a.zone_w=anchor_zone_weight; a.som_w_scale=anchor_som_weight; a.som_pull=get(som_pull,b.name); a.aff_pow=anchor_affinity_power;
    a.som_cx=plan.som_x+plan.som.w/2; a.som_cy=plan.som_y+plan.som.h/2;
    for (const auto& [name,weight]:get(affinity,b.name)) {
        const auto pt=centers.find(name);
        if (pt!=centers.end()) a.affinity.emplace_back(pt->second.first,pt->second.second,weight);
    }
    return a;
}

bool Engine::attempt_pack(bool compact) {
    return run_floorplan_experiment_attempt(in.experiment.get(), plan.punch_free,
        [&] {
            if(in.experiment && in.experiment->interior_order) {
                validate_floorplan_experiment(*in.experiment);
                const int saved_order=compact_order;
                const bool recovery=in.compact_search&&in.experiment->failed_first_retry;
                const bool transactional=recovery||in.experiment->reseat_pose_limits.has_value()||in.experiment->joint_separation_states.has_value();
                const auto start=transactional?std::optional{plan}:std::nullopt;
                const auto offers=transactional?std::optional{side_offers}:std::nullopt;
                const auto restore=[&] {
                    auto accounting=std::move(plan.accounting);
                    plan=*start;plan.accounting=std::move(accounting);side_offers=*offers;
                };
                compact_order=*in.experiment->interior_order;
                try {
                    std::string failed;
                    bool selected_pose=false;
                    bool ok=attempt_pack_impl(compact,nullptr,{},recovery?&failed:nullptr,0,&selected_pose);
                    const auto continuations=in.experiment->reseat_pose_limits?
                        in.experiment->reseat_pose_limits->continuations:0;
                    const bool reuse=in.experiment->reseat_pose_limits&&in.experiment->reseat_pose_limits->reuse_continuation;
                    const ContinuationKey key{plan.board_w,plan.board_h,plan.punch_free,compact,compact_order};
                    const std::size_t preferred=reuse&&continuation_hint&&continuation_hint->first==key&&
                        continuation_hint->second<=continuations?continuation_hint->second:0;
                    const bool can_replay=selected_pose;
                    std::optional<std::size_t> exhausted;
                    for(std::size_t replay=0;!ok&&can_replay&&replay<continuations;++replay){
                        // Permute, never prune: preferred, then the remaining
                        // ascending ordinals. A stale high hint may be empty;
                        // lower ordinals must still run before exhaustion.
                        const auto branch=preferred>1?(replay==0?preferred:
                            (replay<preferred?replay:replay+1)):replay+1;
                        if(exhausted&&branch>=*exhausted)break;
                        restore();
                        if(preferred>1&&replay==0)fallback("interior_reseat_pose_hint");
                        fallback("interior_reseat_pose_resume");
                        ok=attempt_pack_impl(compact,nullptr,{},nullptr,branch,&selected_pose);
                        if(!selected_pose)exhausted=branch;
                        if(ok&&reuse)continuation_hint=std::make_pair(key,branch);
                    }
                    if(!ok&&recovery&&!failed.empty()) {
                        restore();
                        fallback("interior_failed_first_retry");
                        ok=attempt_pack_impl(compact,nullptr,failed);
                        if(ok)plan.composition.push_back("failure-directed order: "+failed+" first");
                    }
                    if(!ok&&transactional)restore();
                    compact_order=saved_order;
                    return ok;
                } catch(...) {if(transactional)restore();compact_order=saved_order;throw;}
            }
            if (!in.compact_search) return attempt_pack_impl(compact);
            const auto start=plan;
            const auto offers=side_offers;
            // Each alternative starts identically. The optional constraint-first
            // candidate retains every legacy order as a fallback, never pruning.
            const bool constraint_first = in.experiment && in.experiment->compact_constraint_first;
            for (int order : {3,0,1,2}) {
                if (order == 3 && !constraint_first) continue;
                auto accounting=std::move(plan.accounting);
                plan=start; plan.accounting=std::move(accounting);
                side_offers=offers; compact_order=order;
                try {
                    bool order_independent_failure=false;
                    if (attempt_pack_impl(compact,&order_independent_failure)) {compact_order=0;return true;}
                    // Interior ordering cannot change edge placement, its
                    // bounded translations or edge/SoM feasibility. All orders
                    // start from the same snapshot; do not repeat that failure.
                    if(order_independent_failure)break;
                } catch (...) {
                    compact_order=0;
                    auto failed_accounting=std::move(plan.accounting);
                    plan=start;plan.accounting=std::move(failed_accounting);
                    side_offers=offers;
                    throw;
                }
            }
            compact_order=0;
            auto accounting=std::move(plan.accounting);
            plan=start;plan.accounting=std::move(accounting);side_offers=offers;
            return false;
        }, [&](bool packed) {
            return FloorplanAttemptObservation{plan.board_w, plan.board_h, packed,
                                               plan.punch_free, std::nullopt};
        });
}
bool Engine::attempt_pack_impl(bool compact,bool* order_independent_failure,
                              const std::string& promote,std::string* failed_subject,
                              std::size_t first_pose_skip,bool* selected_pose) {
    if(selected_pose)*selected_pose=false;
    if(order_independent_failure)*order_independent_failure=true;
    // Borrow only for this synchronous invocation; never attach a sink to
    // occupancy geometry or candidate copies. Rejected trials remain counted.
    auto* const counts=&plan.accounting.quantization_engagements;
    const double bw=plan.board_w,bh=plan.board_h;
    const auto rejected=[&](const std::string& stage,const std::string& subject,bool phase_compact,
                            const std::vector<std::string>& diagnostics=std::vector<std::string>{}) {
        if(in.experiment&&in.experiment->stage_rejected)
            in.experiment->stage_rejected({bw,bh,stage,subject,phase_compact,plan.punch_free,compact_order,diagnostics});
    };
    const int policy=plan.punch_free ? 1:0;
    const auto& shapes=shape_sets[policy];
    const auto& co=components[policy];
    plan.spilled.clear();
    std::vector<PackEdgeBlock> edge_rows;
    for (auto& b:plan.edge_blocks) {
        std::tie(b.w,b.h)=zbox.at(b.name); b.area=block_area(b.w,b.h, counts);
        PackEdgeBlock row;
        row.name=b.name; row.w=b.w; row.h=b.h;
        if (b.order_hint) row.order_hint=*b.order_hint;
        row.reach=b.fanout_reach; row.inset=b.fanout_inset;
        for (const auto& [j,n]:b.j_aff) row.j_aff.emplace_back(j,n);
        row.overmold=overmold(b); row.current_edge=b.edge; row.assigned_edge=edge_of.at(b.name);
        edge_rows.push_back(std::move(row));
    }
    std::vector<PackEdgeJack> jacks;
    for (const auto& j:plan.som.js) jacks.push_back({j.ref,plan.som_x+j.x,plan.som_y+j.y});
    const bool initial_feasibility=in.compact_search&&in.experiment&&in.experiment->compact_edge_feasibility;
    const auto initial_keepouts=initial_feasibility?som_keepouts():std::vector<Box4>{};
    const auto packed=pack_edges(edge_rows,jacks,{bw,bh,edge_margin,edge_inset,clear,cable_gap,overmold_gap,affinity_floor,
                                                plan.som_x,plan.som_y,plan.som.w,plan.som.h}, counts,
                                                initial_feasibility?&initial_keepouts:nullptr);
    if(initial_feasibility&&in.experiment->edge_feasibility_completed)
        in.experiment->edge_feasibility_completed(packed.feasibility_runs,packed.feasibility_intervals,packed.feasibility_rejections);
    if(initial_feasibility&&!packed.rejection_reason.empty()&&in.experiment->edge_feasibility_rejected)
        in.experiment->edge_feasibility_rejected(packed.rejected_edge,packed.rejection_reason,
            packed.feasible_start_low,packed.feasible_start_high);
    // A bounded spill can leave blocks unplaced. Never retain their poses or
    // edge labels from an earlier outline, or pass an empty label downstream.
    if (packed.poses.size()!=plan.edge_blocks.size()) return false;
    for (auto& b:plan.edge_blocks) for (const auto& p:packed.poses) if (p.name==b.name) { b.edge=p.edge; b.x=p.x; b.y=p.y; break; }
    plan.spilled=packed.spilled;
    std::vector<std::tuple<char,double,double,double,double>> run_rows;
    std::vector<Box4> edge_boxes;
    std::vector<EdgeFanoutBlock> fanout_rows;
    for (const auto& b:plan.edge_blocks) {
        run_rows.emplace_back(edge_char(b.edge),b.x,b.y,b.w,b.h);
        edge_boxes.push_back({b.x,b.y,b.x+b.w,b.y+b.h});
        fanout_rows.push_back({b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,edge_char(b.edge)});
    }
    if(in.compact_search&&in.experiment&&in.experiment->compact_edge_translation) {
        const auto shifted=translate_edge_runs(fanout_rows,som_keepouts(),bw,bh,edge_margin,clear,counts);
        if(shifted.moved_edge) {
            for(std::size_t i=0;i<plan.edge_blocks.size();++i) {
                auto& b=plan.edge_blocks[i];b.x=shifted.blocks[i].x;b.y=shifted.blocks[i].y;
                run_rows[i]={edge_char(b.edge),b.x,b.y,b.w,b.h};
                edge_boxes[i]={b.x,b.y,b.x+b.w,b.y+b.h};
            }
            fanout_rows=shifted.blocks;
            fallback("edge_run_translation");
        }
        if(in.experiment->edge_translation_completed)
            in.experiment->edge_translation_completed(shifted.candidates,shifted.moved_edge,shifted.shift);
        // Opt-in search is fail-closed, including same-edge clearance checks.
        if(!shifted.valid)return false;
    }
    checked_quantization_add(plan.accounting.quantization_engagements, "run_overflow_tol");
    if (!edge_runs_margin_ok(run_rows,bw,bh,edge_margin,native_run_overflow_tol())) return false;
    const auto som_rects=som_keepouts();
    if (rects_overlap_any(edge_boxes,som_rects,1e-6) || !cross_edge_fanout_hold(fanout_rows,clear)) return false;
    if(order_independent_failure)*order_independent_failure=false;
    const int som_mask=plan.punch_free ? occ_top:occ_punch, edge_mask=som_mask;
    const Pose som_occ{plan.som_x-som_pad,plan.som_y-som_pad,plan.som.w+2*som_pad,plan.som.h+2*som_pad};
    std::vector<Comp> som_comps;
    if (plan.punch_free) som_comps=som_components(som_occ.x,som_occ.y,plan.dec_radius,
        som_decoupling_cells(plan.som_x,plan.som_y,plan.som.w,plan.som.h,plan.dec_count,dec_inset,counts),
        {som_rects.begin()+1,som_rects.end()},occ_bottom,occ_punch,counts);
    std::map<std::string,std::vector<Comp>> edge_comps;
    for (const auto& b:plan.edge_blocks) if (plan.punch_free)
        edge_comps[b.name]=edge_components(edge_char(b.edge),b.x,b.y,bw,bh,occ_punch,get(co,{b.name,b.shape_idx}),counts);
    const auto [reach_bound,envelope]=spatial_bounds_accounted(far_ceil,max_reach,clear,in.place_clear,cable_gap,2.0,
        counts);
    if (std::max(clear,2*reach_bound)>envelope+1e-9) throw std::logic_error("floorplan: spatial interaction envelope underbounds fan-out reach");
    Occupancy occ(bw,bh,clear,envelope,reach_bound,occ_step,frontier_half);
    occ.add(som_occ.x,som_occ.y,som_occ.w,som_occ.h,{},{},som_mask,som_comps,counts);
    const auto corners=legalize_mh_corners(bw,bh,mh_corner);
    for (const auto& c:corners) occ.add(c.x0,c.y0,c.x1-c.x0,c.y1-c.y0,{},{},occ_punch,{},counts);
    std::map<std::string,FloorplanPoint> centers;
    for (const auto& b:plan.edge_blocks) {
        occ.add(b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,edge_mask,get(edge_comps,b.name),counts);
        centers[b.name]={b.cx(),b.cy()};
    }
    std::vector<std::string> names;
    std::vector<int> tiers;
    std::vector<double> connections,areas;
    for (const auto& b:plan.interior_blocks) {
        bool face=false;
        for (const auto& [n,f]:in.project.module_face_anchors) { (void)f; if (b.name==n) face=true; }
        names.push_back(b.name); tiers.push_back(face ? 0 : (b.pull && b.pull->exclusive ? 1:2));
        std::vector<double> weights;
        for (const auto& [n,w]:get(affinity,b.name)) { (void)n; weights.push_back(w); }
        connections.push_back(pack_conn_weight(weights,get(som_pull,b.name)));
        const auto wh=zbox.at(b.name); areas.push_back(wh.first*wh.second);
    }
    std::vector<FloorplanBlock*> order,placed;
    for (int i:pack_interior_order(names,tiers,connections,areas)) order.push_back(&plan.interior_blocks[i]);
    const bool alternate_order=in.compact_search || (in.experiment && in.experiment->interior_order);
    if (alternate_order && compact_order == 3) {
        sort_constraint_first(order, in.compose.index, zbox);
    } else if (alternate_order && compact_order) {
        // Stable ties retain the established connectivity/priority ordering.
        std::stable_sort(order.begin(),order.end(),[&](const auto* a,const auto* b) {
            if (compact_order==2) {
                auto count=[&](const auto* block) {
                    const auto it=shapes.find(block->name);
                    return it==shapes.end() ? std::size_t{1}:it->second.size();
                };
                if (count(a)!=count(b)) return count(a)<count(b);
            }
            const auto awh=zbox.at(a->name),bwh=zbox.at(b->name);
            return awh.first*awh.second>bwh.first*bwh.second;
        });
    }
    if(!promote.empty()) {
        const auto found=std::find_if(order.begin(),order.end(),[&](const auto* b){return b->name==promote;});
        if(found!=order.end())std::rotate(order.begin(),found,found+1);
    }
    std::map<std::string,std::vector<Comp>> chosen;
    auto occ_put=[&](const FloorplanBlock& b){occ.add(b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,side_mask(b.side),get(chosen,b.name),counts);};
    auto occ_pull=[&](const FloorplanBlock& b){occ.remove(b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,side_mask(b.side),get(chosen,b.name),counts);};
    const auto selected_hull=[&](const std::string& name,int shape_index)->std::optional<Box4> {
        if(shape_index) {
            const auto m=in.compose.shape_metrics.find({name,shape_index});
            return m==in.compose.shape_metrics.end()?std::nullopt:pad_union_hull(m->second.pad_union);
        }
        const auto m=in.compose.metrics.find(name);
        return m==in.compose.metrics.end()?std::nullopt:pad_union_hull(m->second.pad_union);
    };
    const auto near_domain=[&](const FloorplanBlock& b,int shape_index,auto& win) {
        // Hard connector proximity constrains every seating strategy, not
        // only those whose preferred anchor explicitly names that connector.
        for(const auto& term:in.compose.index.hard) {
            if(term.kind!="near_max"||!term.bound)continue;
            // Pad-to-pad distance is symmetric even though authored terms
            // retain a subject/target direction for diagnostics.
            const auto other=term.subject==b.name?term.target():
                (term.target()==b.name?term.subject:std::string{});
            if(other.empty())continue;
            const auto hull=selected_hull(b.name,shape_index);if(!hull)continue;
            std::optional<Box4> target;
            for(const auto& jack:plan.som.js) {
                if(jack.ref.empty()||jack.ref.front()!='J'||other!="som_j"+jack.ref.substr(1))continue;
                target=Box4{plan.som_x+jack.x,plan.som_y+jack.y,
                    plan.som_x+jack.x+jack.w,plan.som_y+jack.y+jack.h};
                break;
            }
            // Edge blocks have their final poses before interior seating.
            // Use their actual selected pad geometry, not the body envelope.
            if(!target)for(const auto& edge:plan.edge_blocks)if(edge.name==other) {
                if(const auto local=selected_hull(edge.name,edge.shape_idx))
                    target=Box4{edge.x+local->x0,edge.y+local->y0,
                                edge.x+local->x1,edge.y+local->y1};
                break;
            }
            if(target) {
                const auto domain=near_translation_domain(*hull,*target,*term.bound,occ_step);
                std::get<0>(win)=std::max(std::get<0>(win),domain.x0);
                std::get<1>(win)=std::min(std::get<1>(win),domain.x1);
                std::get<2>(win)=std::max(std::get<2>(win),domain.y0);
                std::get<3>(win)=std::min(std::get<3>(win),domain.y1);
            }
        }
    };
    auto near=[&](const FloorplanBlock& b,int shape_index,FloorplanPoint a,double w,double h,Halo reach,Halo inset,int mask,const std::vector<Comp>& comps,
                  const FloorplanBlock* evicted) {
        std::tuple<double,double,double,double> win{-bw,2*bw,-bh,2*bh};
        if (evicted) win=evict_window(evicted->x,evicted->y,evicted->w,evicted->h,evicted->fanout_reach,evicted->fanout_inset,
                                     get(chosen,evicted->name),w,h,reach,inset,comps,clear);
        near_domain(b,shape_index,win);
        return occ.place_near(a.first,a.second,w,h,reach,inset,mask,comps,std::get<0>(win),std::get<1>(win),std::get<2>(win),std::get<3>(win),counts);
    };
    auto seat=[&](FloorplanBlock& b,FloorplanPoint a,const FloorplanBlock* evicted) {
        const auto variants=shapes.find(b.name);
        if (variants==shapes.end()) {
            const auto& cc=get(co,{b.name,0});
            const auto p=near(b,0,a,b.w,b.h,b.fanout_reach,b.fanout_inset,occ_top,cc,evicted);
            if (!p) return false;
            b.shape_idx=0; b.side="top"; chosen[b.name]=cc; pose(b,*p); return true;
        }
        std::vector<SeatShapeCand> cands;
        const auto restricted=owned_shape_choices.find(b.name);
        for (std::size_t k=0;k<variants->second.size();++k) {
            if(restricted!=owned_shape_choices.end()&&static_cast<int>(k)!=restricted->second)continue;
            const auto& s=variants->second[k];
            auto win=std::make_tuple(-bw,2*bw,-bh,2*bh);
            if (evicted) win=evict_window(evicted->x,evicted->y,evicted->w,evicted->h,evicted->fanout_reach,evicted->fanout_inset,
                get(chosen,evicted->name),s.w,s.h,s.reach,s.inset,s.comps,clear);
            near_domain(b,static_cast<int>(k),win);
            cands.push_back({static_cast<int>(k),s.w,s.h,s.reach,s.inset,side_mask(s.side),s.side,s.comps,
                std::get<0>(win),std::get<1>(win),std::get<2>(win),std::get<3>(win)});
        }
        auto hits=in.compact_search
            ? seat_shape_candidates_on_current_board(occ,a.first,a.second,cands,bw,bh,clear,counts)
            : seat_shape_sides_on_current_board(occ,a.first,a.second,cands,bw,bh,clear,counts);
        if (hits.empty()) return false;
        std::sort(hits.begin(),hits.end(),[](const auto& a,const auto& b){return std::tie(a.dist_key,a.index)<std::tie(b.dist_key,b.index);});
        auto best=hits.front();
        if (hits.size()==1) side_offers[b.name]={best.side,best.side,best.index,std::nullopt,std::nullopt};
        else {
            // Membership is invariant across this block's shape trials. Only
            // b's pose/shape changes; estimate consumes these borrowed pointers
            // synchronously. Prepare once, not once per competing shape.
            std::vector<const FloorplanBlock*> partial;
            partial.reserve(plan.edge_blocks.size()+placed.size()+1);
            for (const auto& e:plan.edge_blocks) partial.push_back(&e);
            partial.insert(partial.end(),placed.begin(),placed.end());
            partial.push_back(&b);
            auto judge=[&](const SeatShapeHit& h) {
                const auto saved=b;
                pose(b,{h.x,h.y,h.w,h.h}); b.shape_idx=h.index; b.side=h.side;
                double value;
                try { value=estimate(partial,b.name); } catch (...) { b=saved; throw; }
                b=saved; return value;
            };
            const double incumbent=judge(hits[0]),challenger=judge(hits[1]);
            const auto quality=in.owned_shape_quality.lower_bound({b.name,0});
            const bool has_quality=in.compact_search && quality!=in.owned_shape_quality.end() &&
                quality->first.first==b.name;
            std::vector<double> evaluated;
            if (has_quality) { evaluated.reserve(hits.size()); evaluated={incumbent,challenger}; }
            if (pick_sided_challenger(incumbent,challenger,1e-6)) best=hits[1];
            double selected=best.index==hits[1].index ? challenger:incumbent;
            if (in.compact_search) for (std::size_t i=2;i<hits.size();++i) {
                const double value=judge(hits[i]);
                if (has_quality) evaluated.push_back(value);
                if (pick_sided_challenger(selected,value,1e-6)) {best=hits[i]; selected=value;}
            }
            if (has_quality) {
                // Preserve the primary estimator decision, then compare the
                // complete exact-rank bucket. Pareto dominance is NOT a sort
                // comparator and a running incumbent can discard a survivor.
                const OwnedShapeTieRank primary{best.index,true,best.w,best.h,
                                               selected,best.dist_key,best.side};
                std::vector<OwnedShapeTieRank> bucket;
                for (std::size_t i=0;i<hits.size();++i) {
                    const auto& h=hits[i];
                    OwnedShapeTieRank rank{h.index,true,h.w,h.h,evaluated.at(i),h.dist_key,h.side};
                    if (owned_shape_same_primary_rank(rank,primary)) bucket.push_back(rank);
                }
                const auto winner=owned_shape_select_tied_bucket(true,in.owned_shape_quality,b.name,bucket);
                if (winner) for (std::size_t i=0;i<hits.size();++i) if (hits[i].index==*winner) {
                    best=hits[i]; selected=evaluated.at(i); break;
                }
                if(in.experiment&&in.experiment->owned_quality_first) {
                    std::vector<OwnedShapeLocatedRank> alternatives;
                    for(std::size_t i=0;i<hits.size();++i){
                        const auto& h=hits[i];
                        alternatives.push_back({{h.index,true,h.w,h.h,evaluated.at(i),h.dist_key,h.side},h.x,h.y});
                    }
                    const int choice=owned_shape_select_same_pose_quality(in.owned_shape_quality,b.name,alternatives,best.index);
                    for(std::size_t i=0;i<hits.size();++i)if(hits[i].index==choice){best=hits[i];selected=evaluated.at(i);break;}
                }
                if(in.experiment&&in.experiment->owned_shape_selection_completed) {
                    std::vector<OwnedShapeTieRank> alternatives;
                    alternatives.reserve(hits.size());
                    for(std::size_t i=0;i<hits.size();++i) {
                        const auto& h=hits[i];
                        alternatives.push_back({h.index,true,h.w,h.h,evaluated.at(i),h.dist_key,h.side});
                    }
                    in.experiment->owned_shape_selection_completed(b.name,alternatives,in.owned_shape_quality,best.index);
                }
            }
            side_offers[b.name]={hits[0].side+"(incumbent)/"+
                (in.compact_search ? "all-shapes":hits[1].side),best.side,best.index,incumbent,
                in.compact_search ? selected:challenger};
            if (in.compact_search && std::all_of(hits.begin(),hits.end(),[&](const auto& h){return h.side==hits[0].side;}))
                side_offers[b.name]={best.side,best.side,best.index,std::nullopt,std::nullopt};
        }
        pose(b,{best.x,best.y,best.w,best.h}); b.shape_idx=best.index; b.side=best.side;
        b.fanout_reach=best.reach; b.fanout_inset=best.inset; b.area=block_area(b.w,b.h, counts); chosen[b.name]=best.comps;
        return true;
    };
    int evict_budget=reseat_evict_budget;
    bool first_recovery=true;
    auto retry=[&](FloorplanBlock& b,FloorplanPoint a) {
        if (evict_budget<1) return false;
        std::vector<std::tuple<double,double,double,double,std::string>> ranks;
        for (const auto* p:placed) ranks.emplace_back(p->x,p->y,p->w,p->h,p->name);
        const auto ranked=reseat_rank(a.first,a.second,ranks);
        const bool alternatives=in.experiment&&in.experiment->reseat_pose_limits.has_value();
        for(int pass=0;pass<(alternatives?2:1);++pass) for (int idx:ranked) {
            auto& e=*placed[idx]; const auto saved_e=e,saved_b=b;
            // A rejected victim trial can change only the incoming block's
            // entries. The displaced block's center is updated only on success;
            // its chosen geometry is never changed by this retry. Preserve
            // absence as well as values, including the rejected side offer.
            const auto saved_chosen=save_entry(chosen,b.name);
            const auto saved_center=save_entry(centers,b.name);
            const auto saved_offer=save_entry(side_offers,b.name);
            FloorplanPoseRetryObservation observation;
            if(pass){
                observation.incoming=b.name;observation.displaced=e.name;
                fallback("interior_reseat_pose_search");
            }
            occ_pull(e);
            bool ok=seat(b,a,&e);
            const bool incoming_seated=ok;
            if (ok && !pass) {
                occ_put(b); centers[b.name]={b.cx(),b.cy()};
                const auto anchor=pack_anchor(anchor_row(e,centers));
                const auto p=near(e,e.shape_idx,anchor,e.w,e.h,e.fanout_reach,e.fanout_inset,side_mask(e.side),get(chosen,e.name),nullptr);
                if (!p) { ok=false; occ_pull(b); }
                else { e.x=p->x; e.y=p->y; occ_put(e); centers[e.name]={e.cx(),e.cy()}; }
            }
            else if(ok) {
                const auto first=FloorplanPoint{b.x,b.y};
                auto win=evict_window(e.x,e.y,e.w,e.h,e.fanout_reach,e.fanout_inset,get(chosen,e.name),
                                     b.w,b.h,b.fanout_reach,b.fanout_inset,get(chosen,b.name),clear);
                near_domain(b,b.shape_idx,win);
                const auto limits=*in.experiment->reseat_pose_limits;
                const auto poses=occ.place_near_candidates(a.first,a.second,b.w,b.h,b.fanout_reach,b.fanout_inset,
                    side_mask(b.side),get(chosen,b.name),std::get<0>(win),std::get<1>(win),std::get<2>(win),std::get<3>(win),
                    limits.poses,limits.frontier_nodes,counts);
                observation.generated=poses.poses.size();observation.frontier_nodes=poses.frontier_nodes;
                observation.budget_exhausted=poses.budget_exhausted;
                observation.result_capped=!poses.search_complete&&!poses.budget_exhausted;
                if(observation.budget_exhausted)fallback("interior_reseat_pose_budget");
                if(observation.result_capped)fallback("interior_reseat_pose_cap");
                ok=false;
                for(const auto& p:poses.poses) {
                    if(p.x==first.first&&p.y==first.second)continue; // ordinary pass already tried it
                    fallback("interior_reseat_pose_trial");++observation.attempted;
                    b.x=p.x;b.y=p.y;occ_put(b);centers[b.name]={b.cx(),b.cy()};
                    const auto anchor=pack_anchor(anchor_row(e,centers));
                    const auto next=near(e,e.shape_idx,anchor,e.w,e.h,e.fanout_reach,e.fanout_inset,
                                         side_mask(e.side),get(chosen,e.name),nullptr);
                    if(!next){occ_pull(b);continue;}
                    if(first_recovery&&first_pose_skip){
                        --first_pose_skip;++observation.skipped;
                        fallback("interior_reseat_pose_skip");
                        occ_pull(b);continue;
                    }
                    first_recovery=false;
                    if(selected_pose)*selected_pose=true;
                    e.x=next->x;e.y=next->y;occ_put(e);centers[e.name]={e.cx(),e.cy()};
                    // The earlier score compared different poses. Do not keep
                    // that stale estimate as evidence for this recovered pose.
                    side_offers[b.name]={b.side,b.side,b.shape_idx,std::nullopt,std::nullopt};
                    ok=true;break;
                }
            }
            if (ok) { --evict_budget; fallback("interior_reseat_retry"); }
            else {
                b=saved_b; e=saved_e;
                restore_entry(chosen,b.name,saved_chosen);
                restore_entry(centers,b.name,saved_center);
                restore_entry(side_offers,b.name,saved_offer);
                occ_put(e);
            }
            if(in.experiment&&in.experiment->reseat_completed)
                in.experiment->reseat_completed({bw,bh,b.name,e.name,incoming_seated,ok,plan.punch_free,compact_order});
            if(pass&&in.experiment->pose_retry_completed){observation.success=ok;in.experiment->pose_retry_completed(observation);}
            if(ok)return true;
        }
        return false;
    };
    for (auto* b:order) {
        std::tie(b->w,b->h)=zbox.at(b->name); b->area=block_area(b->w,b->h, counts);
        const auto a=pack_anchor(anchor_row(*b,centers));
        if (seat(*b,a,nullptr)) { occ_put(*b); centers[b->name]={b->cx(),b->cy()}; }
        else if (!retry(*b,a)) {
            if(failed_subject&&b!=order.front())*failed_subject=b->name;
            rejected("interior_seating",b->name,compact);return false;
        }
        placed.push_back(b);
    }
    std::vector<RefineBlock> refine;
    for (const auto* b:order) {
        RefineBlock row;
        row.name=b->name; row.x=b->x; row.y=b->y; row.w=b->w; row.h=b->h;
        row.reach=b->fanout_reach; row.inset=b->fanout_inset; row.mask=side_mask(b->side); row.comps=get(chosen,b->name);
        row.anchor=anchor_row(*b,centers); row.aff_named=get(affinity,b->name);
        const auto unrestricted=std::make_tuple(-bw,2*bw,-bh,2*bh);
        auto win=unrestricted;
        near_domain(*b,b->shape_idx,win);
        if(win!=unrestricted)row.translation_window=win;
        if (b->pull && !b->pull->exclusive) row.pull_to=b->pull->to;
        refine.push_back(std::move(row));
    }
    const auto refined=refine_pack_passes(occ,std::move(refine),
        std::unordered_map<std::string,FloorplanPoint>(centers.begin(),centers.end()),16,bw,bh,counts);
    for (std::size_t i=0;i<order.size();++i) { order[i]->x=refined.poses[i].first; order[i]->y=refined.poses[i].second; }

    if (!in.compose.index.hard.empty()) {
        FloorplanLegalizeInput li;
        li.board_w=bw; li.board_h=bh; li.index=in.compose.index; li.metrics=in.compose.metrics;
        li.channel_demand=channel_demand; li.clear=clear; li.origin=in.origin;
        for (const auto& b:plan.interior_blocks) if (b.shape_idx) {
            const auto m=in.compose.shape_metrics.find({b.name,b.shape_idx});
            if (m==in.compose.shape_metrics.end()) throw std::logic_error("floorplan: "+b.name+" chose shape "+std::to_string(b.shape_idx)+" but no per-shape zone metrics were registered — the legalizer would judge shape-0 geometry (silent breakage)");
            li.metrics[b.name]=m->second;
        }
        std::set<std::string> participants,movable;
        for (const auto& t:li.index.hard) if (t.kind=="flow_hop" || t.kind=="near_max" || t.kind=="facing") {
            participants.insert(t.subject); participants.insert(t.target());
        }
        for (const auto& b:plan.interior_blocks)
            if (participants.count(b.name) && in.compose.wired_participants.count(b.name)) movable.insert(b.name);
        if (!movable.empty()) {
            li.fixed_rects.emplace_back("som",legalize_som_rect(plan.som_x,plan.som_y,plan.som.w,plan.som.h,som_pad));
            const auto occupied_faces=[](int primary,const std::vector<Comp>& children) {
                for(const auto& child:children)primary|=child.mask;
                return primary;
            };
            li.primary_fanout["som"]={{},{},som_mask,occupied_faces(som_mask,som_comps),som_comps};
            for (const auto& c:corners) {
                const auto name="corner@"+number(c.x0)+","+number(c.y0);
                li.fixed_rects.emplace_back(name,c);
                li.primary_fanout[name]={{},{},occ_punch,occ_punch,std::vector<Comp>{}};
            }
            for (const auto& b:plan.edge_blocks)
                li.primary_fanout[b.name]={b.fanout_reach,b.fanout_inset,edge_mask,occupied_faces(edge_mask,get(edge_comps,b.name)),get(edge_comps,b.name)};
            for (const auto& b:plan.interior_blocks)
                li.primary_fanout[b.name]={b.fanout_reach,b.fanout_inset,side_mask(b.side),occupied_faces(side_mask(b.side),get(chosen,b.name)),get(chosen,b.name)};
            li.reservation_retry_started=[&]{fallback("legalize_reservation_retry");};
            li.facing_retry_started=[&]{fallback("legalize_facing_retry");};
            if(in.experiment)li.joint_separation_states=in.experiment->joint_separation_states;
            li.joint_retry_started=[&]{fallback("legalize_joint_retry");};
            li.joint_retry_completed=[&](const JointSeparationWork& work,bool ok){
                for(std::size_t i=0;i<work.visited;++i)fallback("legalize_joint_state");
                for(std::size_t i=0;i<work.axis_solves;++i)fallback("legalize_joint_axis");
                for(std::size_t i=0;i<work.qualifications;++i)fallback("legalize_joint_proposal");
                for(std::size_t i=0;i<work.qualification_rejections;++i)fallback("legalize_joint_reject");
                if(work.budget_exhausted)fallback("legalize_joint_budget");
                if(in.experiment&&in.experiment->joint_retry_completed)in.experiment->joint_retry_completed(work,ok);
            };
            auto fix=[&](const FloorplanBlock& b){li.fixed_rects.emplace_back(b.name,Box4{b.x,b.y,b.x+b.w,b.y+b.h}); li.fixed_poses[b.name]={b.x,b.y};};
            for (const auto& b:plan.edge_blocks) fix(b);
            for (const auto& b:plan.interior_blocks) if (!movable.count(b.name)) fix(b);
            li.fixed_rects.insert(li.fixed_rects.end(),in.compose.corridors.begin(),in.compose.corridors.end());
            for (const auto& [name, box]:in.compose.corridors) {
                (void)box;
                li.primary_fanout[name]={}; // Logical corridor: retain its existing exclusion gap.
            }
            li.som_core_page=som_core_rect(plan.som_x,plan.som_y,plan.som.w,plan.som.h,in.origin.first,in.origin.second,.03);
            std::vector<std::tuple<std::string,double,double,double,double>> rows;
            for (const auto& j:plan.som.js) rows.emplace_back(j.ref,j.x,j.y,j.w,j.h);
            for (const auto& [n,x0,y0,x1,y1]:som_jack_rects(plan.som_x,plan.som_y,rows)) li.som_j_rects[n]={x0,y0,x1,y1};
            const auto orig=plan.interior_blocks;
            auto legalize=[&](bool do_compact) {
                plan.interior_blocks=orig;
                std::vector<FloorplanLegalizeVar> vars;
                for (const auto& b:plan.interior_blocks) if (movable.count(b.name)) vars.push_back({b.name,b.w,b.h,{b.x,b.y},b.x,b.y});
                std::vector<std::string> log; li.compact=do_compact;
                li.report_infeasible_cycle=in.experiment&&bool(in.experiment->stage_rejected);
                if (!floorplan_legalize_compact_accounted(li,vars,log,plan.accounting.quantization_engagements)) {
                    rejected("legalizer","",do_compact,log);return false;
                }
                for (auto& b:plan.interior_blocks) for (const auto& v:vars) if (v.name==b.name) { b.x=v.x; b.y=v.y; break; }
                std::vector<PairsBlock> ints,edges;
                for (const auto& b:plan.interior_blocks) ints.push_back({b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,side_mask(b.side),get(chosen,b.name)});
                for (const auto& b:plan.edge_blocks) edges.push_back({b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,edge_mask,get(edge_comps,b.name)});
                if (!pairs_hold_from_layout(ints,edges,som_occ.x,som_occ.y,som_occ.w,som_occ.h,som_mask,som_comps,bw,bh,mh_corner,occ_punch,clear,counts)) {
                    rejected("post_legalizer_geometry","",do_compact,log);return false;
                }
                plan.composition=std::move(log); return true;
            };
            if (!legalize(compact)) {
                if (!(compact && legalize(false))) return false;
                fallback("legalize_only_compaction");
            }
        }
    }
    return true;
}

double Engine::refine_screened_incumbent(double incumbent_estimate) {
    if (!std::isfinite(incumbent_estimate) || incumbent_estimate<0)
        throw FloorplanError("floorplan: invalid screened incumbent estimate");
    auto incumbent=plan;
    auto offers=side_offers;
    auto restore=[&] {
        // Rejected work is still real work; never rewind the execution ledger.
        auto accounting=std::move(plan.accounting);
        plan=std::move(incumbent); plan.accounting=std::move(accounting); side_offers=std::move(offers);
    };
    try {
        if (attempt_pack(true)) {
            choose_connector_shapes();
            const double refined=estimate();
            if (std::isfinite(refined) && refined>=0 && refined<=incumbent_estimate) return refined;
        }
    } catch (...) {
        restore();
        throw; // An exception is not an infeasible candidate or permission to continue.
    }
    restore();
    fallback("screened_incumbent_retained");
    // Re-evaluate the selected layout, including its real scalar accounting and
    // observer event; no stale screening estimate is published as a new result.
    return estimate();
}

void Engine::choose_connector_shapes() {
    std::vector<std::string> names;
    for (const auto& b:plan.edge_blocks) names.push_back(b.name);
    std::sort(names.begin(),names.end());
    for (const auto& name:names) {
        const auto shapes=in.geometry.shapes.find(name);
        if (shapes==in.geometry.shapes.end() || shapes->second.size()<2) continue;
        auto& b=*std::find_if(plan.edge_blocks.begin(),plan.edge_blocks.end(),[&](const auto& x){return x.name==name;});
        const double base=estimate();
        auto incumbent=plan;
        auto offers=side_offers;
        const auto restore_incumbent=[&] {
            auto accounting=std::move(plan.accounting);
            plan=std::move(incumbent); plan.accounting=std::move(accounting);
            side_offers=std::move(offers);
        };
        try {
            std::tie(b.fanout_reach,b.fanout_inset)=fanout(shapes->second[1]); b.shape_idx=1;
            if (attempt_pack(true) && estimate()<base-1e-6) continue;
        } catch (...) {
            restore_incumbent();
            throw;
        }
        // attempt_pack mutates plan and side_offers; its compact_order is reset
        // before returning. Occupancy/placement/legalizer scratch is local.
        // Restore the complete accepted state, retaining ALL executed trial
        // accounting. No restoration pack ran, so none is counted or observed.
        restore_incumbent();
    }
}
}  // namespace schgen::floorplan_detail
