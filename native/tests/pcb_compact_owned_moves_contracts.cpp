#include "schgen/board_inputs.hpp"
#include "schgen/catalog.hpp"
#include "schgen/netlist_gate.hpp"
#include "fresh_project_schematic.hpp"
#include "pcb_placement_internal.hpp"
#include <iostream>

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
void invariant(Fixture& f, const FloorplanOffsets& before,
               const FloorplanRotations& rotations,
               const std::map<std::string,std::string>& sides,
               const decltype(Placer::pin_net)& nets) {
    for (const auto& row : f.rows()) {
        require(f.p->pos.at(row.owner)==before.at(row.owner),"declared owner moved independently");
        require(f.p->pos.at(row.cap)==before.at(row.cap),"declared bypass/bulk capacitor moved independently");
    }
    require(f.p->rotations==rotations && f.p->geometry.side_of==sides && f.p->pin_net==nets,
            "identity, rotation, side or net changed");
}
void tests(const PcbPlacementInput& source) {
    for (bool opposite : {false,true}) {
        Fixture f(source,"bringup_rails",true); f.l4(opposite);
        const auto before=f.p->pos; const auto rot=f.p->rotations;
        const auto sides=f.p->geometry.side_of; const auto nets=f.p->pin_net;
        f.p->l4_pull();
        invariant(f,before,rot,sides,nets);
        require(f.p->pos.at("C_FREE1")!=before.at("C_FREE1") &&
                f.p->pos.at("C_FREE2")!=before.at("C_FREE2"),"L4 froze unrelated same-sheet parts");
        require(f.p->ctx.quantization.at("placement_l4_pose_precision4dp")==4,
                "L4 counts must reflect only the two actual unowned commits");
        Fixture unowned(source,"bringup_rails",true); unowned.l4(opposite);
        const auto cap=unowned.rows().front().cap;
        unowned.in.owned_groups.clear(); unowned.p->l4_pull();
        require(unowned.p->pos.at(cap)!=before.at(cap),"L4 test did not exercise the old ownership regression");
    }
    for (const auto& side : {"top","bottom"}) {
        Fixture f(source,"board_aux",true); f.reorder_case(side);
        const auto before=f.p->pos; const auto rot=f.p->rotations;
        const auto sides=f.p->geometry.side_of; const auto nets=f.p->pin_net;
        f.p->reorder(); invariant(f,before,rot,sides,nets);
        require(f.p->pos.at("C_FREE1")==before.at("C_FREE2") &&
                f.p->pos.at("C_FREE2")==before.at("C_FREE1"),"reorder froze unowned same-sheet slot swap");
        Fixture unowned(source,"board_aux",true); unowned.reorder_case(side);
        const auto rows=unowned.rows(); unowned.in.owned_groups.clear(); unowned.p->reorder();
        bool crossed_owner=false, have_bulk=false;
        for(const auto& r:rows) {
            have_bulk |= r.role==OwnedCapRole::OutputBulk;
            for(const auto& other:rows)
                crossed_owner |= r.owner!=other.owner && unowned.p->pos.at(r.cap)==before.at(other.cap);
        }
        require(crossed_owner,"reorder test did not exercise cross-owner cap slot regression");
        require(have_bulk,"bulk role must be covered without acquiring bypass movement permission");
    }
    for (bool reorder : {false,true}) {
        Fixture legacy(source,reorder?"board_aux":"bringup_rails",false);
        Fixture empty(source,reorder?"board_aux":"bringup_rails",false);
        if(reorder){legacy.reorder_case("bottom");empty.reorder_case("bottom");}
        else{legacy.l4(false);empty.l4(false);}
        empty.in.owned_groups.clear();
        if(reorder){legacy.p->reorder();empty.p->reorder();}
        else{legacy.p->l4_pull();empty.p->l4_pull();}
        require(legacy.p->pos==empty.p->pos && legacy.p->ctx.quantization==empty.p->ctx.quantization,
                "default attached/absent ownership differs");
        for(int bad=0;bad<3;++bad) {
            Fixture f(source,"bringup_rails",true); f.l4(false);
            const auto row=f.rows().front();
            if(bad==0)f.p->pos.erase(row.cap);
            if(bad==1)f.in.owned_groups[f.sheet]=nullptr;
            if(bad==2)f.p->ctx.by_ref.at(row.cap).sheet="foreign";
            const auto before=f.p->pos;bool rejected=false;
            try {if(reorder)f.p->reorder();else f.p->l4_pull();}
            catch(const std::exception&){rejected=true;}
            require(rejected && f.p->pos==before,"invalid ownership did not reject atomically");
        }
    }
}
// Regression: without a sheet allocation, ownership-preserving corridor repair
// cannot establish its leash and must fail explicitly, without geometry loss.
void eviction_risk(const PcbPlacementInput& source) {
    Fixture f(source,"bringup_rails",true);
    const auto row=f.rows().front();
    f.part("J_CORRIDOR",50,50,"top","connector");
    f.p->ctx.pool["J_CORRIDOR"]=source.return_path_footprints.begin()->second;
    f.p->som_refs["J_CORRIDOR"]="J1";
    const auto corridor=pcb_escape_corridor_board(*f.p->mod("J_CORRIDOR"),50,50,0);
    const double x=(corridor.x0+corridor.x1)/2,y=(corridor.y0+corridor.y1)/2;
    f.part(row.owner,x,y,"top","owner",row.owner_pin);
    f.part(row.cap,x,y,"bottom");
    const auto gap=[&] {
        PcbCheckModel model; model.origin_x=model.origin_y=0;
        for(const auto& ref:{row.owner,row.cap}) {
            PcbCheckInstance i;i.ref=ref;i.mod=f.p->mod(ref);
            i.x=f.p->pos.at(ref).first;i.y=f.p->pos.at(ref).second;i.side=f.p->side(ref);
            model.insts.push_back(i);
        }
        const PcbCheckInput check(std::move(model));
        const auto a=check.geometry_at(0).pad_boxes.at(row.owner_pin);
        const auto b=check.geometry_at(1).pad_boxes.at(row.cap_pin);
        return std::hypot(std::max({0.,a.x0-b.x1,b.x0-a.x1}),
                          std::max({0.,a.y0-b.y1,b.y0-a.y1}));
    };
    const double before=gap();
    const auto entry=f.p->pos;
    const auto counts=f.p->ctx.quantization;
    bool rejected=false;
    try { f.p->evict(); }
    catch(const PcbZoneInfeasible&) { rejected=true; }
    // This fixture deliberately has no allocated sheet block, so neither an
    // independent exit nor a full-group exit has a provable legal leash.
    require(rejected,"unallocated owned eviction did not fail explicitly");
    require(f.p->pos==entry && gap()==before,"failed eviction changed ownership geometry");
    require(f.p->ctx.quantization!=counts,"failed eviction lost actual trial work");
    require(!f.p->out.placement_accounting.fallback_events.empty() &&
            f.p->out.placement_accounting.fallback_events.back()=="corridor_stray_unmovable",
            "failed eviction missing terminal rejection receipt");
    std::cout<<"EVICTION_REJECTED unallocated witness; geometry retained; actual work retained\n";
}
}
int main(int argc,char** argv) {
    try {
        if(argc!=3 || !schgen::open_part_catalog(argv[2]))
            throw std::runtime_error("usage: owned-moves REPOSITORY CATALOG");
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
        tests(source);eviction_risk(source);
        schgen::close_part_catalog();
        std::cout<<"PASS "<<checks<<" compact ownership move/swap assertions\n";
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
