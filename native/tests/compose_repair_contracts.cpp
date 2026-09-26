#include "pcb_placement_fixture.hpp"
#include "schgen/compose_repair.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/legalize.hpp"
#include "../src/accurate_norm.hpp"
#include <cstdlib>
#include <unistd.h>
#include <cmath>
#include <iostream>

namespace {
using namespace schgen;
using placement_fixture::field;
using placement_fixture::string;
using placement_fixture::read;
using J=JsonNode;
std::size_t checks=0;
void require(bool ok,const std::string &why){++checks;if(!ok)throw std::runtime_error(why);}
void same(const J &a,const J &b,const std::string &where) {
    require(a.kind==b.kind,where+" type");
    if(a.kind==JsonKind::Object){require(a.object_value.size()==b.object_value.size(),where+" size");for(const auto &[k,v]:b.object_value)same(field(a,k),v,where+"/"+k);}
    else if(a.kind==JsonKind::Array){require(a.array_value.size()==b.array_value.size(),where+" size");for(std::size_t i=0;i<b.array_value.size();++i)same(a.array_value[i],b.array_value[i],where+"/"+std::to_string(i));}
    else if(a.kind==JsonKind::String)require(a.string_value==b.string_value,where+" actual="+a.string_value+" expected="+b.string_value);
    else if(a.kind==JsonKind::Number)require(a.number_value==b.number_value,where+" actual="+std::to_string(a.number_value)+" expected="+std::to_string(b.number_value));
    else if(a.kind==JsonKind::Bool)require(a.bool_value==b.bool_value,where+" bool");
}
ComposeDocument subdoc(const ComposeDocument &doc,const J &n,const std::string &path) {
    ComposeDocument out;out.data=n;
    for(const auto &p:doc.float_paths)if(p.compare(0,path.size()+1,path+"/")==0)out.float_paths.insert(p.substr(path.size()));
    for(const auto &[p,v]:doc.integer_tokens)if(p.compare(0,path.size()+1,path+"/")==0)out.integer_tokens[p.substr(path.size())]=v;
    return out;
}
std::vector<std::string> strings(const J &a){std::vector<std::string> out;for(const auto &s:a.array_value)out.push_back(s.string_value);return out;}
ComposeTermKey key(const J &n){return {n.array_value.at(0).string_value,n.array_value.at(1).string_value,n.array_value.at(2).string_value};}
ComposeSpecEdit edit(const J &fields,const std::string &type) {
    ComposeSpecEdit e;
    if(type=="SetPullWeight")e.kind=ComposeEditKind::SetPullWeight;
    if(type=="MoveEdgeBlock")e.kind=ComposeEditKind::MoveEdgeBlock;
    if(type=="CompositeEdit")e.kind=ComposeEditKind::Composite;
    for(const auto &[k,v]:fields.object_value){
        if(k=="block")e.block=v.string_value;else if(k=="to")e.to=v.string_value;else if(k=="weight")e.weight=v.number_value;
        else if(k=="face")e.face=v.string_value;else if(k=="basis")e.basis=v.string_value;else if(k=="name")e.name=v.string_value;
        else if(k=="from_edge")e.from_edge=v.string_value;else if(k=="to_edge")e.to_edge=v.string_value;else if(k=="exclusive")e.exclusive=v.bool_value;
        else if(k=="target_key"&&v.kind!=JsonKind::Null)e.target_key=key(v);
        else if(k=="edits")for(const auto &c:v.array_value)e.edits.push_back(edit(c,object_field(c,"edits")?"CompositeEdit":object_field(c,"name")?"MoveEdgeBlock":object_field(c,"to")?"AddPull":"SetPullWeight"));
    }return e;
}
void edit_same(const ComposeSpecEdit &e,const J &r,const std::string &label) {
    const auto expected=edit(field(r,"fields"),string(r,"type"));
    require(e.describe()==string(r,"description"),label+" description");
    require(e.intent()==field(field(r,"fields"),"intent").bool_value,label+" intent");
    require(e.kind==expected.kind&&e.target_key==expected.target_key&&e.block==expected.block&&e.to==expected.to&&e.weight==expected.weight&&e.face==expected.face&&e.exclusive==expected.exclusive&&e.basis==expected.basis&&e.name==expected.name&&e.from_edge==expected.from_edge&&e.to_edge==expected.to_edge,label+" fields");
    require(e.edits.size()==expected.edits.size(),label+" children");
    for(std::size_t i=0;i<e.edits.size();++i)require(e.edits[i].describe()==expected.edits[i].describe()&&e.edits[i].basis==expected.edits[i].basis&&e.edits[i].target_key==expected.edits[i].target_key,label+" child fields");
}
void units(const std::filesystem::path &base) {
    const auto doc=parse_compose_document(read(base/"python.json"));
    const auto &root=doc.data;
    std::size_t i=0;
    for(const auto &r:field(root,"accept").array_value) {
        const auto p="/accept/"+std::to_string(i++);
        std::set<ComposeTermKey> targets;for(const auto &k:field(r,"target_keys").array_value)targets.insert(key(k));
        const auto got=accept_compose_repair(subdoc(doc,field(r,"before"),p+"/before"),subdoc(doc,field(r,"after"),p+"/after"),targets,field(r,"allow_area_growth").bool_value);
        require(got.ok==field(r,"ok").bool_value,string(r,"name")+" verdict");
        require(got.reasons==strings(field(r,"reasons")),string(r,"name")+" reasons"+(got.reasons.empty()?"":got.reasons.front()));
    }
    for(const auto &r:field(root,"edits").array_value) {
        const auto raw=parse_compose_document(string(r,"raw"));const auto &er=field(r,"edit");const auto e=edit(field(er,"fields"),string(er,"type"));
        edit_same(e,er,"edit");const auto original=render_compose_json(raw);
        std::string error;
        try {const auto output=render_compose_json(e.apply(raw));require(!object_field(r,"error"),"expected edit failure");require(output==string(r,"output"),"edit bytes "+e.describe());}
        catch(const std::invalid_argument &ex){error=ex.what();}
        if(auto want=object_field(r,"error"))require(error==want->string_value,"edit error "+error);
        else require(error.empty(),"unexpected edit error "+error);
        require(render_compose_json(raw)==original,"input mutation");
    }
    for(const auto &r:field(root,"intent").array_value) {
        std::string error;
        try{auto got=parse_compose_allow_intent(strings(field(r,"items")));require(!object_field(r,"error"),"intent expected error");const auto &expected=field(r,"edits").array_value;require(got.size()==expected.size(),"intent count");for(std::size_t k=0;k<got.size();++k)edit_same(got[k],expected[k],"intent");}
        catch(const std::invalid_argument &ex){error=ex.what();}
        if(auto want=object_field(r,"error"))require(error==want->string_value,"intent error "+error);else require(error.empty(),"unexpected intent error");
    }
    i=0;
    for(const auto &r:field(root,"proposals").array_value) {
        auto led=subdoc(doc,field(r,"ledger"),"/proposals/"+std::to_string(i++)+"/ledger");
        const auto proposed=propose_compose_repairs(led,parse_compose_document(string(r,"raw")),parse_compose_allow_intent(strings(field(r,"allow"))));
        const auto &expected=field(r,"edits").array_value;require(proposed.size()==expected.size(),"proposal count");
        for(std::size_t k=0;k<proposed.size();++k)edit_same(proposed[k],expected[k],"proposal");
        same(field(led.data,"intent_gated"),field(field(r,"ledger"),"intent_gated"),"intent gated");
    }
    for(const auto &r:field(root,"history").array_value) {
        const auto got=append_compose_ledger(parse_compose_document(string(r,"previous")),parse_compose_document(string(r,"ledger")),string(r,"step"));
        require(got.json==string(r,"json"),"history JSON bytes");require(got.markdown==string(r,"markdown"),"history Markdown bytes");
    }
}
void real_ledgers(const std::filesystem::path &root,const std::string &project) {
    auto fixture=placement_fixture::load(root,project);
    auto model=pcb_model_from_json(fixture.model,fixture.expected_pool);
    const auto rows=field(parse_json_file((root/"native/tests/data/compose_repair"/(project+"_strict.json")).string()),"rows").array_value;
    for(const auto &r:rows) {
        auto changed=model;
        if(string(r,"name")=="moved_power_first")for(auto &inst:changed.insts)if(inst.sheet=="power"){inst.x+=100;break;}
        if(string(r,"name")=="missing_power")changed.insts.erase(std::remove_if(changed.insts.begin(),changed.insts.end(),[](const auto &inst){return inst.sheet=="power";}),changed.insts.end());
        const auto got=measure_compose_ledger(fixture.input,changed);
        const auto expected=parse_compose_document(string(r,"ledger"));
        same(got.data,expected.data,project+"/"+string(r,"name"));
        require(render_compose_json(got,1,true)==string(r,"ledger"),project+"/"+string(r,"name")+" ledger bytes");
    }
}
FloorplanTermIndex index_from(const J &n) {
    FloorplanTermIndex out;
    for(const auto &[name,rows]:n.object_value) {
        auto &dst=name=="hard"?out.hard:name=="soft"?out.soft:out.na;
        for(const auto &row:rows.array_value) {
            FloorplanTerm t;t.kind=string(row,"kind");t.sheet=string(row,"sheet");t.subject=string(row,"subject");t.target_raw=string(row,"target_raw");t.basis=string(row,"basis");t.enforced=field(row,"enforced").bool_value;
            if(field(row,"bound").kind!=JsonKind::Null)t.bound=field(row,"bound").number_value;
            t.output_roles=strings(field(row,"output_roles"));t.out_refs=strings(field(row,"out_refs"));dst.push_back(t);
        }
    }return out;
}
double value(const J &n){if(n.kind==JsonKind::Number)return n.number_value;return n.string_value=="-Infinity"?-INFINITY:INFINITY;}
void predictions(const std::filesystem::path &root) {
    auto f=placement_fixture::load(root,"devkit_mini");
    const auto oracle=parse_json_file((root/"native/tests/data/compose_repair/predictions_strict.json").string());
    for(const auto &r:field(oracle,"predictions").array_value) {
        const auto e=edit(field(r,"edit"),string(r,"type"));std::string error;
        try {
            const auto got=evaluate_compose_candidate(f.input,parse_compose_document(string(r,"raw")),e,index_from(field(r,"index")));
            require(!object_field(r,"error"),"predicted expected error");
            require(got.area==field(r,"area").number_value,"prediction area");require(got.spilled==strings(field(r,"spilled")),"prediction spilled");
            require(render_compose_json(got.edited)==string(r,"edited"),"prediction edited bytes");
            const auto &evals=field(r,"evaluations").array_value;require(got.evaluations.size()==evals.size(),"prediction evaluation size");
            for(std::size_t i=0;i<evals.size();++i) {
                const auto &a=got.evaluations[i];const auto &b=evals[i];
                if(a.measured!=value(field(b,"measured")))std::cerr<<std::hexfloat<<"prediction hex actual="<<a.measured<<" expected="<<value(field(b,"measured"))<<std::defaultfloat<<'\n';
                require(a.measured==value(field(b,"measured")),"prediction measured "+a.term.kind+" "+std::to_string(a.measured)+" vs "+std::to_string(value(field(b,"measured"))));
                require(a.bound==value(field(b,"bound"))&&a.margin==value(field(b,"margin")),"prediction bound/margin");
                require(a.ok==field(b,"ok").bool_value&&a.note==string(b,"note"),"prediction verdict/note");
            }
        }catch(const FloorplanSpecError &ex){error=ex.what();}
        catch(const std::invalid_argument &ex){error=ex.what();}
        if(auto want=object_field(r,"error")) {
            auto expected=want->string_value;
            const auto colon=expected.find(": ");
            if(colon!=expected.npos&&expected.substr(0,colon).find(".json")!=expected.npos)expected=expected.substr(colon+2);
            require(!error.empty()&&error.find(expected)!=error.npos,"prediction error "+error+" vs "+expected);
        }else require(error.empty(),"unexpected prediction failure "+error);
    }
}
void publish(const std::filesystem::path &p,const std::string &bytes){write_atomic_file(p.string(),{bytes.begin(),bytes.end()});}
struct Scratch {
    std::filesystem::path path;
    Scratch(){char pattern[]="/private/tmp/compose-repair-test.XXXXXX";auto p=mkdtemp(pattern);if(!p)throw std::runtime_error("mkdtemp failed");path=p;}
    ~Scratch(){std::error_code ec;std::filesystem::remove_all(path,ec);}
};
void workflow(const std::filesystem::path &root) {
    auto f=placement_fixture::load(root,"devkit_mini");const auto base=pcb_model_from_json(f.model,f.expected_pool);
    const auto oracle=parse_json_file((root/"native/tests/data/compose_repair/workflow_strict.json").string());
    auto initial=base;
    initial.insts.erase(std::remove_if(initial.insts.begin(),initial.insts.end(),[](const auto &i){return i.sheet!="uart_bridge"&&i.sheet!="usb_uart_connector";}),initial.insts.end());
    for(auto &i:initial.insts)if(i.sheet=="uart_bridge")i.x+=50.;
    for(const auto &row:field(oracle,"drivers").array_value) {
        Scratch tmp;ComposeCommandPaths paths{tmp.path/"floorplan.json",tmp.path/"ledger.json",tmp.path/"ledger.md"};
        const auto original=string(row,"original"),mode=string(row,"mode");publish(paths.spec,original);
        ComposeCommandOptions options;options.repair=true;options.dry_run=mode=="dry";options.max_steps=static_cast<int>(field(row,"max_steps").number_value);
        int builds=0,runs=0;std::vector<std::string> observed;std::string streamed;
        ComposeCommandHost host;
        host.build_model=[&]{
            ++builds;auto input=f.input;input.floorplan.spec=floorplan_spec_from_json(parse_compose_document(read(paths.spec)).data,"floorplan.json");
            auto model=builds==1?initial:base;if(builds>1&&mode=="rejected")model.insts[0].x+=1000.;
            return ComposeBoardSnapshot{input,model};
        };
        // Transport harness only: this exit status is not claimed as a physical
        // board proof. Every before/after gate still measures the real model.
        host.run_board=[&]{++runs;observed.push_back(read(paths.spec));std::string text;for(int i=0;i<2003;++i)text+="µ";return ComposeBoardRun{mode=="failed"?7:0,mode=="failed"?text+"tail":""};};
        host.output=[&](const auto &s){streamed+=s;};
        const auto got=run_compose_command(options,paths,host);
        require(got.exit_code==field(row,"code").number_value,mode+" exit");
        require(got.output==string(row,"stdout"),mode+" stdout actual="+got.output+" expected="+string(row,"stdout"));
        require(got.output==streamed,mode+" output stream");require(builds==field(row,"build_calls").number_value&&runs==field(row,"board_calls").number_value,mode+" call budget");
        require(observed==strings(field(row,"observed")),mode+" explicit edit before board run");
        require(read(paths.spec)==string(row,"final_spec"),mode+" final spec bytes");
        require(read(paths.ledger_json)==string(row,"ledger"),mode+" ledger bytes");
        require(read(paths.ledger_markdown)==string(row,"markdown"),mode+" Markdown bytes");
        require(got.applied==(mode.rfind("success",0)==0),mode+" applied flag");
    }
    const auto original=string(field(oracle,"drivers").array_value.front(),"original");
    // Extra native safety properties: no fake success when a host is absent,
    // exceptions restore the exact source bytes, concurrent edits survive.
    for(const auto &mode:{"no-host","throws","concurrent","bad-intent","measure","no-candidates","native-rebuild"}) {
        Scratch tmp;ComposeCommandPaths paths{tmp.path/"floorplan.json",tmp.path/"ledger.json",tmp.path/"ledger.md"};publish(paths.spec,original);
        ComposeCommandOptions options;options.repair=std::string(mode)!="measure";
        if(std::string(mode)=="bad-intent")options.allow_intent={"bad"};
        int builds=0,runs=0;ComposeCommandHost host;
        host.build_model=[&]{
            ++builds;auto input=f.input;input.floorplan.spec=floorplan_spec_from_json(parse_compose_document(read(paths.spec)).data,"floorplan.json");
            auto model=(std::string(mode)=="no-candidates"||std::string(mode)=="measure")?base:initial;
            if(builds>1&&std::string(mode)=="native-rebuild")model=build_pcb_model(input).model;
            return ComposeBoardSnapshot{input,model};
        };
        if(std::string(mode)!="no-host")host.run_board=[&]() -> ComposeBoardRun {
            ++runs;
            if(std::string(mode)=="throws")throw std::runtime_error("host threw");
            if(std::string(mode)=="concurrent"){publish(paths.spec,"human edit\n");throw std::runtime_error("host threw after concurrent edit");}
            return {0,""};
        };
        std::string error;
        try{
            auto got=run_compose_command(options,paths,host);
            require(std::string(mode)=="measure"||std::string(mode)=="no-candidates"||std::string(mode)=="native-rebuild","expected driver failure");
            require(got.exit_code==0,std::string(mode)+" success");
            if(std::string(mode)=="native-rebuild")require(got.applied&&builds==2&&runs==1,"fresh native model acceptance");
            else require(!got.applied&&runs==0&&read(paths.spec)==original,"diagnostic does not apply");
        }catch(const std::exception &ex){error=ex.what();}
        if(std::string(mode)=="measure"||std::string(mode)=="no-candidates"||std::string(mode)=="native-rebuild")require(error.empty(),std::string(mode)+" "+error);
        else {
            require(!error.empty(),"missing boundary exception");
            require(!std::filesystem::exists(paths.ledger_json),"no success ledger after exception");
            require(read(paths.spec)==(std::string(mode)=="concurrent"?"human edit\n":original),"safe spec rollback");
            if(std::string(mode)=="bad-intent")require(builds==0&&runs==0,"intent validation first");
        }
    }
}
void ranking(const std::filesystem::path &root) {
    auto oracle=parse_json_file((root/"native/tests/data/compose_repair/ranking.json").string());std::vector<ComposeCandidate> cases;
    for(const auto &row:field(oracle,"candidates").array_value) {
        ComposeCandidate c;c.edit=edit(field(row,"edit"),"AddPull");c.area=field(row,"area").number_value;c.spilled=strings(field(row,"spilled"));c.error=string(row,"error");
        for(const auto &r:field(row,"evaluations").array_value) {
            const auto &t=field(r,"term");FloorplanTermEval ev;ev.term.kind=string(t,"kind");ev.term.subject=string(t,"subject");ev.term.target_raw=string(t,"target_raw");ev.term.enforced=field(t,"enforced").bool_value;
            ev.measured=value(field(r,"measured"));ev.bound=value(field(r,"bound"));ev.margin=value(field(r,"margin"));ev.ok=field(r,"ok").bool_value;c.evaluations.push_back(ev);
        }cases.push_back(c);
    }
    const auto got=rank_compose_candidates(cases);require(got.ranked.size()==field(oracle,"eligible_count").number_value,"ranking eligible count");require(got.output==string(oracle,"ranking_output"),"ranking exact output");
}
void kernels(const std::filesystem::path &root) {
    const auto oracle=parse_json_file((root/"native/tests/data/compose_repair/kernel_regressions.json").string());
    for(const auto &r:field(oracle,"channel").array_value)require(channel_demand_mm(static_cast<int>(field(r,"n").number_value),6,2.,.2)==field(r,"expected").number_value,"independent channel-demand rounding");
    for(const auto &r:field(oracle,"facing").array_value) {
        const auto a=placement_fixture::point(field(r,"zone")),b=placement_fixture::point(field(r,"output")),c=placement_fixture::point(field(r,"down"));
        const auto result=accurate_facing_dot(a.first,a.second,b.first,b.second,c.first,c.second);
        require(result.first==field(r,"expected").array_value[0].number_value,"independent facing dot");
        require(result.second==field(r,"expected").array_value[1].number_value,"independent facing angle");
    }
}
} // namespace
int main(int argc,char **argv) {
    try {
        if(argc!=2)throw std::runtime_error("usage: compose_repair_contracts REPO_ROOT");
        const std::filesystem::path root=argv[1];units(root/"native/tests/data/compose_repair");
        for(const auto *project:{"carrier","devkit_mini"})real_ledgers(root,project);
        workflow(root);
        ranking(root);
        kernels(root);
        predictions(root);
        std::cout<<"compose repair contracts: "<<checks<<" passed\n";return 0;
    }catch(const std::exception &ex){std::cerr<<"compose repair contract FAILED after "<<checks<<": "<<ex.what()<<'\n';return 1;}
}
