#include "schgen/board_inputs.hpp"
#include "schgen/catalog.hpp"
#include "schgen/netlist_gate.hpp"
#include "pcb_placement_internal.hpp"
#include <iostream>

namespace {
using namespace schgen;
using namespace schgen::pcb_placement;
void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Probe {
    PcbPlacementInput in;
    PcbZoneResult zones;
    FloorplanStage stage;
    std::unique_ptr<Placer> p;
    std::string owner,cap;
    Probe(const PcbPlacementInput& source,bool compact,int exemption,bool reverse,bool opposite):in(source) {
        in.floorplan.compact_search=compact;
        // Real Context domain: populate through project policy, never by
        // inserting a ref (or even a sheet) into ctx.l4_exempt in the test.
        if(exemption==1) in.floorplan.project.wired_sheets.push_back("bringup_rails");
        if(exemption==2) {
            in.floorplan.project.wired_sheets.push_back("probe_contract");
            in.contracts["probe_contract"]=parse_json_text(
                R"({"external":{"near_max":[{"other":"bringup_rails.U1"}]}})");
        }
        const auto& row=owned_group_placements(*in.owned_groups.at("bringup_rails")).at(0);
        owner=row.owner;cap=row.cap;
        stage.plan.board_w=stage.plan.board_h=120;stage.plan.som_x=stage.plan.som_y=90;
        p=std::make_unique<Placer>(in,zones,stage);
        const std::string side=reverse?"bottom":"top";
        part(owner,side,60,60,true,false);
        part(cap,opposite?(reverse?"top":"bottom"):side,68,64,false,false);
        part("U_OTHER",side,70,60,true,false);
        part("J_FIXED",side,58,60,false,true);
        require(p->ctx.l4_exempt.count("bringup_rails")==std::size_t(exemption!=0),"Context sheet exemption missing");
        require(!p->ctx.l4_exempt.count(owner)&&!p->ctx.l4_exempt.count(cap),"test accidentally used reference-domain exemptions");
    }
    void part(const std::string& ref,const std::string& side,double x,double y,bool active,bool fixed) {
        std::string bytes="(footprint probe (layer F.Cu)";
        for(int k=1;k<=(active?3:2);++k)bytes+=" (pad \""+std::to_string(k)+"\" smd rect (at 0 0) (size .2 .2) (layers F.Cu F.Mask))";
        bytes+=")";
        p->ctx.by_ref[ref]={ref,ref,"bringup_rails","probe","probe","probe"};
        p->ctx.pool[ref]=pcb_check_footprint(ref,bytes);
        p->geometry.resolvable[ref]=ref;p->geometry.bbox_of[ref]={-.5,-.5,.5,.5};p->geometry.side_of[ref]=side;
        if(fixed)p->geometry.conn_edge[ref]="left";
        p->pos[ref]={x,y};
    }
};
}
int main(int argc,char** argv){try{
    if(argc!=3||!schgen::open_part_catalog(argv[2]))throw std::runtime_error("usage: sheet-exemption REPOSITORY CATALOG");
    const auto paths=resolve_project_paths(argv[1],"carrier");
    const auto circuits=load_project_circuits(paths);
    std::vector<CircuitSheetIr> sheets;for(const auto& c:circuits)sheets.push_back(c.circuit);
    const auto link=link_sheets(sheets,parse_json_file(paths.som_interface_file.string()),
        parse_json_file((paths.project_root/"som_mapping.json").string()));
    require(link.ok(),"live hierarchy link failed");
    BoardInputOptions options;options.compact_search=true;
    NetlistExtractOptions extraction;extraction.kicad_cli="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli";
    const auto source=load_board_inputs(paths,circuits,link,
        extract_netlist(paths.project_root/"Zynq_Carrier.kicad_sch",extraction),options);
    for(bool reverse:{false,true})for(bool opposite:{false,true})for(int exemption:{1,2}) {
        Probe unlocked(source,true,0,reverse,opposite),locked(source,true,exemption,reverse,opposite);
        const auto before=locked.p->pos;
        unlocked.p->breathe("A");
        require(unlocked.p->pos.at(unlocked.owner).first>before.at(locked.owner).first,"no actual movement witness");
        locked.p->breathe("A");locked.p->breathe("B");
        require(locked.p->pos==before,"sheet-exempt owned group or other sheet member moved");
        Probe legacy(source,false,0,reverse,opposite),legacy_exempt(source,false,exemption,reverse,opposite);
        for(const auto* phase:{"A","B"}){legacy.p->breathe(phase);legacy_exempt.p->breathe(phase);}
        require(legacy.p->pos==legacy_exempt.p->pos&&legacy.p->ctx.quantization==legacy_exempt.p->ctx.quantization,
            "default geometry or actual receipts changed");
    }
    close_part_catalog();
    std::cout<<"PASS 8 live-owned sheet-domain exemption cases; wired/near-target, both faces, A/B, default pose/receipt parity\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
