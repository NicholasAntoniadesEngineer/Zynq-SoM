#include "compose_repair_internal.hpp"
#include "schgen/legalize.hpp"
#include "schgen/ratsnest_gate.hpp"

namespace schgen {
using namespace compose_detail;
namespace {
JsonNode rounded(double x,int places) {return std::isinf(x)?JsonNode{}:j(py_round(x,places));}
JsonNode flow(const PcbPlacementFlowResult &r,bool budget) {
    auto out=jo({{"ok",jb(r.ok)}});
    if(budget)set(out,"flow_budget_mm",j(r.flow_budget_mm));
    set(out,"violations",sorted_strings(r.violations));set(out,"unresolved",sorted_strings(r.unresolved));
    auto terms=ja();for(const auto &t:r.terms)terms.array_value.push_back(jo({{"kind",j(t.kind)},{"subject",j(t.subject)},{"target",j(t.target)},{"measured",rounded(t.measured,4)},{"bound",j(t.bound)},{"ok",jb(t.ok)},{"advisory",jb(t.advisory)}}));
    set(out,"terms",terms);return out;
}
std::vector<std::string> seats(const FloorplanTermIndex &index,const std::optional<FloorplanSpec> &spec) {
    std::vector<std::string> out;if(!spec)return out;
    const auto edges=spec->edge_of();
    for(const auto &t:index.hard) {
        if(t.kind!="near_max")continue;
        auto it=spec->interior.find(t.subject);if(it==spec->interior.end()||!it->second.near)continue;
        const auto &a=it->second;
        if(edges.count(*a.near)&&!(a.pull&&a.pull->exclusive))out.push_back(t.subject+": WIRED near_max -> "+t.target_raw+" rides the floorplan near-anchor at edge block "+repr(*a.near)+" without an exclusive pull in carrier/floorplan.json — seat is packing-luck (migrate the seat to the pull knob)");
    }std::sort(out.begin(),out.end());return out;
}
}
ComposeDocument measure_compose_ledger(const PcbPlacementInput &input,const PcbModel &model,QuantizationCounts* measurement_counts) {
    PcbCheckInput checked(model);const auto policy=pcb_placement_gate_policy(input);
    const auto index=pcb_final_compose_index(input,model);
    const auto evaluations=measure_pcb_compose_terms(checked,index,policy,measurement_counts);
    ComposeDocument d;d.data=jo({{"board",jo({{"w",j(model.board_w)},{"h",j(model.board_h)},{"area_mm2",j(py_round(model.board_w*model.board_h,1))}})}});
    set(d.data,"flow_gate",flow(check_pcb_placement_flow(checked,policy,nullptr,measurement_counts),true));
    std::map<std::string,JsonNode> advisory;
    for(const auto &i:model.insts){auto p=policy.contracts.find(i.sheet);if(p!=policy.contracts.end())advisory[p->first]=p->second;}
    set(d.data,"advisory_gate",flow(check_pcb_placement_flow(checked,policy,&advisory,measurement_counts),false));
    auto terms=ja();std::vector<std::string> triggers;
    const auto floor=floors();
    for(const auto &e:evaluations) {
        const auto &t=e.term;
        terms.array_value.push_back(jo({{"kind",j(t.kind)},{"subject",j(t.subject)},{"target",j(t.target_raw)},{"enforced",jb(t.enforced)},{"measured",rounded(e.measured,4)},{"bound",rounded(e.bound,4)},{"margin",rounded(e.margin,4)},{"ok",jb(e.ok)},{"basis",j(t.basis)}}));
        if(!std::isfinite(e.margin))continue;
        auto f=floor.find(t.kind);
        if(t.enforced&&f!=floor.end()&&e.margin<f->second) {
            auto name=t.kind=="flow_hop"?"flow":t.kind=="far_min"?"far":t.kind;
            triggers.push_back(name+" "+t.subject+"->"+t.target_raw+": margin "+fmt(e.margin,2,true)+(t.kind=="facing"?"deg":"")+" < floor "+pyfloat(f->second));
        }
        // Board-size-derived flow references rank placement quality; exceeding
        // one is not evidence of a hardware fault or a repair obligation.
        if(!e.ok&&!t.enforced&&t.kind!="near_intent"&&t.kind!="flow_hop")triggers.push_back("ADVISORY-RED "+t.kind+" "+t.subject+"->"+t.target_raw+": "+fmt(e.measured,2,true)+" vs "+fmt(e.bound,2,true)+" (repair-before-wire blocker)");
    }
    set(d.data,"terms",terms);
    const auto margins=pcb_compose_hard_margins(evaluations);
    const auto group=[](const PcbComposeMarginStats& s){return jo({{"measured",j(static_cast<double>(s.measured))},
        {"unresolved",j(static_cast<double>(s.unresolved))},{"sum",j(s.sum)},
        {"minimum",s.minimum?j(*s.minimum):JsonNode{}}});};
    set(d.data,"hard_margins",jo({{"distance_mm",group(margins.distance_mm)},
        {"facing_degrees",group(margins.facing_degrees)}}));
    const auto rats=check_ratsnest(checked);const auto slack=rats.cross_budget_mm-rats.cross_mm;
    const auto pct=rats.cross_budget_mm?py_round(100.*slack/rats.cross_budget_mm,2):0.;
    auto dispersion=jo();for(const auto &[k,v]:ratsnest_dispersion_by_sheet(rats))set(dispersion,k,j(v));
    set(d.data,"law5",jo({{"ok",jb(rats.ok)},{"cross_mm",j(rats.cross_mm)},{"budget_mm",j(rats.cross_budget_mm)},{"slack_mm",j(py_round(slack,1))},{"slack_pct",j(pct)},{"off_board",j(static_cast<double>(rats.off_board.size()))},{"dispersed",j(static_cast<double>(rats.dispersed.size()))},{"dispersion_by_sheet",dispersion}}));
    auto violations=jo();for(const auto &[s,r]:check_all_pcb_placement_contracts(checked,policy))set(violations,s,j(static_cast<double>(r.violations.size())));
    set(d.data,"contract_violations",violations);
    auto hotspots=jo();
    for(const auto &[pair,count]:pcb_cross_airwires_by_pair(model)) {
        const auto demand=channel_demand_mm(count.first,6,2.,.2);
        if(demand>0.&&pair.first.compare(0,5,"som_j")!=0&&pair.second.compare(0,5,"som_j")!=0)set(hotspots,pair.first+"|"+pair.second,jo({{"airwires",j(count.first)},{"mm",j(count.second)},{"corridor_mm",j(demand)}}));
    }
    set(d.data,"channel_hotspots",hotspots);
    if(pct<5.)triggers.push_back("law5 cross slack "+pyfloat(pct)+"% < floor 5.0%");
    set(d.data,"repair_triggers",sorted_strings(triggers));set(d.data,"seat_consistency",strings(seats(index,input.floorplan.spec)));
    floats(d,d.data);
    for(const auto* unit:{"distance_mm","facing_degrees"})for(const auto* count:{"measured","unresolved"})
        d.float_paths.erase(std::string("/hard_margins/")+unit+"/"+count);
    d.float_paths.erase("/law5/off_board");d.float_paths.erase("/law5/dispersed");
    for(const auto &[s,v]:violations.object_value){(void)v;d.float_paths.erase("/contract_violations/"+pointer(s));}
    for(const auto &[s,v]:hotspots.object_value){(void)v;d.float_paths.erase("/channel_hotspots/"+pointer(s)+"/airwires");}
    return d;
}
ComposeReplica compose_plan_replica(const PcbPlacementInput &input,const FloorplanSpec &spec) {
    auto authored=input;authored.floorplan.spec=spec;authored.two_side=true;
    const auto zones=build_pcb_zone_geometry(authored);
    const auto prepared=prepare_pcb_floorplan(authored,zones);
    ComposeReplica out;out.plan=build_floorplan(prepared);
    auto &ev=out.evaluation;ev.board_w=out.plan.board_w;ev.board_h=out.plan.board_h;ev.origin=prepared.origin;
    ev.som_core_page=som_core_rect(out.plan.som_x,out.plan.som_y,out.plan.som.w,out.plan.som.h,prepared.origin.first,prepared.origin.second,.03);
    ev.metrics=prepared.compose.metrics;
    for(const auto *blocks:{&out.plan.edge_blocks,&out.plan.interior_blocks})for(const auto &b:*blocks) {
        out.poses[b.name]={b.x,b.y};
        if(b.shape_idx)ev.metrics[b.name]=prepared.compose.shape_metrics.at({b.name,b.shape_idx});
    }
    // No independent reimplementation of legalizer, term or gate algorithms.
    out.area=py_round(out.plan.board_w*out.plan.board_h,1);return out;
}
ComposeCandidate evaluate_compose_candidate(const PcbPlacementInput &input,const ComposeDocument &raw,const ComposeSpecEdit &edit,const FloorplanTermIndex &index,const std::optional<std::set<std::string>> &valid_names) {
    ComposeCandidate out;out.edit=edit;out.edited=edit.apply(raw);
    const auto spec=floorplan_spec_from_json(out.edited.data,"floorplan.json",valid_names);
    auto replica=compose_plan_replica(input,spec);replica.evaluation.index=index;
    out.evaluations=floorplan_evaluate_terms(replica.evaluation,replica.poses);
    out.area=replica.area;out.spilled=replica.plan.spilled;return out;
}
ComposeRanking rank_compose_candidates(std::vector<ComposeCandidate> candidates) {
    ComposeRanking out;
    for(auto &c:candidates) {
        const auto prefix="  candidate "+c.edit.describe()+": ";
        if(!c.error.empty()){out.output+=prefix+"INVALID ("+c.error+")\n";continue;}
        if(!c.spilled.empty()){out.output+=prefix+"REJECT (spilled: "+list_repr(c.spilled)+")\n";continue;}
        if(!std::isfinite(c.area)||c.area<=0){out.output+=prefix+"REJECT (invalid board area)\n";continue;}
        std::vector<std::string> red;
        for(const auto &ev:c.evaluations)if(ev.term.enforced&&!ev.ok)red.push_back(key_repr(key(ev.term)));
        if(!red.empty()){out.output+=prefix+"REJECT (predicts hard RED: ["+document_detail::join(red,", ")+"])\n";continue;}
        c.minimum_distance_mm.reset();c.minimum_facing_degrees.reset();c.soft_red=0;
        bool invalid=false;
        for(const auto &ev:c.evaluations) {
            if(ev.term.enforced) {
                const auto& kind=ev.term.kind;
                if(ev.note=="UNRESOLVED"||!std::isfinite(ev.measured)||!std::isfinite(ev.bound)||!std::isfinite(ev.margin)||
                   (kind!="facing"&&kind!="flow_hop"&&kind!="near_max"&&kind!="far_min")) {invalid=true;break;}
                auto& minimum=kind=="facing"?c.minimum_facing_degrees:c.minimum_distance_mm;
                if(!minimum||ev.margin<*minimum)minimum=ev.margin;
            }
            if(!ev.term.enforced&&!ev.ok&&ev.term.kind!="near_intent")++c.soft_red;
        }
        if(invalid){out.output+=prefix+"REJECT (unresolved or invalid hard measurement)\n";continue;}
        out.ranked.push_back(std::move(c));
    }
    const auto rank=[](const auto& c) {
        // Missing groups are not measurements or infinite safety credit.
        return std::make_tuple(c.soft_red,c.area,-c.minimum_distance_mm.value_or(0.),
            -c.minimum_facing_degrees.value_or(0.),c.edit.describe());
    };
    std::stable_sort(out.ranked.begin(),out.ranked.end(),[&](const auto& a,const auto& b){return rank(a)<rank(b);});
    out.output+="compose: ranked candidates (soft RED, area, minimum mm margin, minimum degree margin, edit; replica ORDER only — emitted board is the arbiter):\n";
    const auto shown=[](const std::optional<double>& v){return v?fmt(*v,4,true):"unavailable";};
    for(std::size_t i=0;i<std::min<std::size_t>(10,out.ranked.size());++i){const auto &c=out.ranked[i];out.output+="  "+c.edit.describe()+": predicted min margin "+shown(c.minimum_distance_mm)+" mm / "+shown(c.minimum_facing_degrees)+" degrees, area "+pyfloat(c.area)+" mm^2\n";}
    return out;
}
} // namespace schgen
