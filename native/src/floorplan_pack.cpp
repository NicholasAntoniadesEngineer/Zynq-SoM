#include "floorplan_internal.hpp"

#include <algorithm>
#include <cmath>
#include <unordered_map>

namespace schgen::floorplan_detail {
namespace {
template<class Map> const typename Map::mapped_type& get(const Map& map, const typename Map::key_type& key) {
    const auto it = map.find(key);
    static const typename Map::mapped_type empty{};
    return it == map.end() ? empty : it->second;
}
char edge_char(const std::string& edge) { return edge.empty() ? '\0' : edge.front(); }
void pose(FloorplanBlock& b, const Pose& p) { b.x=p.x; b.y=p.y; b.w=p.w; b.h=p.h; }
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
        [&] { return attempt_pack_impl(compact); }, [&](bool packed) {
            return FloorplanAttemptObservation{plan.board_w, plan.board_h, packed,
                                               plan.punch_free, std::nullopt};
        });
}
bool Engine::attempt_pack_impl(bool compact) {
    // Borrow only for this synchronous invocation; never attach a sink to
    // occupancy geometry or candidate copies. Rejected trials remain counted.
    auto* const counts=&plan.accounting.quantization_engagements;
    const double bw=plan.board_w,bh=plan.board_h;
    const int policy=plan.punch_free ? 1:0;
    const auto& shapes=shape_sets[policy];
    const auto& co=components[policy];
    plan.spilled.clear();
    std::vector<PackEdgeBlock> edge_rows;
    for (auto& b:plan.edge_blocks) {
        std::tie(b.w,b.h)=zbox.at(b.name); b.area=block_area(b.w,b.h);
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
    const auto packed=pack_edges(edge_rows,jacks,{bw,bh,edge_margin,edge_inset,clear,cable_gap,overmold_gap,affinity_floor,
                                                plan.som_x,plan.som_y,plan.som.w,plan.som.h});
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
    checked_quantization_add(plan.accounting.quantization_engagements, "run_overflow_tol");
    if (!edge_runs_margin_ok(run_rows,bw,bh,edge_margin,.1)) return false;
    const auto som_rects=som_keepouts();
    if (rects_overlap_any(edge_boxes,som_rects,1e-6) || !cross_edge_fanout_hold(fanout_rows,clear)) return false;
    const int som_mask=plan.punch_free ? occ_top:occ_punch, edge_mask=som_mask;
    const Pose som_occ{plan.som_x-som_pad,plan.som_y-som_pad,plan.som.w+2*som_pad,plan.som.h+2*som_pad};
    std::vector<Comp> som_comps;
    if (plan.punch_free) som_comps=som_components(som_occ.x,som_occ.y,plan.dec_radius,
        som_decoupling_cells(plan.som_x,plan.som_y,plan.som.w,plan.som.h,plan.dec_count,dec_inset),
        {som_rects.begin()+1,som_rects.end()},occ_bottom,occ_punch);
    std::map<std::string,std::vector<Comp>> edge_comps;
    for (const auto& b:plan.edge_blocks) if (plan.punch_free)
        edge_comps[b.name]=edge_components(edge_char(b.edge),b.x,b.y,bw,bh,occ_punch,get(co,{b.name,b.shape_idx}));
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
    std::map<std::string,std::vector<Comp>> chosen;
    auto occ_put=[&](const FloorplanBlock& b){occ.add(b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,side_mask(b.side),get(chosen,b.name),counts);};
    auto occ_pull=[&](const FloorplanBlock& b){occ.remove(b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,side_mask(b.side),get(chosen,b.name),counts);};
    auto near=[&](FloorplanPoint a,double w,double h,Halo reach,Halo inset,int mask,const std::vector<Comp>& comps,
                  const FloorplanBlock* evicted) {
        std::tuple<double,double,double,double> win{-bw,2*bw,-bh,2*bh};
        if (evicted) win=evict_window(evicted->x,evicted->y,evicted->w,evicted->h,evicted->fanout_reach,evicted->fanout_inset,
                                     get(chosen,evicted->name),w,h,reach,inset,comps,clear);
        return occ.place_near(a.first,a.second,w,h,reach,inset,mask,comps,std::get<0>(win),std::get<1>(win),std::get<2>(win),std::get<3>(win),counts);
    };
    auto seat=[&](FloorplanBlock& b,FloorplanPoint a,const FloorplanBlock* evicted) {
        const auto variants=shapes.find(b.name);
        if (variants==shapes.end()) {
            const auto& cc=get(co,{b.name,0});
            const auto p=near(a,b.w,b.h,b.fanout_reach,b.fanout_inset,occ_top,cc,evicted);
            if (!p) return false;
            b.shape_idx=0; b.side="top"; chosen[b.name]=cc; pose(b,*p); return true;
        }
        std::vector<SeatShapeCand> cands;
        for (std::size_t k=0;k<variants->second.size();++k) {
            const auto& s=variants->second[k];
            auto win=std::make_tuple(-bw,2*bw,-bh,2*bh);
            if (evicted) win=evict_window(evicted->x,evicted->y,evicted->w,evicted->h,evicted->fanout_reach,evicted->fanout_inset,
                get(chosen,evicted->name),s.w,s.h,s.reach,s.inset,s.comps,clear);
            cands.push_back({static_cast<int>(k),s.w,s.h,s.reach,s.inset,side_mask(s.side),s.side,s.comps,
                std::get<0>(win),std::get<1>(win),std::get<2>(win),std::get<3>(win)});
        }
        auto hits=seat_shape_sides(occ,a.first,a.second,cands,bw,bh,clear,counts);
        if (hits.empty()) return false;
        std::sort(hits.begin(),hits.end(),[](const auto& a,const auto& b){return std::tie(a.dist_key,a.index)<std::tie(b.dist_key,b.index);});
        auto best=hits.front();
        if (hits.size()==1) side_offers[b.name]={best.side,best.side,best.index,std::nullopt,std::nullopt};
        else {
            auto judge=[&](const SeatShapeHit& h) {
                const auto saved=b;
                pose(b,{h.x,h.y,h.w,h.h}); b.shape_idx=h.index; b.side=h.side;
                std::vector<const FloorplanBlock*> partial;
                for (const auto& e:plan.edge_blocks) partial.push_back(&e);
                partial.insert(partial.end(),placed.begin(),placed.end()); partial.push_back(&b);
                double value;
                try { value=estimate(partial,b.name); } catch (...) { b=saved; throw; }
                b=saved; return value;
            };
            const double incumbent=judge(hits[0]),challenger=judge(hits[1]);
            if (pick_sided_challenger(incumbent,challenger,1e-6)) best=hits[1];
            side_offers[b.name]={hits[0].side+"(incumbent)/"+hits[1].side,best.side,best.index,incumbent,challenger};
        }
        pose(b,{best.x,best.y,best.w,best.h}); b.shape_idx=best.index; b.side=best.side;
        b.fanout_reach=best.reach; b.fanout_inset=best.inset; b.area=block_area(b.w,b.h); chosen[b.name]=best.comps;
        return true;
    };
    int evict_budget=reseat_evict_budget;
    auto retry=[&](FloorplanBlock& b,FloorplanPoint a) {
        if (evict_budget<1) return false;
        std::vector<std::tuple<double,double,double,double,std::string>> ranks;
        for (const auto* p:placed) ranks.emplace_back(p->x,p->y,p->w,p->h,p->name);
        for (int idx:reseat_rank(a.first,a.second,ranks)) {
            auto& e=*placed[idx]; const auto saved_e=e,saved_b=b;
            const auto saved_chosen=chosen;
            const auto saved_centers=centers;
            occ_pull(e);
            bool ok=seat(b,a,&e);
            if (ok) {
                occ_put(b); centers[b.name]={b.cx(),b.cy()};
                const auto anchor=pack_anchor(anchor_row(e,centers));
                const auto p=near(anchor,e.w,e.h,e.fanout_reach,e.fanout_inset,side_mask(e.side),get(chosen,e.name),nullptr);
                if (!p) { ok=false; occ_pull(b); }
                else { e.x=p->x; e.y=p->y; occ_put(e); centers[e.name]={e.cx(),e.cy()}; }
            }
            if (ok) { --evict_budget; fallback("interior_reseat_retry"); return true; }
            b=saved_b; e=saved_e; chosen=saved_chosen; centers=saved_centers; occ_put(e);
        }
        return false;
    };
    for (auto* b:order) {
        std::tie(b->w,b->h)=zbox.at(b->name); b->area=block_area(b->w,b->h);
        const auto a=pack_anchor(anchor_row(*b,centers));
        if (seat(*b,a,nullptr)) { occ_put(*b); centers[b->name]={b->cx(),b->cy()}; }
        else if (!retry(*b,a)) return false;
        placed.push_back(b);
    }
    std::vector<RefineBlock> refine;
    for (const auto* b:order) {
        RefineBlock row;
        row.name=b->name; row.x=b->x; row.y=b->y; row.w=b->w; row.h=b->h;
        row.reach=b->fanout_reach; row.inset=b->fanout_inset; row.mask=side_mask(b->side); row.comps=get(chosen,b->name);
        row.anchor=anchor_row(*b,centers); row.aff_named=get(affinity,b->name);
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
            for (const auto& c:corners) li.fixed_rects.emplace_back("corner@"+number(c.x0)+","+number(c.y0),c);
            auto fix=[&](const FloorplanBlock& b){li.fixed_rects.emplace_back(b.name,Box4{b.x,b.y,b.x+b.w,b.y+b.h}); li.fixed_poses[b.name]={b.x,b.y};};
            for (const auto& b:plan.edge_blocks) fix(b);
            for (const auto& b:plan.interior_blocks) if (!movable.count(b.name)) fix(b);
            li.fixed_rects.insert(li.fixed_rects.end(),in.compose.corridors.begin(),in.compose.corridors.end());
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
                if (!floorplan_legalize_compact_accounted(li,vars,log,plan.accounting.quantization_engagements)) return false;
                for (auto& b:plan.interior_blocks) for (const auto& v:vars) if (v.name==b.name) { b.x=v.x; b.y=v.y; break; }
                std::vector<PairsBlock> ints,edges;
                for (const auto& b:plan.interior_blocks) ints.push_back({b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,side_mask(b.side),get(chosen,b.name)});
                for (const auto& b:plan.edge_blocks) edges.push_back({b.x,b.y,b.w,b.h,b.fanout_reach,b.fanout_inset,edge_mask,get(edge_comps,b.name)});
                if (!pairs_hold_from_layout(ints,edges,som_occ.x,som_occ.y,som_occ.w,som_occ.h,som_mask,som_comps,bw,bh,mh_corner,occ_punch,clear,counts)) return false;
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

void Engine::choose_connector_shapes() {
    std::vector<std::string> names;
    for (const auto& b:plan.edge_blocks) names.push_back(b.name);
    std::sort(names.begin(),names.end());
    for (const auto& name:names) {
        const auto shapes=in.geometry.shapes.find(name);
        if (shapes==in.geometry.shapes.end() || shapes->second.size()<2) continue;
        auto& b=*std::find_if(plan.edge_blocks.begin(),plan.edge_blocks.end(),[&](const auto& x){return x.name==name;});
        const double base=estimate();
        const auto reach=b.fanout_reach,inset=b.fanout_inset;
        const auto events=plan.accounting.fallback_events;
        std::tie(b.fanout_reach,b.fanout_inset)=fanout(shapes->second[1],false); b.shape_idx=1;
        if (attempt_pack(true) && estimate()<base-1e-6) continue;
        b.fanout_reach=reach; b.fanout_inset=inset; b.shape_idx=0;
        if (!attempt_pack(true)) throw FloorplanError("floorplan: restoring the incumbent pack after rejecting "+name+"'s mirror shape failed — the deterministic re-pack must reproduce the accepted board");
        plan.accounting.fallback_events=events;
    }
}
}  // namespace schgen::floorplan_detail
