#include "floorplan_internal.hpp"
#include "schgen/precision_ops.hpp"

#include <algorithm>
#include <cmath>
#include <regex>

namespace schgen::floorplan_detail {
namespace {
const std::set<std::string> edge_families{"TYPE-C-31-M-12","HDMI-019S","AFC07-S40FCA-00","SFW15R-1STE1LF","TF-01A","DS1024-2x6R2","XT60PW-M"};
// Each helper books only its immediately following real scalar call in the
// current plan invocation; candidate restore already preserves all accounting.
struct BuildPrecision {
    QuantizationCounts& counts;
    double area(double value) const {
        static const std::string name="floorplan_candidate_area_precision1dp";
        checked_quantization_add(counts,name);
        return floorplan_candidate_area_precision1dp(value);
    }
    double aspect(double value) const {
        static const std::string name="floorplan_seed_aspect_precision4dp";
        checked_quantization_add(counts,name);
        return floorplan_seed_aspect_precision4dp(value);
    }
    double value(double value) const {
        static const std::string name="floorplan_ledger_value_precision1dp";
        checked_quantization_add(counts,name);
        return floorplan_ledger_value_precision1dp(value);
    }
    double margin(double value) const {
        static const std::string name="floorplan_ledger_margin_precision3dp";
        checked_quantization_add(counts,name);
        return floorplan_ledger_margin_precision3dp(value);
    }
    double dimension(double value) const {
        static const std::string name="floorplan_ledger_dimension_precision4dp";
        checked_quantization_add(counts,name);
        return floorplan_ledger_dimension_precision4dp(value);
    }
};
using Inputs=std::vector<std::pair<std::string,JsonNode>>;
using Winner=std::tuple<double,double,double,double,double>; // area,w,h,estimate,budget
Inputs winner_inputs(const Winner& w,QuantizationCounts& counts) {
    const BuildPrecision precision{counts};
    return {{"board_w",jvalue(std::get<1>(w))},{"board_h",jvalue(std::get<2>(w))},
        {"area",jvalue(std::get<0>(w))},{"est_cross",jvalue(precision.value(std::get<3>(w)))},
        {"budget",jvalue(precision.value(std::get<4>(w)))},{"headroom",jvalue(precision.value(std::get<4>(w)-std::get<3>(w)))}};
}
std::string outline_text(double w,double h) { return number(w)+"x"+number(h); }
void add_weight(std::vector<std::pair<std::string,double>>& rows,const std::string& key,double w) {
    for (auto& row:rows) if (row.first==key) { row.second+=w; return; }
    rows.emplace_back(key,w);
}
}  // namespace

void Engine::initialize() {
    std::vector<std::string> sheet_names;
    std::vector<std::tuple<std::string,bool,std::string,std::vector<std::string>>> bindings;
    for (const auto& sc:in.sheets) sheet_names.push_back(sc.name);
    for (const auto& b:in.link.bindings) {
        const bool deferred=b.status=="deferred" && !b.ptype.expect.empty();
        bindings.emplace_back(b.sheet,deferred,deferred ? b.ptype.expect : "",b.targets);
    }
    std::map<std::string,std::vector<std::pair<std::string,int>>> aff;
    for (const auto& row:j_affinity(sheet_names,bindings)) aff.emplace(row);
    std::vector<std::tuple<std::string,double,double>> jack_rows;
    for (const auto& j:plan.som.js) jack_rows.emplace_back(j.ref,j.x,j.y);
    std::map<std::string,std::string> j_edges;
    for (const auto& row:j_edge_map(jack_rows,plan.som.w,plan.som.h)) j_edges.emplace(row);
    const FloorplanSpec spec=in.spec.value_or(FloorplanSpec{});
    const auto spec_edges=spec.edge_of(); const auto spec_order=spec.edge_order();
    std::set<std::string> regs;
    for (const auto& r:in.regulators) regs.insert(r.sheet);
    std::map<std::string,std::set<std::string>> zone_refs;
    for (const auto& sc:in.sheets) for (const auto* p:zone_parts(sc)) {
        zone_refs[sc.name].insert(p->ref);
        const auto wh=part_dims(p->footprint); raw_area+=wh.first*wh.second;
    }
    const std::regex deferred_re(R"(\b(rj45|usb_uart)_connector\b)");
    for (const auto& [name,sc]:sheets) {
        auto parts=zone_parts(*sc);
        if ((starts(name,"som_j") || name=="som_decoupling") && parts.empty()) continue;
        FloorplanBlock b; b.name=name; b.n_parts=static_cast<int>(parts.size()); b.j_aff=aff[name];
        std::sort(parts.begin(),parts.end(),[](const auto* a,const auto* b){return a->ref<b->ref;});
        for (const auto* p:parts) if (edge_families.count(p->value)) {
            const auto wh=part_dims(p->footprint); b.conns.push_back({p->ref,p->value,wh.first,wh.second});
        }
        std::set<std::string> reserved;
        for (const auto& pt:sc->port_types)
            for (auto m=std::sregex_iterator(pt.expect.begin(),pt.expect.end(),deferred_re);m!=std::sregex_iterator();++m)
                reserved.insert(m->str());
        b.reserved.assign(reserved.begin(),reserved.end());
        const bool is_edge=spec_edges.count(name) || ((!b.conns.empty() || !b.reserved.empty()) && !spec.interior.count(name));
        b.kind=is_edge ? "edge":"interior";
        if (is_edge) {
            if (spec_edges.count(name)) {
                edge_of[name]=spec_edges.at(name); b.pinned=true;
                if (spec_order.count(name)) b.order_hint=spec_order.at(name);
            } else {
                const auto j=dominant_j(b.j_aff);
                edge_of[name]=j && j_edges.count(*j) ? j_edges.at(*j):"N";
            }
            plan.edge_blocks.push_back(std::move(b));
        } else plan.interior_blocks.push_back(std::move(b));
    }
    // Net order follows the original sheet/net insertion order. It controls
    // floating-point affinity accumulation and must not be replaced by sorting.
    std::vector<std::pair<std::string,std::set<std::string>>> net_sheets;
    std::map<std::string,std::size_t> net_index;
    std::map<std::string,std::set<std::string>> port_sheets;
    std::set<std::string> som_nets;
    for (const auto& sc:in.sheets) {
        for (const auto& n:sc.nets) {
            if (starts(sc.name,"som_j")) {
                som_nets.insert(n.name);
                bool auxiliary=false;
                for (const auto& p:n.pins) if (zone_refs[sc.name].count(p.ref)) auxiliary=true;
                if (!auxiliary) continue;
            }
            if (n.net_class=="port") port_sheets[n.name].insert(sc.name);
            const auto inserted=net_index.emplace(n.name,net_sheets.size());
            if (inserted.second) net_sheets.emplace_back(n.name,std::set<std::string>{});
            net_sheets[inserted.first->second].second.insert(sc.name);
        }
        if (!starts(sc.name,"som_j") && std::any_of(sc.parts.begin(),sc.parts.end(),[](const auto& p){return p.footprint.find("MountingHole")==std::string::npos;})) ++n_sub;
    }
    for (auto& b:plan.interior_blocks) {
        const auto explicit_anchor=spec.interior.find(b.name);
        if (explicit_anchor!=spec.interior.end()) {
            const auto& a=explicit_anchor->second; b.pinned=true; b.pull=a.pull;
            auto sv=a.side.value_or("E");
            if (sv=="top" || sv=="bottom" || sv=="either") { b.layer_pref=sv; sv="E"; }
            if (a.layer) b.layer_pref=*a.layer;
            b.zone=a.near ? "@"+*a.near:sv; continue;
        }
        bool reg=regs.count(b.name)!=0;
        for (const auto& p:in.project.reg_band_prefixes) reg |= starts(b.name,p);
        if (reg) { b.zone="E"; continue; }
        const auto dominant=dominant_j(b.j_aff);
        if (dominant && !j_edges.count(*dominant)) throw FloorplanError("floorplan: affinity references missing SoM connector "+*dominant);
        b.zone=dominant ? j_edges.at(*dominant):"E";
        int best_n=0; const FloorplanBlock* best=nullptr;
        for (const auto& e:plan.edge_blocks) {
            int n=0;
            for (const auto& [net,members]:port_sheets) { (void)net; if (members==std::set<std::string>{b.name,e.name}) ++n; }
            if (n>best_n) { best_n=n; best=&e; }
        }
        if (best_n>=2) b.zone="@"+best->name;
    }
    for (const auto& [net,members]:net_sheets) {
        if (members.size()==2) ++channel_demand[{*members.begin(),*members.rbegin()}];
        if (members.size()<2 && !som_nets.count(net)) continue;
        const double w=1.0/std::max<std::size_t>(1,members.size()+(som_nets.count(net) ? 1:0));
        for (auto a=members.begin();a!=members.end();++a) {
            if (som_nets.count(net)) som_pull[*a]+=w;
            for (auto b=std::next(a);b!=members.end();++b) {
                add_weight(affinity[*a],*b,w); add_weight(affinity[*b],*a,w);
            }
        }
    }
}

void Engine::ledger_initial(double sw,double sh) {
    const BuildPrecision precision{plan.accounting.quantization_engagements};
    calc("overmold_side_gap",jvalue(overmold_gap),{{"plug_width",jvalue(overmold_plug_width)},{"copper_half_width",jvalue(overmold_copper_half_width)}});
    calc("edge_band",jvalue(edge_band),{{"edge_depth_cap",jvalue(edge_depth_cap)},{"edge_band_relief",jvalue(edge_band_relief)}});
    calc("occ_punch_mask",jvalue(occ_punch),{{"occ_top",jvalue(occ_top)},{"occ_bottom",jvalue(occ_bottom)}});
    const double ordinary=floorplan_experiment_via_cost(in.experiment.get(),false,est_via_cost(false));
    const double impedance=floorplan_experiment_via_cost(in.experiment.get(),true,est_via_cost(true));
    calc("est_via_ordinary",jvalue(ordinary),{{"via_cost",jvalue(ordinary)}});
    calc("est_via_impedance",jvalue(impedance),{{"via_cost",jvalue(impedance)}});
    int nj=0;
    for (const auto& sc:in.sheets) if (starts(sc.name,"som_j")) ++nj;
    calc("subsystem_count",jvalue(n_sub),{{"n_sheets",jvalue(static_cast<int>(in.sheets.size()))},{"n_som_j",jvalue(nj)},
        {"n_mechanical_only",jvalue(static_cast<int>(in.sheets.size())-n_sub-nj)}});
    calc("seed_outline",jvalue(outline_text(sw,sh)),{{"som_w",jvalue(plan.som.w)},{"som_h",jvalue(plan.som.h)},
        {"som_halo",jvalue(som_halo)},{"edge_band",jvalue(edge_band)},{"component_area",jvalue(precision.value(raw_area))},
        {"pack_efficiency",jvalue(fill)},{"perimeter_keepout",jvalue(perimeter)},{"seed_w",jvalue(sw)},{"seed_h",jvalue(sh)}});
    int low=0,high=0;
    for (const auto& [sheet,wh]:in.geometry.zone_box) {
        (void)wh;
        for (const auto* offsets:{&in.geometry.top_off,&in.geometry.bot_off}) {
            const auto os=offsets->find(sheet);
            if (os==offsets->end()) continue;
            for (const auto& [ref,xy]:os->second) {
                (void)xy;
                if (!in.geometry.resolvable.count(ref)) continue;
                const int pins=footprint(in.geometry.resolvable.at(ref)).pins;
                if (pins>=min_subject_pins) { if (pins<=8) ++low; else ++high; }
            }
        }
    }
    calc("d13_tier_population",jvalue(low+high),{{"n_subjects",jvalue(low+high)},{"tier_le2_0p20",jvalue(0)},
        {"tier_le8_1p50",jvalue(low)},{"tier_ge9_2p00",jvalue(high)}});
    const auto [gw,gh,cols,rows]=som_decoupling_grid(plan.som.w,plan.som.h,plan.dec_count,dec_inset);
    calc("decoupling_grid",jvalue(plan.dec_count),{{"n_caps",jvalue(plan.dec_count)},{"som_w",jvalue(plan.som.w)},
        {"som_h",jvalue(plan.som.h)},{"inset",jvalue(dec_inset)},{"grid_w",jvalue(precision.dimension(gw))},
        {"grid_h",jvalue(precision.dimension(gh))},{"cols",jvalue(cols)},{"rows",jvalue(rows)}});
}
void Engine::ledger_sides() {
    const BuildPrecision precision{plan.accounting.quantization_engagements};
    int two=0,bottom=0,single=0;
    for (const auto& [name,s]:side_offers) {
        if (!s.incumbent) {
            ++single; calc("side_fixed",jvalue(s.chosen),{{"label",jvalue(name)},{"offered",jvalue(s.offered)},{"shape_idx",jvalue(s.shape)}});
        } else {
            ++two; if (s.chosen=="bottom") ++bottom;
            calc("side_choice",jvalue(s.chosen),{{"label",jvalue(name)},{"offered",jvalue(s.offered)},
                {"est_incumbent",jvalue(precision.value(*s.incumbent))},{"est_challenger",jvalue(precision.value(*s.challenger))},
                {"margin",jvalue(precision.margin(*s.incumbent-*s.challenger))}});
        }
    }
    calc("side_census",jvalue(two+single),{{"n_blocks",jvalue(two+single)},{"n_two_face",jvalue(two)},
        {"n_chose_bottom",jvalue(bottom)},{"n_single_face",jvalue(single)}});
}

FloorplanPlan Engine::run() {
    const BuildPrecision precision{plan.accounting.quantization_engagements};
    ledger_open();
    initialize();
    const auto outline=derive_outline_wh(plan.som.w,plan.som.h,som_halo,edge_band,perimeter,fill,raw_area);
    const double sw=std::get<0>(outline),sh=std::get<1>(outline),bw=std::get<2>(outline),bh=std::get<3>(outline),
                 aw=std::get<4>(outline),ah=std::get<5>(outline);
    const std::string seed_note="SoM "+outline_text(plan.som.w,plan.som.h)+" + "+number(som_halo)+"mm halo + "+number(edge_band)+
        "mm connector band/edge -> core "+outline_text(bw,bh)+"; component area "+number(raw_area,0)+"mm2 / "+number(fill)+
        " fill -> area floor "+number(aw,0)+"x"+number(ah,0)+"; + "+number(perimeter)+"mm perimeter keepout -> "+
        outline_text(sw,sh)+" mm (rounded up to 5mm grid)";
    board_size(sw,sh); plan.outline_note=seed_note;
    prepare_geometry(); ledger_initial(sw,sh); prepare_cross();
    calc("est_via_class_split",jvalue(n_impedance),{{"n_cross_nets",jvalue(static_cast<int>(cross_nets.size()))},
        {"n_impedance",jvalue(n_impedance)},{"n_ordinary",jvalue(static_cast<int>(cross_nets.size())-n_impedance)},
        {"impedance_classes",jvalue(impedance_classes)}});
    std::map<std::string,std::tuple<int,Halo,Halo>> pristine;
    for (auto* b:blocks()) pristine[b->name]={b->shape_idx,b->fanout_reach,b->fanout_inset};
    auto reset_shapes=[&] { for (auto* b:blocks()) std::tie(b->shape_idx,b->fanout_reach,b->fanout_inset)=pristine.at(b->name); };
    auto restore=[&](const FloorplanPlan& saved) {
        // Candidate decisions and quantization engagements describe ALL work;
        // only layout and the caller-managed fallback event snapshot roll back.
        auto accounting=std::move(plan.accounting); plan=saved; plan.accounting=std::move(accounting);
    };
    const auto entry_events=plan.accounting.fallback_events;
    if (in.spec && in.spec->outline) {
        board_size(in.spec->outline->first,in.spec->outline->second);
        auto fixed=[&](bool free) {
            plan.punch_free=free;
            if (!attempt_pack(true)) throw FloorplanError("floorplan: the REAL 2-sided packed blocks do not fit the fixed outline "+
                outline_text(plan.board_w,plan.board_h)+" declared in carrier/floorplan.json — enlarge it or use \"outline\":\"auto\"");
            choose_connector_shapes(); return estimate();
        };
        reset_shapes(); double estimate_real=fixed(false);
        const auto conservative=plan; const auto offers=side_offers;
        plan.accounting.fallback_events=entry_events; reset_shapes();
        std::optional<double> free_est;
        try { free_est=fixed(true); } catch (const FloorplanError&) {}
        if (free_est && *free_est<estimate_real-1e-6) estimate_real=*free_est;
        else { restore(conservative); side_offers=offers; plan.accounting.fallback_events=conservative.accounting.fallback_events; fallback("punch_free_plan_rejected"); }
        const double area=precision.area(plan.board_w*plan.board_h);
        const double budget=cross_budget(plan.board_w,plan.board_h,n_sub,in.cross_budget_k);
        calc("plan_choice",jvalue("fixed"),{{"conservative_area",jvalue(area)},{"conservative_est",jvalue(precision.value(estimate_real))},
            {"free_area",jvalue(area)},{"free_est",jvalue(free_est ? precision.value(*free_est):0.0)}});
        ledger_sides();
        auto inputs=winner_inputs({area,plan.board_w,plan.board_h,estimate_real,budget},plan.accounting.quantization_engagements); inputs.emplace_back("plan",jvalue("fixed"));
        calc("sizing_winner",jvalue(outline_text(plan.board_w,plan.board_h)),std::move(inputs));
        plan.outline_note="FIXED outline "+outline_text(plan.board_w,plan.board_h)+" mm declared in carrier/floorplan.json; estimated cross-subsystem airwire "+
            number(estimate_real,0)+" mm (LAW-5 budget "+number(budget,0)+" mm — the REAL gate in `schgen board` is the arbiter)";
        return std::move(plan);
    }
    const double seed_aspect=precision.aspect(sw/sh);
    const std::set<double> aspects{seed_aspect,1,1.1,1.2,1.3,1.4};
    auto search=[&](bool free) -> Winner {
        plan.punch_free=free;
        ledger_pass(free);
        std::map<std::string,int> tally{{"generated",0},{"reject_aspect",0},{"reject_min_area",0},{"reject_not_smaller",0},{"reject_pack",0},{"reject_law5_budget",0},{"accepted",0}};
        std::optional<Winner> best; bool fit_seen=false;
        double min_area=plan.som.w*plan.som.h;
        const auto& sets=shape_sets[free ? 1:0];
        for (const auto& [name,wh]:zbox) {
            double area=wh.first*wh.second;
            const auto variants=sets.find(name);
            if (variants!=sets.end()) {
                area=variants->second.front().w*variants->second.front().h;
                for (const auto& s:variants->second) area=std::min(area,s.w*s.h);
            }
            min_area+=area;
        }
        auto evaluate=[&](double w,double h) -> std::optional<Winner> {
            board_size(w,h);
            if (!attempt_pack(false)) { ++tally["reject_pack"]; return std::nullopt; }
            fit_seen=true;
            const double budget=cross_budget(w,h,n_sub,in.cross_budget_k), est=estimate();
            if (est>budget) { ++tally["reject_law5_budget"]; return std::nullopt; }
            ++tally["accepted"]; return Winner{precision.area(w*h),w,h,est,budget};
        };
        for (double aspect:aspects) for (int k=0;k<80;++k) {
            checked_quantization_add(plan.accounting.quantization_engagements, "outline_grow_step");
            const double grow=outline_grow(k);
            const double w=quantize("outline_snap_up",sw+grow*(aspect/seed_aspect));
            const double h=quantize("outline_snap_up",sh+grow);
            ++tally["generated"];
            if (w<h) { ++tally["reject_aspect"]; continue; }
            if (w*h<min_area) { ++tally["reject_min_area"]; continue; }
            if (auto candidate=evaluate(w,h)) { if (!best || *candidate<*best) best=candidate; break; }
        }
        if (!best) throw FloorplanError(std::string("floorplan: could not fit all REAL packed blocks under the LAW-5 airwire budget on any searched outline (blocks ")+(fit_seen ? "did":"never")+" fit)");
        const double w0=std::get<1>(*best),h0=std::get<2>(*best);
        std::vector<double> ws,hs;
        for (int k=0;k<=refine_span;++k) {
            checked_quantization_add(plan.accounting.quantization_engagements, "outline_fine_grid");
            ws.push_back(fine_shrink(w0,k));
            checked_quantization_add(plan.accounting.quantization_engagements, "outline_fine_grid");
            hs.push_back(fine_shrink(h0,k));
        }
        for (double w:ws) for (double h:hs) {
            ++tally["generated"];
            if (w<=0 || h<=0 || w<h) { ++tally["reject_aspect"]; continue; }
            if (w*h>=std::get<1>(*best)*std::get<2>(*best)-1e-6) { ++tally["reject_not_smaller"]; continue; }
            if (w*h<min_area) { ++tally["reject_min_area"]; continue; }
            if (auto candidate=evaluate(w,h)) best=candidate;
        }
        board_size(std::get<1>(*best),std::get<2>(*best));
        if (!attempt_pack(true)) throw FloorplanError("floorplan: the winning outline "+outline_text(plan.board_w,plan.board_h)+" failed the final compact re-pack — refusing to emit a stale layout");
        choose_connector_shapes();
        Inputs ti;
        for (const auto* key:{"generated","reject_aspect","reject_min_area","reject_not_smaller","reject_pack","reject_law5_budget","accepted"}) ti.emplace_back(key,jvalue(tally.at(key)));
        calc("outline_candidates",jvalue(tally.at("generated")),std::move(ti),"sizing.pass");
        calc("law5_airwire_budget",jvalue(precision.value(std::get<4>(*best))),{{"cross_k",jvalue(in.cross_budget_k)},
            {"board_w",jvalue(plan.board_w)},{"board_h",jvalue(plan.board_h)},{"n_subsystems",jvalue(n_sub)}},"sizing.pass");
        calc("pass_winner",jvalue(outline_text(plan.board_w,plan.board_h)),winner_inputs(*best,plan.accounting.quantization_engagements),"sizing.pass");
        return *best;
    };
    reset_shapes(); const Winner conservative_best=search(false);
    const auto conservative=plan; const auto offers=side_offers;
    plan.accounting.fallback_events=entry_events; reset_shapes();
    std::optional<Winner> free_best;
    try { free_best=search(true); } catch (const FloorplanError&) {}
    Winner best=conservative_best; std::string choice="conservative";
    if (free_best && (std::get<0>(*free_best)<std::get<0>(best)-1e-6 ||
        (std::get<0>(*free_best)<=std::get<0>(best)+1e-6 && std::get<3>(*free_best)<std::get<3>(best)-1e-6))) {
        best=*free_best; choice="free";
    } else {
        restore(conservative); side_offers=offers; plan.accounting.fallback_events=conservative.accounting.fallback_events; fallback("punch_free_plan_rejected");
    }
    calc("plan_choice",jvalue(choice),{{"conservative_area",jvalue(std::get<0>(conservative_best))},
        {"conservative_est",jvalue(precision.value(std::get<3>(conservative_best)))},
        {"free_area",jvalue(free_best ? std::get<0>(*free_best):0.0)},{"free_est",jvalue(free_best ? precision.value(std::get<3>(*free_best)):0.0)}});
    ledger_sides();
    auto wi=winner_inputs(best,plan.accounting.quantization_engagements); wi.emplace_back("plan",jvalue(choice));
    calc("sizing_winner",jvalue(outline_text(plan.board_w,plan.board_h)),std::move(wi));
    std::string aspect_text;
    for (double a:aspects) { if (!aspect_text.empty()) aspect_text+=", "; aspect_text+=number(a); }
    plan.outline_note=seed_note+"; then SMALLEST-AREA search over aspects "+aspect_text+" -> "+outline_text(plan.board_w,plan.board_h)+
        " mm (the smallest board holding the REAL 2-sided packed blocks with the estimated cross-subsystem airwire "+number(std::get<3>(best),0)+
        " <= LAW-5 budget "+number(std::get<4>(best),0)+" mm — honest routing headroom, the gate is not relaxed), SoM "+
        outline_text(plan.som.w,plan.som.h)+" centered";
    return std::move(plan);
}
}  // namespace schgen::floorplan_detail

namespace schgen {
FloorplanPlan build_floorplan(const FloorplanInput& input) { return floorplan_detail::Engine(input).run(); }
}  // namespace schgen
