#include "pcb_placement_fixture.hpp"
#include "schgen/experiment_tools.hpp"
#include "../src/experiment_tools_internal.hpp"
#include <iostream>
#include <unistd.h>

namespace {
using namespace placement_fixture;
std::size_t checks = 0;
void require(bool ok, const std::string &why) { ++checks; if (!ok) throw std::runtime_error(why); }
struct Temporary {
    std::filesystem::path path;
    Temporary() { std::string pattern = "/private/tmp/experiment-contracts.XXXXXX"; if (!mkdtemp(pattern.data())) throw std::runtime_error("mkdtemp"); path = pattern; }
    ~Temporary() { std::error_code ignored; std::filesystem::remove_all(path, ignored); }
};
ExperimentDocument subdocument(const ExperimentDocument &source, const J &value, const std::string &prefix) {
    ExperimentDocument result; result.data = value;
    for (const auto &p : source.float_paths) if (p.compare(0, prefix.size()+1, prefix+"/") == 0) result.float_paths.insert(p.substr(prefix.size()));
    for (const auto &[p, token] : source.integer_tokens) if (p.compare(0, prefix.size()+1, prefix+"/") == 0) result.integer_tokens[p.substr(prefix.size())] = token;
    return result;
}
void same(const J &a, const J &b, const std::string &where) {
    require(a.kind == b.kind, where + " kind");
    if (a.kind == JsonKind::Object) {
        require(a.object_value.size() == b.object_value.size(), where + " fields");
        for (const auto &[k,v] : b.object_value) same(field(a,k),v,where+"/"+k);
    } else if (a.kind == JsonKind::Array) {
        require(a.array_value.size() == b.array_value.size(), where + " size " + std::to_string(a.array_value.size()) + " != " + std::to_string(b.array_value.size()));
        for (std::size_t i=0;i<b.array_value.size();++i) same(a.array_value[i],b.array_value[i],where+"/"+std::to_string(i));
    } else if (a.kind == JsonKind::Number) require(a.number_value==b.number_value,where+" got="+std::to_string(a.number_value)+" expected="+std::to_string(b.number_value));
    else if (a.kind == JsonKind::String) require(a.string_value==b.string_value,where+" string");
    else if (a.kind == JsonKind::Bool) require(a.bool_value==b.bool_value,where+" bool");
}
void unit(const std::filesystem::path &root) {
    using experiment_detail::publish;
    auto source = parse_compose_document(read(root / "native/tests/data/experiment_tools/driver_reference.json"));
    std::size_t index=0;
    for (const auto &row : field(source.data,"drivers").array_value) {
        const bool sweep=string(row,"script")=="w11_sweep";
        const auto sheets=strings(field(row,"sheets"));
        const auto verdict=subdocument(source,field(row,"verdict"),"/drivers/"+std::to_string(index)+"/verdict");
        const ExperimentBoardRun board{static_cast<int>(number(row,"exit_code")),string(row,"stdout"),string(row,"stderr")};
        const auto argument=string(row,sweep?"mm":"tag");
        auto got=sweep?format_w11_sweep(argument,sheets,board,verdict,string(row,"pcb")):format_chir_rung(argument,board,verdict,string(row,"pcb"));
        require(got.output==string(row,"expected"),"independent driver output bytes case "+std::to_string(index));
        require(got.board_exit_code==board.exit_code,"transport status retained separately");
        require(got.pass_token==(board.stdout_text.find("BOARD: PASS")!=std::string::npos),"historical stdout token meaning");
        Temporary tmp;
        ExperimentBoardPaths paths{tmp.path/"floorplan.json",tmp.path/"baseline.json",tmp.path/"board.kicad_pcb",tmp.path/"verdict.json"};
        publish(paths.spec,string(row,"original_spec")); publish(paths.fallback_baseline,string(row,"restored_baseline"));
        publish(paths.pcb,string(row,"pcb")); publish(paths.verdict,render_experiment_json(verdict));
        int calls=0;
        ExperimentBoardHost host;
        host.run_board=[&](const ExperimentBoardRequest &request) {
            ++calls; require(request.no_render,"native board no-render request");
            require(request.ordinary_via_mm.has_value()==sweep,"explicit scoped ordinary parameter");
            if(sweep) require(*request.ordinary_via_mm==parse_experiment_ordinary_via(argument),"ordinary argument forwarded");
            require(read(paths.spec)==string(row,"spec_during"),"exact candidate spec indentation/numeric types");
            publish(paths.fallback_baseline,"changed by board");
            return board;
        };
        auto applied=sweep?run_w11_sweep(paths,host,argument,sheets):run_chir_rung(paths,host,argument,sheets);
        require(applied.output==got.output && calls==1,"driver executes host once");
        require(read(paths.spec)==string(row,"restored_spec"),"restore exact spec bytes");
        require(read(paths.fallback_baseline)==string(row,"restored_baseline"),"restore exact baseline bytes");
        require(read(paths.pcb)==string(row,"pcb"),"board artifact not rolled back");
        host.run_board=[&](const auto &)->ExperimentBoardRun { publish(paths.fallback_baseline,"failed run"); throw std::runtime_error("board exception"); };
        bool failed=false;
        try { (void)run_chir_rung(paths,host,"reject",sheets); } catch(const std::runtime_error &e) { failed=std::string(e.what())=="board exception"; }
        require(failed,"host exception propagates");
        require(read(paths.spec)==string(row,"restored_spec") && read(paths.fallback_baseline)==string(row,"restored_baseline"),"exceptions restore both originals");
        host.run_board=[&](const auto &) { publish(paths.verdict,"malformed");publish(paths.pcb,"new board remains");publish(paths.fallback_baseline,"mutated");return board; };
        failed=false;
        try {(void)run_chir_rung(paths,host,"parse reject",sheets);}catch(const std::exception &){failed=true;}
        require(failed && read(paths.pcb)=="new board remains","parse failure preserves generated board artifacts");
        require(read(paths.spec)==string(row,"restored_spec") && read(paths.fallback_baseline)==string(row,"restored_baseline"),"parse failure restores inputs");
        ++index;
    }
    for(const auto *bad:{"nan","inf","-1","1+2","2; run()","0x1p2","1e9999","","2.2 mm"," 2.2"}) {
        bool failed=false;try{(void)parse_experiment_ordinary_via(bad);}catch(const std::exception &){failed=true;}
        require(failed,std::string("reject nonliteral parameter: ")+bad);
    }
    require(parse_experiment_ordinary_via("-0")==0 && parse_experiment_ordinary_via("+.25")==.25,"finite nonnegative literals");
    for(const auto &[input,expected]:std::vector<std::pair<std::string,std::string>>{{"","d41d8cd98f00b204e9800998ecf8427e"},{"a","0cc175b9c0f1b6a831c399e269772661"},{"abc","900150983cd24fb0d6963f7d28e17f72"},{"message digest","f96b697d7cb7938d525a2f31aaf161d0"}})
        require(experiment_detail::diagnostic_md5(input)==expected,"independent MD5 vectors");
    require(experiment_circuit_json_path("subsystems/a.py")=="subsystems/a/circuit.json","flat source mapping");
    require(experiment_circuit_json_path("subsystems/a/a.py")=="subsystems/a/circuit.json","package mapping");
    for(const auto &row:field(source.data,"dump").array_value) {
        auto circuit=parse_circuit_ir(field(row,"ir"));
        auto dump=prepare_native_circuit_dump(circuit,"subsystems/"+circuit.name+".py");
        require(dump.bytes==string(row,"expected"),"independent canonical JSON bytes "+circuit.name);
        Temporary tmp;dump.path=tmp.path/"outputs"/circuit.name/"circuit.json";
        require(!std::filesystem::exists(dump.path),"pure preparation does not publish");
        publish_native_circuit_dump(dump);require(read(dump.path)==dump.bytes,"explicit single dump publication");
        circuit.parts.push_back(circuit.parts.front());
        bool rejected=false;try{(void)prepare_native_circuit_dump(circuit,"invalid.py");}catch(const std::exception &){rejected=true;}
        require(rejected,"malformed authored IR rejected before publication");
    }
    auto snapshot=parse_json_file((root/"native/tests/data/experiment_tools/observer_reference.json").string());
    for(const auto &frame:field(field(snapshot,"snapshots"),"frames").array_value) {
        PcbFootprintPool pool;
        for(const auto &[name,bytes]:field(field(snapshot,"snapshots"),"footprints").object_value)
            pool["/private/tmp/native-experiments.LfDTUF/"+name+".kicad_mod"]=pcb_check_footprint(name,bytes.string_value);
        PcbModel m;
        for(const auto &row:field(frame,"expected").array_value) {
            PcbCheckInstance inst;inst.ref=string(row,"ref");inst.sheet=string(row,"sheet");inst.mod=pool.at(string(row,"mod_path"));
            inst.x=number(row,"x");inst.y=number(row,"y");inst.rotation=number(row,"rotation");inst.side=string(row,"side");
            for(const auto &[pin,n]:field(row,"pad_nets").object_value)inst.pad_nets[pin]={static_cast<int>(n.array_value[0].number_value),n.array_value[1].string_value};
            m.insts.push_back(inst);
        }
        const auto lengths=experiment_cross_lengths(m.insts);
        const auto &expected=field(frame,"cross").array_value;
        require(lengths.cross==expected[0].number_value&&lengths.total==expected[1].number_value&&lengths.n_cross==expected[2].number_value,"independent probe MST measurements");
    }
}
void probes(const std::filesystem::path &root, const std::string &project) {
    auto fixture=load(root,project);
    const auto base=root/"native/tests/data/experiment_tools";
    const auto probe=run_w12_stageprobe(fixture.input,"independent");
    const auto expected=parse_json_file((base/(project+"_stageprobe.json")).string());
    same(field(probe.document.data,"rows"),field(field(expected,"result"),"rows"),project+" stage probe");
    const auto formats=parse_json_file((base/"probe_format_reference.json").string());
    auto bytes=[&](const std::string &name,const std::string &output) {
        const auto &record=field(formats,name);
        require(output.size()==number(record,"output_bytes") && pcb_sha256(output)==string(record,"output_sha256"),name+" exact complete output bytes");
    };
    bytes(project+"_stageprobe",probe.output);
    if(project=="devkit_mini") {
        auto conservative=run_w12_stageprobe(fixture.input,"conservative",{},true);
        const auto cons=parse_json_file((base/(project+"_conservative.json")).string());
        same(field(conservative.document.data,"rows"),field(field(cons,"result"),"rows"),project+" conservative probe");
        bytes(project+"_conservative",conservative.output);
        require(!conservative.placement.floorplan.plan.punch_free,"forced conservative is genuine solver result");
        const auto bound=run_w12_bound(fixture.input,"bounds");
        const auto reference=parse_json_file((base/(project+"_bound.json")).string());
        same(field(bound.document.data,"n_calls"),field(field(reference,"result"),"n_calls"),"real packing call count");
        same(field(bound.document.data,"cands"),field(field(reference,"result"),"cands"),"all candidate parameters/estimates");
        bytes(project+"_bound",bound.output);
        auto input=fixture.input;
        auto via=std::make_shared<FloorplanExperiment>();via->ordinary_via_mm=5.;
        input.floorplan.experiment=via;
        const auto changed=run_w12_stageprobe(input,"mutation",{"power_mon"});
        const auto mutation=parse_json_file((base/"devkit_mini_mutation.json").string());
        same(field(changed.document.data,"rows"),field(field(mutation,"result"),"rows"),"independent layer/ordinary-cost mutation");
        require(input.floorplan.spec->interior.at("power_mon").layer==fixture.input.floorplan.spec->interior.at("power_mon").layer,"candidate layer does not mutate caller input");
        require(via->ordinary_via_mm==5. && !via->attempt_completed && !via->unscoped_estimate,"per-run recorder does not mutate caller observer");
        require(!fixture.input.floorplan.experiment,"control retains original via policy");
    }
    if(project=="carrier") {
        const auto vectors=parse_json_file((base/"carrier_via_vectors.json").string());
        require(!field(vectors,"cases").array_value.empty(),"ordinary override has genuine bottom candidates");
        auto zones=build_pcb_zone_geometry(fixture.input);
        auto prepared=prepare_pcb_floorplan(fixture.input,zones);
        bool changed=false;
        for(const auto &row:field(vectors,"cases").array_value) {
            auto plan=probe.placement.floorplan.plan;
            bool found=false;
            for(auto *blocks:{&plan.edge_blocks,&plan.interior_blocks})for(auto &block:*blocks)
                if(block.name==string(row,"sheet")) {block.shape_idx=static_cast<int>(number(row,"shape"));block.side="bottom";found=true;}
            require(found,"independent variant owns existing block");
            const auto &costs=field(row,"costs").array_value,&values=field(row,"expected").array_value;
            for(std::size_t i=0;i<costs.size();++i) {
                auto observer=std::make_shared<FloorplanExperiment>();observer->ordinary_via_mm=costs[i].number_value;
                prepared.experiment=observer;
                const auto value=measure_floorplan_experiment_plan(prepared,plan).estimate;
                require(value==values[i].number_value,"independent via-cost candidate estimate "+string(row,"sheet")+" "+std::to_string(i));
                changed|=value!=values.front().number_value;
            }
        }
        require(changed,"ordinary override reaches real native estimator, not a no-op constant edit");
    }
    std::cout<<project<<": independent complete stage report passed\n";
}
void catalogs(const std::filesystem::path &root) {
    require(open_part_catalog((root/"native/catalog.bin").string()),"open existing part catalog read-only");
    const auto reference=parse_json_file((root/"native/tests/data/experiment_tools/catalog_reference.json").string());
    for(const auto *project:{"carrier","devkit_mini"}) {
        auto paths=resolve_project_paths(root,std::filesystem::path(project));
        auto prepared=prepare_native_circuit_dumps(paths,project);
        const auto &expected=field(field(reference,project),"sheets").array_value;
        require(prepared.size()==expected.size(),std::string(project)+" all live native factories");
        for(std::size_t i=0;i<prepared.size();++i) {
            const auto &dump=prepared[i];const auto &e=expected[i];
            require(dump.path==paths.subsystems_dir/string(e,"name")/"circuit.json","native canonical output path");
            require(dump.bytes.size()==number(e,"bytes") && pcb_sha256(dump.bytes)==string(e,"sha256"),std::string(project)+" independent dump bytes "+string(e,"name"));
        }
        Temporary tmp;
        auto output_paths=paths;output_paths.repository_root=tmp.path;output_paths.subsystems_dir=tmp.path/project/"subsystems";
        auto report=run_dump_circuits(output_paths,project);
        require(report.size()>0 && report.find("dumped "+std::to_string(prepared.size())+" circuit.json files\n")!=std::string::npos,"catalog publication report");
        for(const auto &dump:prepared) require(read(output_paths.subsystems_dir/dump.path.parent_path().filename()/"circuit.json")==dump.bytes,"explicit isolated catalog publication bytes");
        // A late publication failure must not erase earlier successful writes.
        Temporary blocked;
        output_paths.repository_root=blocked.path;output_paths.subsystems_dir=blocked.path/project/"subsystems";
        const auto second=prepared.at(1).path.parent_path().filename();
        std::filesystem::create_directories(output_paths.subsystems_dir);
        experiment_detail::publish(output_paths.subsystems_dir/second,"not a directory");
        bool failed=false;try{(void)run_dump_circuits(output_paths,project);}catch(const std::exception &){failed=true;}
        require(failed,"catalog late write error propagates");
        require(read(output_paths.subsystems_dir/prepared.front().path.parent_path().filename()/"circuit.json")==prepared.front().bytes,"catalog leaves earlier explicit writes on later failure");
        std::cout<<project<<": "<<prepared.size()<<" live native catalog byte contracts passed\n";
    }
    close_part_catalog();
}
} // namespace
int main(int argc,char **argv) {
    try {
        if(argc<2||argc>3)throw std::runtime_error("usage: experiment_tools_contracts ROOT [--live]");
        unit(argv[1]);
        if(argc==3 && std::string(argv[2])=="--live") {
            for(const auto *name:{"carrier","devkit_mini"})probes(argv[1],name);
            catalogs(argv[1]);
        }
        std::cout<<"experiment tools: "<<checks<<" assertions passed\n";
    } catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
