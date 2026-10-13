// Includes the owned implementation for focused final-rounded trial checks.
// Link schgen_core, but do not compile moves.cpp separately for this target.
#include "schgen/board_inputs.hpp"
#include "schgen/netlist_gate.hpp"
#include "fresh_project_schematic.hpp"
#include "schgen/native_audit_state.hpp"
#include "../src/pcb_placement_moves.cpp"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <unistd.h>

namespace {
using namespace schgen;
using namespace schgen::pcb_placement;
int checks = 0;
void require(bool value, const char* message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}
struct Fixture {
    PcbPlacementInput in;
    PcbZoneResult zones;
    FloorplanStage stage;
    std::unique_ptr<Placer> p;
    std::string sheet;
    Fixture(const PcbPlacementInput& source, std::string name, bool compact)
        : in(source), sheet(std::move(name)) {
        in.floorplan.compact_search = compact;
        const auto evidence = in.owned_groups.at(sheet);
        in.owned_groups = {{sheet,evidence}};
        in.contracts.clear();
        in.floorplan.project.wired_sheets.clear();
        in.floorplan.project.pilot_prox_sheets.clear();
        in.floorplan.module_offset = FloorplanPoint{0,0};
        in.floorplan.project.module_offset = {0,0};
        in.floorplan.place_clear = .5;
        in.netlist.clear();
        stage.plan.board_w = stage.plan.board_h = 120;
        stage.plan.som_x = 80; stage.plan.som_y = 22;
        p = std::make_unique<Placer>(in,zones,stage);
        p->geometry = {};
        p->ctx.pool.clear();
        p->ctx.by_ref.clear();
        p->origins[sheet] = {};
        FloorplanBlock block;block.name=sheet;block.w=block.h=120;
        stage.plan.interior_blocks.push_back(block);
    }
    void part(const std::string& ref, double x, double y, const std::string& side,
              const std::string& footprint = "cap", const std::string& pin = "1") {
        const std::set<std::string> pads{"1","2",pin};
        std::string bytes = "(footprint probe (layer F.Cu)"
            " (fp_rect (start -1 -1) (end 1 1) (stroke (width 0.05) (type default)) (layer F.CrtYd))";
        for (const auto& name : pads)
            bytes += " (pad \"" + name + "\" smd rect (at 0 0) (size 0.2 0.2) (layers F.Cu F.Mask))";
        bytes += ")";
        p->ctx.by_ref[ref] = {ref,ref,sheet,footprint,footprint,footprint};
        p->ctx.pool[ref] = pcb_check_footprint(footprint,bytes);
        p->geometry.resolvable[ref] = ref;
        p->geometry.bbox_of[ref] = {-1,-1,1,1};
        p->geometry.side_of[ref] = side;
        if (footprint == "anchor") p->geometry.conn_rot[ref] = 0;
        p->geometry.refs_by_sheet[sheet].push_back(ref);
        (side=="bottom" ? p->geometry.bot_off : p->geometry.top_off)[sheet][ref] = {x,y};
        p->pos[ref] = {x,y};
        p->grid_placed.insert(ref);
    }
    const std::vector<OwnedCapPlacement>& rows() const {
        return owned_group_placements(*in.owned_groups.at(sheet));
    }
    void wire(const std::string& cap, const std::string& anchor, const std::string& net) {
        in.netlist.push_back({net,{{cap,"1"},{anchor,"1"}}});
        p->pin_net[{cap,"1"}] = {1,net};
        p->pin_net[{anchor,"1"}] = {1,net};
    }
    void l4(bool opposite) {
        const auto row = rows().front();
        part(row.owner,20,20,opposite?"top":"bottom","owner",row.owner_pin);
        part(row.cap,23,20,"bottom");
        part("C_FREE1",20,24,"bottom");
        part("C_FREE2",23,24,"bottom");
    }
    void reorder_case(const std::string& side) {
        int n=0;
        for (const auto& row : rows()) {
            if (!p->pos.count(row.owner))
                part(row.owner,15+20*n,40,side,"owner",row.owner_pin);
            part(row.cap,20+3*n,20,side);
            const auto anchor="J_ANCHOR"+std::to_string(n);
            part(anchor,32-3*n,40,side,"anchor");
            wire(row.cap,anchor,"rail"+std::to_string(n));
            ++n;
        }
        part("C_FREE1",20,60,side);
        part("C_FREE2",23,60,side);
        part("J_FREE1",23,80,side,"anchor");
        part("J_FREE2",20,80,side,"anchor");
        wire("C_FREE1","J_FREE1","free1");
        wire("C_FREE2","J_FREE2","free2");
    }
};

Box4 setup(Fixture& f,const PcbPlacementInput& source,bool independent=false) {
    const auto row=f.rows().front();
    f.part("J_CORRIDOR",50,50,"top","connector");
    f.p->ctx.pool["J_CORRIDOR"]=source.return_path_footprints.begin()->second;
    f.p->ctx.by_ref["J_CORRIDOR"].sheet="som_j1";
    f.p->som_refs["J_CORRIDOR"]="J1";
    const auto c=pcb_escape_corridor_board(*f.p->mod("J_CORRIDOR"),50,50,0);
    const double x=(c.x0+c.x1)/2,y=(c.y0+c.y1)/2;
    f.part(row.owner,x,independent?y+12:y,"top","owner",row.owner_pin);
    f.part(row.cap,x,y,"bottom","cap",row.cap_pin);
    return c;
}
double actual_gap(Fixture& f) {
    const auto check=refit_fanout_geometry(*f.p,nullptr);
    return evict_gap(check,evict_index(check),f.rows().front());
}
void cleared(Fixture& f,Box4 corridor) {
    const auto check=refit_fanout_geometry(*f.p,nullptr);
    for(const auto& [r,i]:evict_index(check))
        if(f.p->side(r)=="bottom")require(!rects_intersect_open(evict_box(check,i),corridor),"corridor still blocked");
}
AuditCounts import_actual(const Fixture& f) {
    NativeQuantizations quantizations;register_native_quantizations(quantizations);
    NativeFallbacks fallbacks;register_native_fallbacks(fallbacks);
    NativeAccountingInbox inbox(quantizations,fallbacks);
    const ExecutionAccounting receipt{f.p->ctx.quantization,f.p->out.placement_accounting.fallback_events};
    require(inbox.merge_once("test/eviction",receipt),"actual receipt did not import");
    require(!inbox.merge_once("test/eviction",receipt),"identical receipt imported twice");
    for(const auto& [name,n]:receipt.quantization_engagements)
        require(quantizations.engagements().at(name)==AuditInteger::decimal(std::to_string(n)),
                "actual precision work lost on import");
    const auto census=fallbacks.census();
    require(!census.count("corridor_evict_owned_rigid") && !census.count("corridor_evict_rejected"),
            "unapproved names entered runtime registry");
    for(const auto& [name,n]:census)
        require(n==AuditInteger(std::count(receipt.fallback_events.begin(),receipt.fallback_events.end(),name)),
                "actual fallback receipt mismatch");
    require(f.p->out.fallback_events==receipt.fallback_events,"legacy and placement event streams differ");
    return census;
}
void reject(Fixture& f) {
    const auto before=f.p->pos;const auto counts=f.p->ctx.quantization;
    bool failed=false;
    try {f.p->evict();} catch(const PcbZoneInfeasible&){failed=true;}
    require(failed && f.p->pos==before,"unsafe candidate did not reject/rollback");
    require(f.p->ctx.quantization!=counts,"rejection lost actual work");
    require(f.p->out.placement_accounting.fallback_events.back()=="corridor_stray_unmovable",
            "failure event missing from receipt");
    require(import_actual(f).at("corridor_stray_unmovable")==AuditInteger(1),
            "explicit obstruction rejection not counted exactly once");
}

void safety_checks(const PcbPlacementInput& source) {
    Fixture f(source,"bringup_rails",true);
    const auto row=f.rows().front();
    f.part(row.owner,20,20,"top","owner",row.owner_pin);
    f.part(row.cap,20,20,"bottom","cap",row.cap_pin);
    const EvictRows rows{row};
    const std::set<std::string> group{row.owner,row.cap};
    const auto legal=[&](const PcbStageRefitPoses& trial,const std::vector<Box4>& corridors=std::vector<Box4>{}) {
        const auto before=refit_fanout_geometry(*f.p,nullptr),after=refit_fanout_geometry(*f.p,&trial);
        return evict_legal(*f.p,before,after,group,rows,corridors,true);
    };
    const PcbStageRefitPoses trial{{row.owner,{30,30,0}},{row.cap,{30,30,0}}};
    require(legal(trial),"legal opposite-face SMD rigid trial rejected");
    auto worsened=trial;
    // Pads overlap at zero gap, so move beyond their complete width.
    worsened[row.cap]={30.3,30,0};
    require(!legal(worsened),"named owner/cap gap increase accepted");
    require(!legal(trial,{{29,29,31,31}}),"a different corridor accepted");
    require(!legal({{row.owner,{.5,30,0}},{row.cap,{.5,30,0}}}),"offboard trial accepted");
    f.p->keepout={29,29,31,31};
    require(!legal(trial),"top keepout accepted");
    f.p->keepout={};
    f.part("R_OBSTACLE",30,30,"bottom");
    require(!legal(trial),"external same-face collision accepted");
    // An external THT blocks the opposite face as well.
    f.p->geometry.side_of["R_OBSTACLE"]="top";
    f.p->ctx.pool["R_OBSTACLE"]=pcb_check_footprint("tht",
        "(footprint tht (layer F.Cu) (fp_rect (start -1 -1) (end 1 1) (stroke (width .05) (type default)) (layer F.CrtYd))"
        " (pad \"1\" thru_hole circle (at 0 0) (size .2 .2) (drill .1) (layers *.Cu *.Mask)))");
    require(has_thru_pads_from_text(f.p->mod("R_OBSTACLE")->bytes),"THT fixture not recognized");
    const auto before=refit_fanout_geometry(*f.p,nullptr),after=refit_fanout_geometry(*f.p,&trial);
    require(!evict_legal(*f.p,before,after,{row.cap},rows,{},false),"opposite-face external THT accepted");
    f.p->pos.erase("R_OBSTACLE");
    // Rounded internal separation, independent of ownership gap improvement:
    // raw 2.500050 centre spacing - 2.000040 extents is legal; emitted
    // 2.500000 spacing yields .499960, and must be rejected.
    f.p->geometry.side_of[row.owner]="bottom";
    for(const auto& r:group) {
        const auto pin=r==row.owner?row.owner_pin:row.cap_pin;
        f.p->ctx.pool[r]=pcb_check_footprint("rounded",
            "(footprint rounded (layer F.Cu) (fp_rect (start -1.00002 -1.00002) (end 1.00002 1.00002)"
            " (stroke (width .05) (type default)) (layer F.CrtYd))"
            " (pad \""+pin+"\" smd rect (at 0 0) (size .2 .2) (layers F.Cu F.Mask)))");
        auto exact=std::make_shared<PcbCheckFootprint>(*f.p->mod(r));
        exact->bbox=Box4{-1.00002,-1.00002,1.00002,1.00002};
        f.p->ctx.pool[r]=exact;
    }
    f.p->pos[row.owner]={20,20};f.p->pos[row.cap]={23,20};
    const PcbStageRefitPoses rounded{{row.owner,{30.000051,30,0}},{row.cap,{32.500101,30,0}}};
    const auto emitted=refit_fanout_geometry(*f.p,&rounded);
    const auto ei=evict_index(emitted);
    const double rounded_separation=evict_box(emitted,ei.at(row.cap)).x0-evict_box(emitted,ei.at(row.owner)).x1;
    require(32.500101-30.000051-2.00004>f.p->ctx.clearance &&
            rounded_separation<f.p->ctx.clearance,"rounding fixture does not cross clearance threshold");
    std::cout<<"ROUNDING internal separation "<<rounded_separation<<" < "<<f.p->ctx.clearance<<'\n';
    require(!legal(rounded),"rounding-created internal clearance violation accepted");
    // Mixed-face internal THT also requires that same signed separation.
    f.p->geometry.side_of[row.owner]="top";
    const auto pin=row.owner_pin;
    f.p->ctx.pool[row.owner]=pcb_check_footprint("tht",
        "(footprint tht (layer F.Cu) (fp_rect (start -1.00002 -1.00002) (end 1.00002 1.00002)"
        " (stroke (width .05) (type default)) (layer F.CrtYd))"
        " (pad \""+pin+"\" thru_hole circle (at 0 0) (size .2 .2) (drill .1) (layers *.Cu *.Mask)))");
    auto exact_tht=std::make_shared<PcbCheckFootprint>(*f.p->mod(row.owner));
    exact_tht->bbox=Box4{-1.00002,-1.00002,1.00002,1.00002};
    f.p->ctx.pool[row.owner]=exact_tht;
    require(!legal(rounded),"rounding-created internal mixed-face THT violation accepted");
    // Fanout: courtyard separation .6 is legal for spacing, but starves a
    // three-pin foreign subject. A gap-preserving translation must still fail.
    Fixture g(source,"bringup_rails",true);
    g.part(row.owner,20,20,"top","owner",row.owner_pin);
    g.part(row.cap,20,20,"bottom","cap",row.cap_pin);
    g.part("U_SUBJECT",32.6,30,"bottom","subject","3");
    g.p->ctx.by_ref["U_SUBJECT"].sheet="foreign_subject";
    const auto gb=refit_fanout_geometry(*g.p,nullptr),ga=refit_fanout_geometry(*g.p,&trial);
    require(!evict_legal(*g.p,gb,ga,group,rows,{},true),"foreign fanout starvation accepted");
}

void top_shadow_contract(const PcbPlacementInput& source) {
    Fixture f(source,"bringup_rails",true);
    const auto c=setup(f,source);
    const auto row=f.rows().front();
    f.p->pos.erase(row.owner);f.p->pos.erase(row.cap);f.in.owned_groups.clear();
    const double x=(c.x0+c.x1)/2,y=(c.y0+c.y1)/2;
    f.part("J_TOP_SHADOW",x,y,"top","tht");
    f.p->ctx.pool["J_TOP_SHADOW"]=pcb_check_footprint("tht",
        "(footprint tht (layer F.Cu) (fp_rect (start -1 -1) (end 1 1) (stroke (width .05) (type default)) (layer F.CrtYd))"
        " (pad \"1\" thru_hole circle (at 0 0) (size .2 .2) (drill .1) (layers *.Cu *.Mask)))");
    require(has_thru_pads_from_text(f.p->mod("J_TOP_SHADOW")->bytes),"top THT fixture not recognized");
    f.p->fixed.insert("J_TOP_SHADOW");
    reject(f); // With the old bottom-only scans this silently succeeded.
    // Ordinary top SMD does not occupy the bottom escape corridor.
    f.part("J_TOP_SHADOW",x,y,"top","smd");
    const auto unchanged=f.p->pos;
    f.p->evict();
    require(f.p->pos==unchanged,"top SMD-only corridor occupancy was moved");
    // Missing bbox must reject before any optional dereference.
    auto missing=std::make_shared<PcbCheckFootprint>(*f.p->mod("J_TOP_SHADOW"));
    missing->bbox.reset();f.p->ctx.pool["J_TOP_SHADOW"]=missing;
    const auto input=refit_fanout_geometry(*f.p,nullptr);
    bool failed=false;
    try { (void)evict_box(input,evict_index(input).at("J_TOP_SHADOW")); }
    catch(const PcbZoneInfeasible&){failed=true;}
    require(failed,"missing footprint bbox not rejected");
}

void source_anchor_contract(const PcbPlacementInput& source) {
    const Context live(source);
    int anchors=0;
    for(const auto& part:live.parts) if(part.sheet.rfind("som_j",0)==0) {
        const auto fp=live.resolve(part.footprint);
        require(fp && !has_thru_pads_from_text(fp->bytes),
                "live escape anchor is not the expected SMT footprint");
        ++anchors;
    }
    require(anchors>0,"live source anchor population missing");
    std::cout<<"LIVE SMT escape anchors "<<anchors<<'\n';
    Fixture f(source,"bringup_rails",true);
    setup(f,source);
    const auto row=f.rows().front();
    f.p->pos.erase(row.owner);f.p->pos.erase(row.cap);f.in.owned_groups.clear();
    auto bytes=f.p->mod("J_CORRIDOR")->bytes;
    bytes.insert(bytes.find_last_of(')'),
        " (pad \"THT_PROBE\" thru_hole circle (at 0 0) (size .2 .2) (drill .1) (layers *.Cu *.Mask)) ");
    f.p->ctx.pool["J_CORRIDOR"]=pcb_check_footprint("hypothetical_tht_source",bytes);
    const auto check=refit_fanout_geometry(*f.p,nullptr);
    const auto i=evict_index(check).at("J_CORRIDOR");
    const auto c=pcb_escape_corridor_board(*f.p->mod("J_CORRIDOR"),50,50,0);
    require(rects_intersect_open(evict_box(check,i),c),"source self-overlap fixture missing");
    require(!evict_movable(*f.p,"J_CORRIDOR"),"source anchor gained movement permission");
    reject(f); // No automatic own-source exception without pad/net/window proof.
}

void error_accounting(const PcbPlacementInput& source) {
    for(bool overflow:{false,true}) {
        Fixture f(source,"bringup_rails",true);setup(f,source);
        const auto cap=f.rows().front().cap;
        if(overflow)f.p->ctx.quantization["placement_emission_pose_precision4dp"]=
            std::numeric_limits<std::size_t>::max();
        else {
            auto malformed=std::make_shared<PcbCheckFootprint>(*f.p->mod(cap));
            malformed->bbox.reset();f.p->ctx.pool[cap]=malformed;
        }
        const auto entry=f.p->pos;
        bool failed=false;
        try {f.p->evict();}
        catch(const std::overflow_error&) {require(overflow,"wrong error classification");failed=true;}
        catch(const PcbZoneInfeasible& e) {
            require(!overflow && std::string(e.what()).find("missing actual footprint bbox")!=std::string::npos,
                    "malformed geometry masqueraded as no legal exit");
            failed=true;
        }
        require(failed && f.p->pos==entry,"exception did not preserve entry geometry");
        require(f.p->out.fallback_events.empty() && f.p->out.placement_accounting.fallback_events.empty(),
                "malformed/overflow fabricated an obstruction fallback");
        if(overflow)
            require(f.p->ctx.quantization.at("placement_emission_pose_precision4dp")==
                    std::numeric_limits<std::size_t>::max(),"overflow counter altered");
        else (void)import_actual(f);
    }
}
std::string read_bytes(const std::filesystem::path& path) {
    std::ifstream stream(path,std::ios::binary);
    if(!stream)throw std::runtime_error("cannot read baseline");
    return {std::istreambuf_iterator<char>(stream),std::istreambuf_iterator<char>()};
}
void unchanged_ceilings(const PcbPlacementInput& source,const std::filesystem::path& root) {
    char name[]="/private/tmp/evict-ratchet-contracts.XXXXXX";
    const auto made=mkdtemp(name);
    if(!made)throw std::runtime_error("mkdtemp failed");
    const std::filesystem::path scratch=made;
    Fixture actual(source,"bringup_rails",true);setup(actual,source);
    actual.p->evict();const auto actual_counts=import_actual(actual);
    for(const auto& project:{"carrier","devkit_mini"}) {
        const auto baseline=root/project/"reports/fallback_baseline.json";
        const auto bytes=read_bytes(baseline);
        const auto ceiling=load_fallback_baseline(baseline);
        require(ceiling.has_value(),"authoritative ceiling absent; do not auto-pin");
        const auto out=scratch/(std::string(project)+".json");
        const auto at=check_fallback_ratchet(*ceiling,baseline,out);
        require(at.ok && !at.pinned,"unchanged existing ceilings did not pass");
        auto above=*ceiling;
        const auto moved=std::stoll(ceiling->at("corridor_evict_moved").str());
        above["corridor_evict_moved"]=AuditInteger(moved+1);
        const auto failout=scratch/(std::string(project)+"-exceeded.json");
        require(!check_fallback_ratchet(above,baseline,failout).ok &&
                !std::filesystem::exists(failout),"existing moved ceiling waived or failed result published");
        above=*ceiling;above["corridor_stray_unmovable"]=AuditInteger(1);
        require(ceiling->at("corridor_stray_unmovable")==AuditInteger(0) &&
                !check_fallback_ratchet(above,baseline,failout).ok,"unmovable zero ceiling waived");
        if(std::string(project)=="carrier")
            require(!check_fallback_ratchet(actual_counts,baseline,failout).ok,
                    "real rigid relocation bypassed carrier zero moved ceiling");
        require(read_bytes(baseline)==bytes,"authoritative baseline bytes changed");
    }
    std::cout<<"RATCHET unchanged source ceilings; isolated outputs "<<scratch<<'\n';
}
void l4_corridor_contract(const PcbPlacementInput& source) {
    for (bool compact : {false,true}) {
        Fixture f(source,"bringup_rails",compact);
        f.part("J_CORRIDOR",50,50,"top","connector");
        f.p->ctx.pool["J_CORRIDOR"]=source.return_path_footprints.begin()->second;
        f.p->ctx.by_ref["J_CORRIDOR"].sheet="som_j1";
        f.p->geometry.top_off[f.sheet].erase("J_CORRIDOR");
        f.p->som_refs["J_CORRIDOR"]="J1";
        const auto corridor=pcb_escape_corridor_board(*f.p->mod("J_CORRIDOR"),50,50,0);
        const double cx=(corridor.x0+corridor.x1)/2, cy=(corridor.y0+corridor.y1)/2;
        const bool vertical=corridor.x1-corridor.x0<corridor.y1-corridor.y0;
        // Make the centroid pull point into the narrow corridor. The two
        // independent passives remain separated and clear of the top connector.
        f.stage.plan.som_x=cx;f.stage.plan.som_y=cy;
        f.stage.plan.som.w=f.stage.plan.som.h=0;
        for(int side : {-1,1})
            f.part(side<0?"C_FREE1":"C_FREE2",vertical?corridor.x0-5:cx+side*5,
                   vertical?cy+side*5:corridor.y0-5,"bottom");
        const auto before=f.p->pos;
        f.p->l4_pull();
        const auto actual=refit_fanout_geometry(*f.p,nullptr);
        const auto index=evict_index(actual);
        int obstructions=0;
        for(const auto* ref : {"C_FREE1","C_FREE2"})
            obstructions+=rects_intersect_open(evict_box(actual,index.at(ref)),corridor);
        std::cout<<"L4 corridor compact="<<compact<<" moved="<<(f.p->pos!=before)
            <<" obstructions="<<obstructions<<" corridor="<<corridor.x0<<","<<corridor.y0<<","<<corridor.x1<<","<<corridor.y1<<"\n";
        require(f.p->pos!=before,"corridor protection disabled all useful pulling");
        require(compact?obstructions==0:obstructions>0,
                "compact L4 must protect corridors at zero offset and 0.5mm clearance; default control stays unchanged");
    }
}
void tests(const PcbPlacementInput& source,const std::filesystem::path& root) {
    {
        Fixture f(source,"bringup_rails",true);
        f.part("R_FREE1",20,20,"bottom");
        f.part("R_FREE2",22.25,20,"bottom");
        const auto before=refit_fanout_geometry(*f.p,nullptr);
        const auto legal=[&](double x,MovementFrame frame) {
            PcbStageRefitPoses pose{{"R_FREE1",{x,20,0}}};
            const auto after=refit_fanout_geometry(*f.p,&pose);
            return evict_legal(*f.p,before,after,{"R_FREE1"},{},{},false,nullptr,frame);
        };
        require(!legal(19.9,MovementFrame::CorridorAllocation),"allocation repair retains its absolute gap policy");
        require(legal(19.9,MovementFrame::FinalFrameNonregression),"thermal repair may improve an existing tight gap");
        require(!legal(20.1,MovementFrame::FinalFrameNonregression),"thermal repair may not worsen an existing tight gap");
        require(legal(19.75,MovementFrame::FinalFrameNonregression),"full nominal clearance recovery is allowed");
        f.p->pos["R_FREE2"]={23,20};
        const auto clear=refit_fanout_geometry(*f.p,nullptr);
        PcbStageRefitPoses pose{{"R_FREE1",{20.6,20,0}}};
        require(!evict_legal(*f.p,clear,refit_fanout_geometry(*f.p,&pose),{"R_FREE1"},{},{},false,nullptr,
                            MovementFrame::FinalFrameNonregression),"thermal repair may not create a new undersized gap");
    }
    {
        Fixture f(source,"bringup_rails",true);
        std::vector<std::string> outcomes;
        auto observer=std::make_shared<PcbPlacementExperiment>();
        observer->thermal_trial=[&](const auto& ref,double x,double y,const auto& outcome) {
            require(ref=="R_BLOCKER" && std::isfinite(x) && std::isfinite(y),
                    "thermal diagnostic carries actual mover and finite trial pose");
            outcomes.push_back(outcome);
        };
        f.in.experiment=observer;
        f.part("U_THERMAL",50,50,"top");
        f.p->ctx.by_ref.at("U_THERMAL").value="TLV75725";
        f.part("R_BLOCKER",60,50,"bottom");
        f.p->ctx.pool["R_BLOCKER"]=pcb_check_footprint("wide-blocker",
            "(footprint wide (layer F.Cu)"
            " (fp_rect (start -4 -2) (end 4 2) (stroke (width 0.05) (type default)) (layer F.CrtYd))"
            " (pad 1 smd rect (at 0 0) (size 8 4) (layers F.Cu F.Mask)))");
        f.p->net_numbers={{"GND",1},{"SIGNAL",2}};
        f.p->pin_net[{"R_BLOCKER","1"}]={2,"SIGNAL"};
        const auto before=refit_fanout_geometry(*f.p,nullptr);
        PcbStageRefitPoses bad{{"R_BLOCKER",{50,50,0}}};
        const auto after=refit_fanout_geometry(*f.p,&bad);
        const auto policy=pcb_emit_policy(f.in.floorplan.project);
        const auto prior=plan_preferred_thermal_vias(before.model(),policy);
        const auto blocked=plan_preferred_thermal_vias(after.model(),policy);
        require(prior.size()==1 && prior.front().sites.chosen.size()==3 &&
                blocked.front().sites.chosen.empty(),"thermal eviction fixture must consume real preferred sites");
        require(evict_legal(*f.p,before,before,{"R_BLOCKER"},{},{},false),
                "thermal guard must retain a legal unchanged move");
        std::string rejection;
        require(!evict_legal(*f.p,before,after,{"R_BLOCKER"},{},{},false,&rejection),
                "opposite-face corridor eviction may not consume preferred thermal capacity");
        require(rejection=="thermal_regression","thermal failure reports the actual constraint");
        require(evict_legal(*f.p,after,before,{"R_BLOCKER"},{},{},false),
                "thermal recovery remains legal");
        f.p->pos["R_BLOCKER"]={50,50};
        const auto blocked_pose=f.p->pos;
        f.p->fixed.insert("R_BLOCKER");
        compact_recover_thermal(*f.p);
        require(f.p->pos==blocked_pose,"thermal repair must not move a fixed blocker");
        f.p->fixed.erase("R_BLOCKER");
        // Earlier stages may legally move secondary parts outside this initial
        // packing allocation. It is not a hardware keepout for thermal repair.
        f.stage.plan.interior_blocks.front().w=20;
        f.stage.plan.interior_blocks.front().h=20;
        require(!thermal_pad_move_candidates(after.model(),policy,blocked).empty(),
                "blocked pad must produce identity-resolved thermal proposals");
        compact_recover_thermal(*f.p);
        const auto recovered=plan_preferred_thermal_vias(
            refit_fanout_geometry(*f.p,nullptr).model(),policy);
        std::cout<<"thermal repair recovered="<<recovered.front().sites.chosen.size()
            <<" blocker="<<f.p->pos.at("R_BLOCKER").first<<","<<f.p->pos.at("R_BLOCKER").second
            <<" events="<<f.p->out.fallback_events.size()<<'\n';
        require(recovered.front().sites.chosen.size()==3,
                "production thermal repair must recover preferred sites");
        require(f.p->pos.at("U_THERMAL")==blocked_pose.at("U_THERMAL"),
                "thermal subject stays in place while its blocker moves");
        require(std::count(f.p->out.fallback_events.begin(),f.p->out.fallback_events.end(),
                           "thermal_repair_moved")>0,"thermal repair must retain accepted work receipts");
        const auto recovered_pose=f.p->pos;
        compact_recover_thermal(*f.p);
        require(f.p->pos==recovered_pose,"complete field must not cause gratuitous movement");
        import_actual(f);
        const auto count=[&](const auto* name) {
            return std::count(f.p->out.fallback_events.begin(),f.p->out.fallback_events.end(),name);
        };
        require(count("thermal_repair_trial")==
                count("thermal_repair_moved")+count("thermal_repair_rejected"),
                "every executed thermal trial has exactly one terminal outcome");
        require(outcomes.size()==static_cast<std::size_t>(count("thermal_repair_trial")) &&
                std::count(outcomes.begin(),outcomes.end(),"accepted")==count("thermal_repair_moved"),
                "diagnostic outcomes reconcile with independent execution receipts");
        f.p->pos["R_BLOCKER"]={50,50};
        f.part("R_PARTNER",50,56,"bottom");
        f.p->ctx.by_ref.at("U_THERMAL").sheet="thermal_subject";
        f.p->ctx.board_refs[f.sheet]={{"R1","R_BLOCKER"},{"R2","R_PARTNER"}};
        f.in.contracts[f.sheet]=parse_json_text(R"({"contract":"placement/lightweight-v0","structures":[
            {"type":"proximity","anchor":"R1","anchor_pins":["1"],"members":["R2"],"max_mm":10,"same_side":true}]})");
        f.p->ctx.wired.insert(f.sheet);
        f.p->contract_members.insert("R_BLOCKER");
        f.p->contract_members.insert("R_PARTNER");
        const auto group_entry=f.p->pos;
        f.p->fixed.insert("R_PARTNER");
        compact_recover_thermal(*f.p);
        require(f.p->pos==group_entry,"fixed member cannot be moved by contract-group association");
        f.p->fixed.erase("R_PARTNER");
        compact_recover_thermal(*f.p);
        require(f.p->pos.at("R_BLOCKER")!=group_entry.at("R_BLOCKER") &&
                f.p->pos.at("R_PARTNER")!=group_entry.at("R_PARTNER"),
                "protected thermal blocker must recover by moving its complete contract group");
        const auto a=f.p->pos.at("R_BLOCKER"), b=f.p->pos.at("R_PARTNER");
        require(a.first==b.first && b.second-a.second==6,
                "contract-group translation preserves the internal arrangement");
        require(plan_preferred_thermal_vias(refit_fanout_geometry(*f.p,nullptr).model(),policy)
                    .front().sites.chosen.size()==3,"contract-group translation recovers thermal capacity");
        import_actual(f);
    }
    {
        Fixture f(source,"bringup_rails",true);
        f.part("R_A",50,50,"bottom");f.part("R_B",54,50,"bottom");
        auto before=refit_fanout_geometry(*f.p,nullptr);
        require(thermal_contact_group(*f.p,before,"R_A",4,0,{})==std::set<std::string>{"R_A","R_B"},
                "thermal contact closure includes collided neighbour");
        f.part("R_C",58,50,"bottom");before=refit_fanout_geometry(*f.p,nullptr);
        require(thermal_contact_group(*f.p,before,"R_A",4,0,{})==std::set<std::string>{"R_A","R_B","R_C"},
                "thermal contact closure follows transitive collisions");
        const PcbStageRefitPoses single{{"R_A",{54,50,0}}};
        const PcbStageRefitPoses translated{{"R_A",{54,50,0}},{"R_B",{58,50,0}},{"R_C",{62,50,0}}};
        require(!evict_legal(*f.p,before,refit_fanout_geometry(*f.p,&single),{"R_A"},{},{},false,nullptr,
                    MovementFrame::FinalFrameNonregression),"individual thermal contact move really collides");
        require(evict_legal(*f.p,before,refit_fanout_geometry(*f.p,&translated),{"R_A","R_B","R_C"},{},{},false,nullptr,
                    MovementFrame::FinalFrameNonregression,true),"complete rigid contact move passes unchanged geometry gates");
        f.p->fixed.insert("R_C");
        require(thermal_contact_group(*f.p,before,"R_A",4,0,{}).empty(),"contact closure cannot move fixed neighbour");
        f.p->fixed.erase("R_C");
        require(thermal_contact_group(*f.p,before,"R_A",4,0,{"R_B"}).empty(),"contact closure protects owned members");
        f.p->ctx.by_ref.at("R_C").sheet="other";
        require(thermal_contact_group(*f.p,before,"R_A",4,0,{}).empty(),"contact closure cannot absorb another subsystem");
        require(thermal_contact_group(*f.p,before,"R_A",0,0,{})==std::set<std::string>{"R_A"},
                "unchanged pose requires no contact expansion");
    }
    l4_corridor_contract(source);
    error_accounting(source);
    unchanged_ceilings(source,root);
    source_anchor_contract(source);
    top_shadow_contract(source);
    safety_checks(source);
    for(bool independent:{false,true}) {
        Fixture f(source,"bringup_rails",true);const auto corridor=setup(f,source,independent);
        const auto before=f.p->pos;const auto row=f.rows().front();const double gap=actual_gap(f);
        const auto sides=f.p->geometry.side_of;
        const auto rotations=f.p->rotations;
        f.p->evict();cleared(f,corridor);
        require(import_actual(f).at("corridor_evict_moved")==AuditInteger(independent?1:2),
                "rigid group was not counted per moved member");
        require(actual_gap(f)<=gap,"actual rounded ownership gap increased");
        require(f.p->pos.at(row.cap)!=before.at(row.cap),"stray cap not moved");
        require((f.p->pos.at(row.owner)==before.at(row.owner))==independent,
                "wrong independent/rigid resolution");
        require(f.p->geometry.side_of==sides && f.p->rotations==rotations,"face/rotation changed");
        std::cout<<(independent?"INDEPENDENT":"RIGID")<<" gap "<<gap<<" -> "<<actual_gap(f)<<"\n";
    }
    // Fixed/contracted owner must not be moved by association or abandoned.
    for(int lock=0;lock<7;++lock) {
        Fixture f(source,"bringup_rails",true);setup(f,source);const auto row=f.rows().front();
        if(lock==0)f.p->fixed.insert(row.owner);
        if(lock==1)f.p->contract_members.insert(row.owner);
        if(lock==2)f.p->geometry.conn_edge[row.owner]="N";
        if(lock==3) {
            f.in.floorplan.project.wired_sheets={f.sheet};
            const Context eligibility(f.in);
            require(eligibility.l4_exempt.count(f.sheet) &&
                    !eligibility.l4_exempt.count(row.owner),"L4 exemption domain fixture incorrect");
            f.p->ctx.l4_exempt=eligibility.l4_exempt;
        }
        if(lock==4)f.p->grid_placed.erase(row.owner);
        if(lock==5)f.stage.plan.interior_blocks.clear();
        if(lock==6){f.p->ctx.wired.insert(f.sheet);f.in.contracts[f.sheet]=JsonNode{};}
        reject(f);
    }
    // Allocated bbox, not board-only permission; no outside-seat escape.
    {
        Fixture f(source,"bringup_rails",true);const auto c=setup(f,source);
        auto& block=f.stage.plan.interior_blocks.front();
        block.x=c.x0;block.y=c.y0;block.w=c.x1-c.x0;block.h=c.y1-c.y0;
        reject(f);
    }
    // A late impossible stray rolls back an earlier successful independent move.
    {
        Fixture f(source,"bringup_rails",true);setup(f,source,true);
        const auto cap=f.rows().front().cap;
        f.part("Z_BLOCKED",f.p->pos.at(cap).first+4,f.p->pos.at(cap).second,"bottom");
        f.p->fixed.insert("Z_BLOCKED");
        // Expand second corridor around the fixed stray using the same connector.
        f.part("J_SECOND",54,50,"top","connector");
        f.p->ctx.pool["J_SECOND"]=source.return_path_footprints.begin()->second;
        f.p->ctx.by_ref["J_SECOND"].sheet="som_j2";
        f.p->som_refs["J_SECOND"]="J2";
        reject(f);
        require(std::find(f.p->out.fallback_events.begin(),f.p->out.fallback_events.end(),
                          "corridor_evict_moved")!=f.p->out.fallback_events.end(),
                "late-failure test never exercised an earlier accepted trial");
        require(f.p->out.placement_accounting.fallback_events==std::vector<std::string>{
                    "corridor_evict_moved","corridor_stray_unmovable"},
                "late rollback lost or reordered the actual earlier move event");
    }
    // Default path remains byte/count identical with ownership present/absent.
    {
        Fixture a(source,"bringup_rails",false),b(source,"bringup_rails",false);
        setup(a,source);setup(b,source);b.in.owned_groups.clear();
        a.p->evict();b.p->evict();
        require(a.p->pos==b.p->pos && a.p->ctx.quantization==b.p->ctx.quantization &&
                a.p->out.fallback_events==b.p->out.fallback_events,"default ownership changed legacy");
        require(actual_gap(a)>0,"original gap-loss witness no longer reproduces in default");
    }
}
}
int main(int argc,char**argv) {
    try {
        if(argc!=2)throw std::runtime_error("usage: evict-contracts ROOT");
        const auto paths=schgen::resolve_project_paths(argv[1],"carrier");
        const auto circuits=schgen::load_project_circuits(paths);
        std::vector<schgen::CircuitSheetIr> sheets;
        for(const auto& c:circuits)sheets.push_back(c.circuit);
        const auto link=schgen::link_sheets(sheets,schgen::parse_json_file(paths.som_interface_file.string()),
            schgen::parse_json_file((paths.project_root/"som_mapping.json").string()));
        require(link.ok(),"hierarchy link failed");
        schgen::BoardInputOptions options;options.compact_search=true;
        const auto source=schgen::load_board_inputs(paths,circuits,link,
            schgen::extract_netlist(schgen::test::fresh_project_schematic(paths,circuits)),options);
        tests(source,argv[1]);
        std::cout<<"PASS "<<checks<<" compact eviction checks\n";
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
