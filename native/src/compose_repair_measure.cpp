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
    auto terms=ja();for(const auto &t:r.terms)terms.array_value.push_back(jo({{"kind",j(t.kind)},{"subject",j(t.subject)},{"target",j(t.target)},{"measured",rounded(t.measured,4)},{"bound",j(t.bound)},{"ok",jb(t.ok)}}));
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
ComposeDocument measure_compose_ledger(const PcbPlacementInput &input,const PcbModel &model) {
    PcbCheckInput checked(model);const auto policy=pcb_placement_gate_policy(input);
    const auto index=pcb_final_compose_index(input,model);
    const auto evaluations=measure_pcb_compose_terms(checked,index,policy);
    ComposeDocument d;d.data=jo({{"board",jo({{"w",j(model.board_w)},{"h",j(model.board_h)},{"area_mm2",j(py_round(model.board_w*model.board_h,1))}})}});
    set(d.data,"flow_gate",flow(check_pcb_placement_flow(checked,policy),true));
    std::map<std::string,JsonNode> advisory;
    for(const auto &i:model.insts){auto p=policy.contracts.find(i.sheet);if(p!=policy.contracts.end())advisory[p->first]=p->second;}
    set(d.data,"advisory_gate",flow(check_pcb_placement_flow(checked,policy,&advisory),false));
    auto terms=ja();std::vector<double> finite;std::vector<std::string> triggers;
    const auto floor=floors();
    for(const auto &e:evaluations) {
        const auto &t=e.term;
        terms.array_value.push_back(jo({{"kind",j(t.kind)},{"subject",j(t.subject)},{"target",j(t.target_raw)},{"enforced",jb(t.enforced)},{"measured",rounded(e.measured,4)},{"bound",rounded(e.bound,4)},{"margin",rounded(e.margin,4)},{"ok",jb(e.ok)},{"basis",j(t.basis)}}));
        if(!std::isfinite(e.margin))continue;
        if(t.enforced)finite.push_back(e.margin);
        auto f=floor.find(t.kind);
        if(t.enforced&&f!=floor.end()&&e.margin<f->second) {
            auto name=t.kind=="flow_hop"?"flow":t.kind=="far_min"?"far":t.kind;
            triggers.push_back(name+" "+t.subject+"->"+t.target_raw+": margin "+fmt(e.margin,2,true)+(t.kind=="facing"?"deg":"")+" < floor "+pyfloat(f->second));
        }
        if(!e.ok&&!t.enforced&&t.kind!="near_intent")triggers.push_back("ADVISORY-RED "+t.kind+" "+t.subject+"->"+t.target_raw+": "+fmt(e.measured,2,true)+" vs "+fmt(e.bound,2,true)+" (repair-before-wire blocker)");
    }
    set(d.data,"terms",terms);
    double sum=0.,min=0.;if(!finite.empty()){min=finite.front();for(double n:finite){sum+=n;min=std::min(min,n);}}
    set(d.data,"aggregate_hard_margin",jo({{"sum",j(py_round(sum,2))},{"min",j(py_round(min,2))}}));
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
        std::vector<std::string> red;
        for(const auto &ev:c.evaluations)if(ev.term.enforced&&!ev.ok)red.push_back(key_repr(key(ev.term)));
        if(!red.empty()){out.output+=prefix+"REJECT (predicts hard RED: ["+document_detail::join(red,", ")+"])\n";continue;}
        c.aggregate_margin=0.;c.soft_red=0;
        for(const auto &ev:c.evaluations) {
            if(ev.term.enforced&&std::isfinite(ev.margin))c.aggregate_margin+=ev.margin;
            if(!ev.term.enforced&&!ev.ok&&ev.term.kind!="near_intent")++c.soft_red;
        }
        out.ranked.push_back(std::move(c));
    }
    std::stable_sort(out.ranked.begin(),out.ranked.end(),[](const auto &a,const auto &b){return std::make_tuple(a.soft_red,-a.aggregate_margin,a.area,a.edit.describe())<std::make_tuple(b.soft_red,-b.aggregate_margin,b.area,b.edit.describe());});
    out.output+="compose: ranked candidates (replica ORDER only — emitted board is the arbiter):\n";
    for(std::size_t i=0;i<std::min<std::size_t>(10,out.ranked.size());++i){const auto &c=out.ranked[i];out.output+="  "+c.edit.describe()+": predicted agg-hard-margin "+fmt(c.aggregate_margin,1,true)+", area "+pyfloat(c.area)+"\n";}
    return out;
}
} // namespace schgen
