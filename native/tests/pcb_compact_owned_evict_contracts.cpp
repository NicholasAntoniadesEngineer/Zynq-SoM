// Includes the owned implementation for focused final-rounded trial checks.
// Link schgen_core, but do not compile moves.cpp separately for this target.
#include "schgen/board_inputs.hpp"
#include "schgen/netlist_gate.hpp"
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
            schgen::extract_netlist(paths.project_root/"Zynq_Carrier.kicad_sch"),options);
        tests(source,argv[1]);
        std::cout<<"PASS "<<checks<<" compact eviction checks\n";
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
