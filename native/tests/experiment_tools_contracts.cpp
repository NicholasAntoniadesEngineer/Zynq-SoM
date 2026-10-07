#include "pcb_placement_fixture.hpp"
#include "historical_input_contracts.hpp"
#include "schgen/experiment_tools.hpp"
#include "../src/experiment_tools_internal.hpp"
#include "experiment_metric_contracts.hpp"
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
template<class Check> void rejects(Check check, const std::string& why) {
    bool rejected=false;
    try { check(); } catch (const std::runtime_error&) { rejected=true; }
    require(rejected,"negative control: "+why);
}
void historical_probe_formats(const std::filesystem::path& root) {
    using namespace experiment_detail;
    const auto base=root/"native/tests/data/experiment_tools";
    const auto formats=parse_json_file((base/"probe_format_reference.json").string());
    for (const auto& name : {"carrier_stageprobe", "devkit_mini_stageprobe", "devkit_mini_conservative", "devkit_mini_bound"}) {
        const auto source=parse_compose_document(placement_fixture::read(base/(std::string(name)+".json")));
        const auto frozen=subdocument(source,field(source.data,"result"),"/result");
        const bool bound=std::string(name)=="devkit_mini_bound";
        ExperimentDocument document;
        document.data=bound ? jo({{"tag",j("bounds")},{"K",j(3.)}}) :
            jo({{"tag",j(std::string(name)=="devkit_mini_conservative" ? "conservative" : "independent")}});
        for (const auto& [key,value] : frozen.data.object_value) set(document.data,key,value);
        document.float_paths=frozen.float_paths;
        document.integer_tokens=frozen.integer_tokens;
        if (bound) document.float_paths.insert("/K");
        const auto output=std::string(bound ? "W12BOUND " : "W12PROBE ")+render_experiment_json(document)+"\n";
        const auto& record=field(formats,name);
        require(output.size()==number(record,"output_bytes") && pcb_sha256(output)==string(record,"output_sha256"),
                std::string(name)+" immutable historical formatter bytes");
    }
    // The layer/via mutation's historical rows remain formatter inputs too.
    const auto mutation=parse_compose_document(placement_fixture::read(base/"devkit_mini_mutation.json"));
    const auto frozen=subdocument(mutation,field(mutation.data,"result"),"/result");
    same(parse_json_text(render_experiment_json(frozen)),frozen.data,"immutable mutation formatter input");
}
ExperimentDocument stage_expectations(const PcbPlacementInput& input, const ExperimentProbeResult& probe,
    const std::vector<PcbPlacementObservation>& frames, const FloorplanInput& prepared,const std::string& tag) {
    using namespace experiment_detail;
    using experiment_metric_contracts::lengths;
    const std::vector<std::string> stages{"zone_pack","plan_lattice","shape_bind","step3_emission","l4_pull",
        "edge_seat","breathe","refit_facing","reorder","corridor_eviction","instantiate","emission_frame","escape_copper"};
    require(frames.size()==stages.size(),"complete checkpoint sequence");
    ExperimentDocument expected;
    expected.data=jo({{"tag",j(tag)},{"rows",ja()}});
    std::map<std::string,PcbPlacementPose> previous;
    for (std::size_t index=0; index<frames.size(); ++index) {
        const auto& frame=frames[index];
        require(frame.stage==stages[index],"checkpoint order "+stages[index]);
        auto row=jo({{"stage",j(frame.stage)}});
        const auto prefix="/rows/"+std::to_string(index);
        if (index==1) {
            const auto& plan=probe.placement.floorplan.plan;
            auto bottom=std::vector<std::string>{}; auto shapes=jo();
            for (const auto* blocks : {&plan.edge_blocks,&plan.interior_blocks}) for (const auto& block : *blocks) {
                if (block.side=="bottom") bottom.push_back(block.name);
                if (block.shape_idx) set(shapes,block.name,j(block.shape_idx));
            }
            std::sort(bottom.begin(),bottom.end());
            set(row,"est_cross",j(experiment_metric_contracts::estimate(prepared,plan)));
            set(row,"board",j(fmt(plan.board_w)+"x"+fmt(plan.board_h)));
            set(row,"area",j(plan.board_w*plan.board_h)); set(row,"punch_free",jb(plan.punch_free));
            set(row,"bottom_blocks",experiment_detail::strings(bottom)); set(row,"shapes",shapes);
            expected.float_paths.insert(prefix+"/est_cross"); expected.float_paths.insert(prefix+"/area");
        }
        require(frame.has_positions==(index>=3),"checkpoint position domain "+frame.stage);
        if (frame.has_positions) {
            experiment_metric_contracts::identity(input,frame.instances,require);
            const auto& poses=probe.placement.stages.at(frame.stage);
            for (const auto& inst : frame.instances) {
                const auto& [x,y,rotation,side]=poses.at(inst.ref);
                const bool page=index>=11;
                const auto emit=[&](double value) {return frame.grid_placed.count(inst.ref) ? py_round(25+value,4) : fixed_part_grid(25+value);};
                require(inst.x==(page ? x : emit(x)) && inst.y==(page ? y : emit(y)) && inst.rotation==rotation,
                        "checkpoint matches current stage pose "+frame.stage+" "+inst.ref);
                if (page) require(inst.side==side,"checkpoint page side "+inst.ref);
                if (index>3 && index!=11 && frame.fixed.count(inst.ref))
                    require(poses.at(inst.ref)==previous.at(inst.ref),"fixed stage pose "+frame.stage+" "+inst.ref);
            }
            const auto metric=lengths(frame.instances);
            set(row,"cross",j(metric.cross)); set(row,"total",j(metric.total)); set(row,"n_cross",j(metric.n_cross));
            if (index==3 || index==11) set(row,"moved",JsonNode{});
            else {
                int moved=0;
                for (const auto& [ref,pose] : poses) if (previous.count(ref) && previous.at(ref)!=pose) ++moved;
                set(row,"moved",j(moved));
                if (index==10 || index==12) require(moved==0,"frozen stage poses "+frame.stage);
            }
            previous=poses;
            expected.float_paths.insert(prefix+"/cross"); expected.float_paths.insert(prefix+"/total");
        }
        field(expected.data,"rows").array_value.push_back(std::move(row));
    }
    const auto& model=probe.placement.model;
    experiment_metric_contracts::identity(input,model.insts,require,true);
    const auto metric=lengths(model.insts);
    int bottom=0,top=0;
    for (const auto& inst : model.insts) (inst.side=="bottom" ? bottom : top)++;
    require(model.n_bottom==bottom && model.n_top==top,"model side population from instances");
    field(expected.data,"rows").array_value.push_back(jo({{"stage",j("FINAL_MODEL")},{"cross",j(metric.cross)},
        {"total",j(metric.total)},{"n_bottom",j(bottom)},{"n_top",j(top)},{"board",j(fmt(model.board_w)+"x"+fmt(model.board_h))}}));
    expected.float_paths.insert("/rows/13/cross"); expected.float_paths.insert("/rows/13/total");
    return expected;
}
ExperimentProbeResult measured_probe(PcbPlacementInput input,const std::string& tag,
    const std::vector<std::string>& sheets={},bool conservative=false) {
    std::vector<PcbPlacementObservation> frames;
    auto observer=std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint=[&](const auto& frame){frames.push_back(frame);}; input.experiment=observer;
    const auto probe=run_w12_stageprobe(input,tag,sheets,conservative);
    for (const auto& sheet : sheets) input.floorplan.spec->interior[sheet].layer="either";
    const auto zones=build_pcb_zone_geometry(input);
    const auto prepared=prepare_pcb_floorplan(input,zones);
    const auto expected=stage_expectations(input,probe,frames,prepared,tag);
    same(probe.document.data,expected.data,tag+" independently measured stage report");
    require(probe.output=="W12PROBE "+render_experiment_json(expected)+"\n",tag+" measured report bytes");
    // Reject plausible corruption, using the same validator as the positive
    // cases. Metrics cannot certify part/net identity by themselves.
    for (const auto* key : {"cross","total","n_cross","moved"}) {
        auto wrong=probe.document.data;
        experiment_detail::field(experiment_detail::field(wrong,"rows").array_value.at(4),key).number_value+=1;
        rejects([&]{same(wrong,expected.data,"wrong "+std::string(key));},tag+" wrong "+key);
    }
    for (const auto& entry : std::vector<std::pair<std::size_t,std::string>>{
            {1,"est_cross"},{1,"area"},{13,"cross"},{13,"total"},{13,"n_bottom"},{13,"n_top"}}) {
        const auto index=entry.first;
        const auto& key=entry.second;
        auto wrong=probe.document.data;
        experiment_detail::field(experiment_detail::field(wrong,"rows").array_value.at(index),key).number_value+=1;
        rejects([&]{same(wrong,expected.data,"wrong "+key);},tag+" wrong "+key);
    }
    auto wrong=frames;
    wrong.at(3).instances.front().x+=10;
    rejects([&]{(void)stage_expectations(input,probe,wrong,prepared,tag);},tag+" wrong checkpoint geometry");
    for (const auto* kind : {"ref","sheet","net","pin"}) {
        auto instances=frames.at(3).instances;
        auto& inst=instances.front();
        if (std::string(kind)=="ref") inst.ref="CORRUPTED_REFERENCE";
        if (std::string(kind)=="sheet") inst.sheet="CORRUPTED_SHEET";
        if (std::string(kind)=="net") inst.pad_nets.begin()->second={999999,"CORRUPTED_NET"};
        if (std::string(kind)=="pin") inst.pad_nets.erase(inst.pad_nets.begin());
        rejects([&]{experiment_metric_contracts::identity(input,instances,require);},tag+" wrong "+kind+" identity");
    }
    auto instances=frames.at(3).instances;
    auto& inst=instances.front();
    require(!inst.pad_nets.empty(),"combined pad mutation has a numbered pad");
    const auto pin=inst.pad_nets.begin()->first;
    auto mod=std::make_shared<PcbCheckFootprint>(*inst.mod);
    mod->pads.erase(std::remove_if(mod->pads.begin(),mod->pads.end(),[&](const auto& pad) {
        return std::get<0>(pad)==pin;
    }),mod->pads.end());
    inst.mod=mod; inst.pad_nets.erase(pin);
    rejects([&]{experiment_metric_contracts::identity(input,instances,require);},tag+" physical pad plus net entry deleted");
    instances=frames.at(3).instances; instances.erase(instances.begin());
    rejects([&]{experiment_metric_contracts::identity(input,instances,require);},tag+" missing instance");
    instances=frames.at(3).instances; instances.push_back(instances.front());
    rejects([&]{experiment_metric_contracts::identity(input,instances,require);},tag+" duplicate instance");
    auto wrong_tag=probe.document.data; experiment_detail::field(wrong_tag,"tag").string_value="CORRUPTED_TAG";
    rejects([&]{same(wrong_tag,expected.data,"requested tag");},tag+" wrong requested tag");
    return probe;
}
void measured_bound(PcbPlacementInput input) {
    using namespace experiment_detail;
    std::vector<FloorplanAttemptObservation> attempts;
    auto observer=std::make_shared<FloorplanExperiment>();
    observer->attempt_completed=[&](const auto& attempt) {
        attempts.push_back({attempt.w,attempt.h,attempt.packed,attempt.punch_free,std::nullopt});
    };
    observer->unscoped_estimate=[&](double value) {
        if (!attempts.empty()) attempts.back().estimate=py_round(value,1);
    };
    input.floorplan.experiment=observer;
    const auto bound=run_w12_bound(input,"bounds");
    require(!attempts.empty(),"bound performs actual packing attempts");
    std::vector<FloorplanAttemptObservation> outlines;
    for (const auto& attempt : attempts) {
        const auto hit=std::find_if(outlines.begin(),outlines.end(),[&](const auto& old) {
            return old.w==attempt.w && old.h==attempt.h && old.punch_free==attempt.punch_free;
        });
        if (hit==outlines.end()) outlines.push_back(attempt);
        else if (!hit->estimate && attempt.estimate) *hit=attempt;
    }
    std::stable_sort(outlines.begin(),outlines.end(),[](const auto& a,const auto& b) {
        return std::make_pair(a.punch_free,a.w*a.h)<std::make_pair(b.punch_free,b.w*b.h);
    });
    ExperimentDocument expected;
    expected.data=jo({{"tag",j("bounds")},{"K",j(input.floorplan.cross_budget_k)},
        {"n_calls",j(static_cast<double>(attempts.size()))},{"cands",ja()}});
    expected.float_paths.insert("/K");
    for (std::size_t i=0; i<outlines.size(); ++i) {
        const auto& o=outlines[i];
        field(expected.data,"cands").array_value.push_back(jo({{"w",j(o.w)},{"h",j(o.h)},
            {"packed",jb(o.packed)},{"free",jb(o.punch_free)},{"est",o.estimate ? j(*o.estimate) : JsonNode{}}}));
        for (const auto* key : {"w","h","est"}) expected.float_paths.insert("/cands/"+std::to_string(i)+"/"+key);
    }
    same(bound.document.data,expected.data,"current packing receipts independently grouped");
    require(bound.output=="W12BOUND "+render_experiment_json(expected)+"\n","bound receipt output bytes");
    auto wrong=bound.document.data; field(wrong,"n_calls").number_value+=1;
    rejects([&]{same(wrong,expected.data,"wrong attempt count");},"bound wrong attempt count");
    wrong=bound.document.data; field(field(wrong,"cands").array_value.front(),"w").number_value+=1;
    rejects([&]{same(wrong,expected.data,"wrong attempt outline");},"bound wrong candidate identity");
}
void historical_variant_metrics(const std::filesystem::path& root) {
    // Exact primitive oracle on immutable operands; no packing or placement
    // search runs here. A newly selected live plan cannot alter these vectors.
    const auto fixture=load(root,"carrier");
    auto input=fixture.input.floorplan;
    const auto& source=fixture.source;
    const auto& geometry=field(source,"geometry");
    auto offsets=[](const J& rows) {
        FloorplanOffsets result;
        for (const auto& [key,value] : rows.object_value) result[key]=point(value);
        return result;
    };
    auto strings_map=[](const J& rows) {
        std::map<std::string,std::string> result;
        for (const auto& [key,value] : rows.object_value) result[key]=value.string_value;
        return result;
    };
    auto rotations=[](const J& rows) {
        FloorplanRotations result;
        for (const auto& [key,value] : rows.object_value) result[key]=value.number_value;
        return result;
    };
    auto& g=input.geometry; g={};
    g.zone_box=offsets(field(geometry,"zone_box"));
    g.resolvable=strings_map(field(geometry,"resolvable")); g.side_of=strings_map(field(geometry,"side_of"));
    g.conn_edge=strings_map(field(geometry,"conn_edge")); g.conn_rot=rotations(field(geometry,"conn_rot"));
    g.zone_extra_rot=rotations(field(geometry,"zone_extra_rot")); g.mh_refs=strings(field(geometry,"mh_refs"));
    for (const auto& [sheet,rows] : field(geometry,"top_off").object_value) g.top_off[sheet]=offsets(rows);
    for (const auto& [sheet,rows] : field(geometry,"bot_off").object_value) g.bot_off[sheet]=offsets(rows);
    for (const auto& [sheet,rows] : field(geometry,"shapes").object_value) for (const auto& row : rows.array_value) {
        FloorplanZoneShape shape; shape.w=number(row,"w"); shape.h=number(row,"h"); shape.side=string(row,"side");
        shape.top_off=offsets(field(row,"top_off")); shape.bot_off=offsets(field(row,"bot_off"));
        shape.extra_rot=rotations(field(row,"extra_rot")); shape.mirror=strings_map(field(row,"mirror"));
        g.shapes[sheet].push_back(std::move(shape));
    }
    input.footprints.clear();
    for (const auto& [key,row] : field(source,"footprints").object_value)
        input.footprints[key]={string(row,"source"),sexpr_loads(string(row,"text"))};
    input.footprint_of=strings_map(field(source,"footprint_of"));
    input.impedance_net_classes=strings_map(field(source,"impedance_net_classes"));
    const auto vectors=parse_json_file((root/"native/tests/data/experiment_tools/carrier_via_vectors.json").string());
    std::size_t cases=0;
    for (const auto& row : field(vectors,"cases").array_value) {
        auto plan=fixture.stage.plan;
        bool found=false;
        for (auto* blocks : {&plan.edge_blocks,&plan.interior_blocks}) for (auto& block : *blocks)
            if (block.name==string(row,"sheet")) {block.shape_idx=static_cast<int>(number(row,"shape")); block.side="bottom"; found=true;}
        require(found,"immutable variant has a fixture block");
        const auto& costs=field(row,"costs").array_value;
        const auto& expected=field(row,"expected").array_value;
        require(costs.size()==expected.size(),"complete immutable variant vectors");
        for (std::size_t i=0; i<costs.size(); ++i) {
            auto experiment=std::make_shared<FloorplanExperiment>(); experiment->ordinary_via_mm=costs[i].number_value;
            input.experiment=experiment;
            const auto label=string(row,"sheet")+" shape "+std::to_string(static_cast<int>(number(row,"shape")))+" cost "+std::to_string(i);
            require(measure_floorplan_experiment_plan(input,plan).estimate==expected[i].number_value,
                    "immutable native variant metric "+label);
            require(experiment_metric_contracts::estimate(input,plan)==expected[i].number_value,
                    "immutable independent variant metric "+label);
            ++cases;
        }
    }
    require(cases>0,"immutable variant metric coverage is nonempty");
    std::cout<<"carrier: "<<cases<<" immutable variant cost vectors passed\n";
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
        const auto oracle=experiment_metric_contracts::lengths(m.insts);
        require(oracle.cross==expected[0].number_value&&oracle.total==expected[1].number_value&&oracle.n_cross==expected[2].number_value,
                "test metric oracle agrees with immutable primitive vectors");
    }
    historical_probe_formats(root);
    historical_variant_metrics(root);
}
void probes(const std::filesystem::path &root, const std::string &project) {
    auto fixture=load(root,project);
    const auto base=root/"native/tests/data/experiment_tools";
    const auto probe=measured_probe(fixture.input,"independent");
    if(project=="devkit_mini") {
        auto conservative=measured_probe(fixture.input,"conservative",{},true);
        require(!conservative.placement.floorplan.plan.punch_free,"forced conservative is genuine solver result");
        measured_bound(fixture.input);
        auto input=fixture.input;
        auto via=std::make_shared<FloorplanExperiment>();via->ordinary_via_mm=5.;
        input.floorplan.experiment=via;
        (void)measured_probe(input,"mutation",{"power_mon"});
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
            const auto &costs=field(row,"costs").array_value;
            std::optional<double> first;
            for(std::size_t i=0;i<costs.size();++i) {
                auto observer=std::make_shared<FloorplanExperiment>();observer->ordinary_via_mm=costs[i].number_value;
                prepared.experiment=observer;
                const auto value=measure_floorplan_experiment_plan(prepared,plan).estimate;
                const auto expected=experiment_metric_contracts::estimate(prepared,plan);
                require(value==expected,"independent via-cost candidate estimate "+string(row,"sheet")+" "+std::to_string(i));
                if (!first) first=value;
                changed|=value!=*first;
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
            if (std::string(project)=="carrier" && string(e,"name")=="board_aux") {
                const auto live = parse_circuit_ir(parse_json_text(dump.bytes, "live native dump"));
                // Keep the current dump intact for publication below. Its exact
                // serializer roundtrip plus the projected historical byte hash
                // cover formatting as well as the independently asserted delta.
                const auto handle = paths.subsystems_dir/"board_aux/board_aux.cpp";
                require(experiment_circuit_json_path(handle) == dump.path,
                    "native C++ handle preserves canonical output path");
                require(prepare_native_circuit_dump(live, handle).bytes == dump.bytes,
                    "current board_aux canonical dump roundtrip bytes");
                historical_input_contracts::check(live, project, [&](const auto& projected) {
                    const auto bytes = prepare_native_circuit_dump(projected, handle).bytes;
                    return bytes.size()==number(e,"bytes") && pcb_sha256(bytes)==string(e,"sha256");
                });
            } else {
                require(dump.bytes.size()==number(e,"bytes") && pcb_sha256(dump.bytes)==string(e,"sha256"),std::string(project)+" independent dump bytes "+string(e,"name"));
            }
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
