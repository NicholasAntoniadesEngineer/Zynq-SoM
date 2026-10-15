// Regression: current compact inputs reject the exact archived unsafe seed.
// This test replays placement only; it never runs floorplan search.
#define main inherited_stage_profile_main
#include "compact_stage_profile.cpp"
#undef main
#include "pcb_placement_internal.hpp"
#include "floorplan_internal.hpp"
#include <fstream>
#include <sstream>

namespace {
std::string read_bytes(const std::filesystem::path& p) {
    std::ifstream f(p,std::ios::binary);
    if(!f) throw std::runtime_error("cannot read "+p.string());
    return {std::istreambuf_iterator<char>(f),{}};
}
void demand(bool value,const char* why) {if(!value)throw std::runtime_error(why);}
FloorplanStage replay_plan(const PcbPlacementInput& in,const std::string& log) {
    FloorplanStage stage; stage.plan.som=in.floorplan.som;stage.plan.som_source=in.floorplan.som_source;
    std::istringstream lines(read_bytes(log));std::string line;bool header=false;
    while(std::getline(lines,line)) {
        std::istringstream s(line);std::string tag;s>>tag;
        if(tag=="SEEDPLAN") {
            auto& p=stage.plan;s>>p.board_w>>p.board_h>>p.som_x>>p.som_y>>p.dec_count>>p.dec_radius>>p.punch_free;
            demand(bool(s),"bad exact plan header");header=true;
        } else if(tag=="SEEDBLOCK") {
            FloorplanBlock b;bool edge;
            s>>edge>>std::quoted(b.name)>>std::quoted(b.kind)>>std::quoted(b.edge)>>std::quoted(b.side)
             >>b.shape_idx>>b.x>>b.y>>b.w>>b.h;
            demand(bool(s),"bad exact block row");
            (edge?stage.plan.edge_blocks:stage.plan.interior_blocks).push_back(b);
        }
    }
    demand(header&&!stage.plan.edge_blocks.empty()&&!stage.plan.interior_blocks.empty(),"incomplete exact plan");
    return stage;
}
void print_plan(const FloorplanPlan& p,const PcbZoneResult& zones) {
    std::cout<<"SEEDPLAN "<<p.board_w<<' '<<p.board_h<<' '<<p.som_x<<' '<<p.som_y<<' '
             <<p.dec_count<<' '<<p.dec_radius<<' '<<p.punch_free<<'\n';
    for(const auto* blocks:{&p.edge_blocks,&p.interior_blocks}) for(const auto& b:*blocks) {
        std::cout<<"SEEDBLOCK "<<(blocks==&p.edge_blocks)<<' '<<std::quoted(b.name)<<' '<<std::quoted(b.kind)
                 <<' '<<std::quoted(b.edge)<<' '<<std::quoted(b.side)<<' '<<b.shape_idx<<' '
                 <<b.x<<' '<<b.y<<' '<<b.w<<' '<<b.h<<'\n';
        if(b.name=="bringup_rails"||b.name=="ethernet") {
            const auto& shape=zones.geometry.shapes.at(b.name).at(b.shape_idx);
            std::cout<<"SELECTED "<<b.name<<" index="<<b.shape_idx<<" tag="<<shape.tag<<'\n';
            for(const auto* offsets:{&shape.top_off,&shape.bot_off}) for(const auto& [r,xy]:*offsets)
                std::cout<<"LOCAL "<<b.name<<' '<<r<<' '<<xy.first<<' '<<xy.second<<' '
                         <<(offsets==&shape.top_off?shape.side:(shape.side=="top"?"bottom":"top"))<<'\n';
        }
    }
}
}
int main(int argc,char** argv) {try {
    demand(argc==3,"usage: child-halo-seed private-root exact-plan-fixture");
    std::cout<<std::setprecision(17)<<std::unitbuf;
    const auto paths=resolve_project_paths(argv[1],"carrier");
    demand(open_part_catalog(paths.part_catalog_file.string()),"catalog open failed");
    NetlistExtractOptions extraction;extraction.kicad_cli="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli";
    // This diagnostic consumes an explicitly supplied historical private root:
    // preserve its archived schematic rather than authoring current circuits.
    auto loaded=load(paths,extraction,true,{});auto input=std::move(loaded.input);input.floorplan.compact_search=true;
    demand(input.owned_groups.size()==2,"expected two resolved owned groups");
    const auto zones=build_pcb_zone_geometry(input);
    std::size_t appended=0;
    for(const auto& [sheet,shapes]:zones.geometry.shapes) for(const auto& s:shapes)
        if(s.tag.find("/owned-pins-")!=std::string::npos)++appended;
    std::cout<<"INPUT owned_groups="<<input.owned_groups.size()<<" appended="<<appended<<'\n';
    demand(appended==56,"expected current 56 alternatives");
    double width=0,height=0;std::string first_failure,phase="actual";
    auto observer=std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint=[&](const PcbPlacementObservation& row) {
        if(row.plan){width=row.plan->w;height=row.plan->h;std::cout<<"BOUNDS "<<width<<' '<<height<<'\n';}
        if(!row.has_positions)return;
        demand(width>0&&height>0,"observer lacks actual plan bounds");
        PcbCheckModel m;m.board_w=width;m.board_h=height;m.insts=row.instances;
        const PcbCheckInput check(std::move(m));
        for(const auto& r:check_fanout(check,0).records) if(r.ref=="SW7002") {
            std::cout<<"GAP "<<phase<<' '<<row.stage<<" clearance="<<r.clearance<<" need="<<r.need
                     <<" nearest="<<r.nearest_ref<<" starved="<<r.starved()<<'\n';
            if(r.starved()&&first_failure.empty())first_failure=phase+"/"+row.stage;
        }
        for(std::size_t i=0;i<row.instances.size();++i) {
            const auto& p=row.instances[i];
            if(p.ref=="SW7002"||p.ref=="C10005") {
                const auto b=check.courtyard_at(i);
                std::cout<<"POSE "<<phase<<' '<<row.stage<<' '<<p.ref<<' '<<p.x<<' '<<p.y<<' '
                         <<p.rotation<<' '<<p.side<<" bbox="<<b.x0<<','<<b.y0<<','<<b.x1<<','<<b.y1<<'\n';
            }
        }
    };
    input.experiment=observer;
    const auto stage=replay_plan(input,argv[2]);width=stage.plan.board_w;height=stage.plan.board_h;
    const auto result=place_pcb_model_accounted(input,zones,stage,PcbZoneAccountingOwnership::SeparateFromFloorplan);
    print_plan(result.floorplan.plan,zones);
    const auto emitted=render_pcb(result.model,pcb_emit_policy(input.floorplan.project));
    const auto hash=pcb_sha256(emitted.pcb);
    const std::string archive_hash="3e2856ebb4807a4d3470b33780c40cc660c8c7c762cfd5ea2e90e0b2f6a1a98f";
    std::cout<<"ARCHIVE_MATCH "<<(hash==archive_hash)<<" actual="<<hash<<" archived="<<archive_hash<<'\n';
    demand(hash==archive_hash,"candidate mismatch; trace attribution uncertain");
    demand(width==170&&height==165,"candidate bounds mismatch");
    std::cout<<"FIRST_FAILURE "<<first_failure<<'\n';
    const auto compiled=prepare_pcb_floorplan(input,zones);
    floorplan_detail::Engine engine(compiled);
    engine.initialize();engine.board_size(width,height);engine.prepare_geometry();
    const auto& switch_shape=engine.shape_sets[1].at("bringup_rails").at(56);
    const auto& ethernet_shape=engine.shape_sets[1].at("ethernet").at(0);
    const auto find_block=[&](const std::string& name)->const FloorplanBlock& {
        for(const auto& b:result.floorplan.plan.interior_blocks) if(b.name==name)return b;
        throw std::runtime_error("missing selected block "+name);
    };
    const auto& sw=find_block("bringup_rails");const auto& eth=find_block("ethernet");
    demand(sw.shape_idx==56&&eth.shape_idx==0,"shape witness changed");
    QuantizationCounts occupancy_counts;
    Occupancy occupancy(width,height,floorplan_detail::clear,std::max(12.,2*engine.max_reach),
                        engine.max_reach,1,.05);
    occupancy.add(eth.x,eth.y,ethernet_shape.w,ethernet_shape.h,ethernet_shape.reach,
        ethernet_shape.inset,floorplan_detail::side_mask(ethernet_shape.side),ethernet_shape.comps,&occupancy_counts);
    const bool fits=occupancy.fits_hashed(sw.x,sw.y,switch_shape.w,switch_shape.h,switch_shape.reach,
        switch_shape.inset,floorplan_detail::side_mask(switch_shape.side),switch_shape.comps,&occupancy_counts);
    std::cout<<"OCCUPANCY_PAIR_ACCEPTS "<<fits<<" primary_side="<<switch_shape.side<<" reach="
             <<switch_shape.reach.w<<','<<switch_shape.reach.e<<','<<switch_shape.reach.n<<','<<switch_shape.reach.s<<'\n';
    for(const auto& c:switch_shape.comps)
        std::cout<<"CHILD_RESERVATION "<<c.dx<<' '<<c.dy<<' '<<c.w<<' '<<c.h<<" mask="<<c.mask<<" reach="<<c.reach.w<<','<<c.reach.e<<','<<c.reach.n<<','<<c.reach.s<<'\n';
    demand(!fits,"unsafe minority-face fanout seed still admitted");
    // Comp is produced AFTER shape rotation. Verify all quarter turns carry
    // the directional halo around with the actual minority courtyard frame.
    auto rotated=zones.geometry.shapes.at("bringup_rails").at(sw.shape_idx);
    const auto near=[](double a,double b){return std::abs(a-b)<.00011;};
    auto previous=engine.zone_components(rotated,true,&occupancy_counts).front();
    for(int turn=0;turn<4;++turn) {
        rotated=pcb_placement::turned(rotated,&occupancy_counts);
        const auto next=engine.zone_components(rotated,true,&occupancy_counts).front();
        for(const auto pair:{std::make_pair(previous.reach,next.reach),std::make_pair(previous.inset,next.inset)}) {
            const auto a=pair.first,b=pair.second;
            demand(near(b.w,a.n)&&near(b.e,a.s)&&near(b.n,a.e)&&near(b.s,a.w),"rotated child directional halo lost");
        }
        previous=next;
    }
    auto legacy_children=switch_shape.comps;
    for(auto& c:legacy_children){c.reach={};c.inset={};}
    demand(occupancy.fits_hashed(sw.x,sw.y,switch_shape.w,switch_shape.h,switch_shape.reach,
        switch_shape.inset,floorplan_detail::side_mask(switch_shape.side),legacy_children),
        "zero-child-halo negative witness no longer admits the archived seed");
    receipt("pair_actual",occupancy_counts);
    // Exact selected shapes and double-precision plan, not rounded Markdown.
    // Isolate the two breathe passes with the same production rounded observer.
    phase="substage";
    pcb_placement::Placer p(input,zones,result.floorplan);
    p.seed();p.l4_pull();p.observe_checkpoint("l4_pull");p.edge_seat();p.observe_checkpoint("edge_seat");
    p.breathe("A");p.observe_checkpoint("breathe_A");p.breathe("B");p.observe_checkpoint("breathe_B");
    receipt("diagnostic_substage_actual",p.ctx.quantization);
    std::cout<<"PASS_CHILD_HALO_REJECTS_ARCHIVED_SEED_NO_BOARD_ACCEPTANCE\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
