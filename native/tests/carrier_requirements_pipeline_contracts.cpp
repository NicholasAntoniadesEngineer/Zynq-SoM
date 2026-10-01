#include "board_pipeline_internal.hpp"
#include "schgen/placement_requirements.hpp"
#include <iostream>
#include <unistd.h>

// Internal production stage, defined in the pipeline TU; not a test substitute.
namespace schgen::board_pipeline_detail { void carrier_surface_requirements_stage(Context&); }
namespace {
using namespace schgen;
using namespace schgen::board_pipeline_detail;
std::size_t checks=0;
void require(bool v,const std::string& why){++checks;if(!v)throw std::runtime_error(why);}
struct Scratch {
    fs::path root;
    Scratch(){auto p=(fs::temp_directory_path()/"carrier-requirement-hook-XXXXXX").string();require(::mkdtemp(p.data())!=nullptr,"scratch");root=p;}
    ~Scratch(){std::error_code e;fs::remove_all(root,e);}
};
struct Fixture {
    Scratch scratch;
    ProjectPaths paths;
    std::vector<ProjectCircuit> circuits;
    BoardPcbStage stage;
    SheetIndex index;
    Fixture(const fs::path& repo):paths(resolve_project_paths(repo,"carrier")),index(load_sheet_index(paths)) {
        paths.subsystems_dir=scratch.root/"manifests";
        ProjectAuthoringInput source;source.context=make_authoring_context(repo);
        std::map<std::string,int> bands(index.begin(),index.end());
        std::map<std::string,std::vector<KicadNetlistPin>> extraction;
        for(const auto* sheet:{"board_aux","bringup_rails"}) {
            fs::create_directories(paths.subsystems_dir/sheet);
            fs::copy_file(repo/"carrier/subsystems"/sheet/"placement_requirements.json",paths.subsystems_dir/sheet/"placement_requirements.json");
            ProjectCircuit live;live.name=sheet;live.circuit=author_project_subsystem("carrier",sheet,source);circuits.push_back(live);
            std::map<std::string,std::string> refs;
            for(const auto& p:live.circuit.parts)refs[p.ref]=board_renamed_ref(p.ref,bands.at(sheet),sheet);
            // Independent test hierarchy extraction fixture, based on live
            // circuit + persistent bands, constructed before candidate geometry.
            for(const auto& n:live.circuit.nets) {
                const auto name=n.net_class=="signal"?"/"+std::string(sheet)+"/"+n.name:n.name;
                for(const auto& p:n.pins)extraction[name].push_back({refs.at(p.ref),p.pin});
            }
            for(const auto& p:live.circuit.parts) {
                PcbFootprintInst i;i.ref=refs.at(p.ref);i.sheet=sheet;i.value=p.value;i.footprint=p.footprint;
                std::string footprint="(footprint \"synthetic-hook\" (layer \"F.Cu\")";
                for(const auto& n:live.circuit.nets) for(const auto& pin:n.pins) if(pin.ref==p.ref) {
                    const auto name=n.net_class=="signal"?"/"+std::string(sheet)+"/"+n.name:n.name;
                    i.pad_nets[pin.pin]={0,name};
                    footprint+=" (pad \""+pin.pin+"\" smd rect (at 0 0) (size 1 1) (layers \"F.Cu\" \"F.Mask\"))";
                }
                i.mod=pcb_check_footprint("synthetic-hook",footprint+")");
                stage.placement.model.insts.push_back(std::move(i));
            }
        }
        int id=1;
        for(const auto& n:extraction){stage.inputs.netlist.push_back(n);stage.placement.model.net_numbers[n.first]=id++;}
        for(auto& i:stage.placement.model.insts) for(auto& p:i.pad_nets)p.second.first=stage.placement.model.net_numbers.at(p.second.second);
        stage.inputs.floorplan.sheet_index=index;stage.inputs.floorplan.project=load_project_config(paths);
    }
    BoardPipelineResult run(const std::string& name,const std::function<void(Context&)>& mutation={}) {
        BoardPipelineOptions options;options.output_root=scratch.root/name;
        Context c(paths,options);c.circuits=circuits;c.index=index;c.pcb=stage;c.pcb_published=true;
        // The integration fixture supplies the upstream-success precondition;
        // this is not a claim to rerun KiCad or the full board pipeline.
        c.schematic=BoardSchematicResult{};
        if(mutation)mutation(c);
        carrier_surface_requirements_stage(c);
        require(c.result.gates.size()==1,"one real hook verdict");
        const auto& gate=c.result.gates.front();
        require(gate.name=="placement_requirements"&&gate.mandatory,"new hook is mandatory under production gate policy");
        require(fs::is_regular_file(c.reports/"placement_requirements.txt"),"hook published report");
        return c.result;
    }
};
void tests(const fs::path& repo) {
    Fixture f(repo);
    const auto baseline=f.run("baseline");
    require(baseline.gates.front().status==BoardGateStatus::passed,baseline.gates.front().report);
    require(baseline.gates.front().report.find("UNVERIFIED")!=std::string::npos,"unknowns explicit in hard-only report");
    const auto measured=read(f.scratch.root/"baseline/reports/placement_requirements_unverified.txt");
    require(measured.find("planar_pad_box_gap_mm=")!=std::string::npos&&measured.find("UNVERIFIED proximity")!=std::string::npos,"real checker measured named terminals");
    auto fail=[&](const std::string& name,const std::function<void(Context&)>& mutate,const std::string& why){
        const auto r=f.run(name,mutate);
        require(r.gates.front().status==BoardGateStatus::failed,"hook must FAIL: "+name);
        require(!r.ok(),"hard violation cannot produce successful pipeline");
        require(r.gates.front().report.find(why)!=std::string::npos,"specific evidence for "+name+": "+r.gates.front().report);
    };
    for(const auto* sheet:{"board_aux","bringup_rails"}) {
        const auto path=f.paths.subsystems_dir/sheet/"placement_requirements.json";
        const auto original=read(path);fs::remove(path);
        fail(std::string("missing-")+sheet,{},"placement_requirements.json");publish_text(path,original);
        auto requirements=parse_json_text(original);
        for(auto& entry:requirements.object_value)if(entry.first=="ownership")entry.second.array_value.pop_back();
        publish_text(path,json(requirements));
        fail(std::string("omitted-")+sheet,{},"ownership");publish_text(path,original);
    }
    fail("pad-name",[](Context& c){c.pcb->placement.model.insts.front().pad_nets.begin()->second.second="corrupted";},"placed pin/net changed");
    fail("pad-id",[](Context& c){c.pcb->placement.model.insts.front().pad_nets.begin()->second.first=0;},"placed pin/net changed");
    fail("access",[](Context& c){for(auto& p:c.pcb->placement.model.insts)if(p.sheet=="board_aux"&&p.ref.rfind("SW",0)==0)p.side="bottom";},"access switch on bottom");
    fail("no-live-sheet",[](Context& c){c.circuits.pop_back();},"required live carrier sheet missing");
    fail("no-placement",[](Context& c){c.pcb.reset();},"current PCB");
    fail("band-drift",[](Context& c){c.pcb->inputs.floorplan.sheet_index.clear();},"reference-band drift");
    fail("extraction-pin",[](Context& c){c.pcb->inputs.netlist.clear();},"missing from hierarchy extraction");
    fail("actual-part-missing",[](Context& c){c.pcb->placement.model.insts.pop_back();},"missing placed part");
    require(f.run("restored").gates.front().status==BoardGateStatus::passed,"restored independent inputs pass hard-only checks");
    f.paths.project_file=resolve_project_paths(repo,"devkit_mini").project_file;
    const auto na=f.run("devkit-nonapplicable",[](Context& c){c.pcb.reset();c.schematic.reset();c.circuits.clear();});
    require(na.gates.front().status==BoardGateStatus::passed&&na.gates.front().report.find("NOT APPLICABLE")!=std::string::npos,"explicit devkit applicability, no carrier inputs required");
}
}
int main(int argc,char** argv) {
    try {require(argc==3,"usage: carrier_requirements_pipeline_contracts REPOSITORY CATALOG");
        require(open_part_catalog(argv[2]),"open invocation catalog");tests(argv[1]);close_part_catalog();
        std::cout<<"PASS "<<checks<<" real pipeline-hook assertions (synthetic geometry/upstream fixture; no full-board rerun)\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
