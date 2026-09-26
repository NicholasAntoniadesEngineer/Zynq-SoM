#include "board_pipeline_internal.hpp"
#include "schgen/selftest_full.hpp"
#include "schgen/process.hpp"
#include <iostream>
#include <png.h>
#include <unistd.h>

namespace {
using namespace schgen;
using namespace schgen::board_pipeline_detail;
std::size_t checks=0;
void require(bool ok,const std::string& message){++checks;if(!ok)throw std::runtime_error(message);}
template<class F>void rejects(F f,const std::string& message){bool caught=false;try{f();}catch(const std::exception&){caught=true;}require(caught,message);}
const JsonNode& field(const JsonNode& n,const std::string& name){const auto* p=object_field(n,name);if(!p)throw std::runtime_error("missing fixture field "+name);return *p;}
void cc(const JsonNode& expected){
    CircuitSheetIr circuit;circuit.name="fixture";circuit.nets={{"A","signal",{{"P1","1"},{"P2","1"}}},{"B","signal",{{"P3","1"}}}};
    SymbolDef symbol;symbol.pins.push_back({"1","P","passive",0,0,0,2.54,false});
    const auto resolver=[&](const std::string&)->const SymbolDef&{return symbol;};
    for(const auto& name:{"good","open","short","labels","missing"}){
        SchematicRoutePlacement p;
        for(int i=0;i<3;++i){if(std::string(name)=="missing"&&i==1)continue;SchematicPlacedPart part;part.ref="P"+std::to_string(i+1);part.lib_id="test:P";part.x=i*10;p.parts.push_back(part);}
        SchematicRoutedSheet routed;
        if(std::string(name)=="good")routed.segs.push_back({0,0,10,0,"deliberately wrong net"});
        if(std::string(name)=="short")routed.segs.push_back({0,0,20,0,"declared net must NOT seed union"});
        if(std::string(name)=="labels"){p.hlabels.push_back({"A",0,0});p.llabels.push_back({"A",10,0});}
        const auto result=check_board_sheet_cc(circuit,p,routed,resolver);const auto& e=field(expected,name);
        require(result.ok()==field(e,"ok").bool_value,std::string(name)+" independent CC verdict");
        require(result.n_components==field(e,"n_components").number_value,"independent geometry components");
        require(result.n_declared==field(e,"n_declared").number_value,"independent declared census");
        for(const auto& pair:std::vector<std::pair<std::string,std::vector<std::string>>>{{"shorts",result.shorts},{"opens",result.opens}}){
            const auto& values=field(e,pair.first).array_value;require(values.size()==pair.second.size(),"independent finding count");
            for(std::size_t k=0;k<values.size();++k)require(values[k].string_value==pair.second[k],"independent exact CC finding");}
    }
    SchematicRoutePlacement p;SchematicPlacedPart a;a.ref="P1";a.lib_id="test:P";p.parts.push_back(a);
    rejects([&]{check_board_sheet_cc(circuit,p,{},[](const std::string&)->const SymbolDef&{throw SymbolError("unavailable");});},"missing symbol cannot pass CC");
}
void ledger(){
    NativeLedgerDeclaration a;a.name="caller_override";a.kind="ASSUME";a.step="floorplan.sizing";a.source="policy";a.covers={"actual.cpp::caller_override"};a.basis="Explicit caller input";a.resolve=[] {return number(0.7);};
    NativeLedgerDeclaration d;d.name="area";d.kind="CALC";d.step="sizing.pass";d.inputs={"w","h"};d.expression="w*h";d.basis="Actual producer observation";d.repeated=true;
    const std::vector<NativeLedgerDeclaration> declarations{a,d};
    FloorplanAccounting result;result.decisions={
        {"floorplan.sizing","STEP","floorplan.sizing",text(""),{},0,""},
        {"floorplan.sizing","ASSUME","caller_override",number(.7),{},1,""},
        {"floorplan.sizing","STEP","sizing.pass",text("trial"),{},1,""},
        {"sizing.pass","CALC","area",number(999),{{"w",number(3)},{"h",number(4)}},2,""}};
    NativeLedger l;for(const auto& x:declarations)l.declare(x);import_board_floorplan_ledger(l,result,declarations);
    require(l.audit_state().recorded==std::set<std::string>{"caller_override","area"},"actual decisions recorded");
    require(l.render().find("999")!=std::string::npos,"ledger imports actual result; never recomputes formula to 12");
    require(l.audit_state().problems.empty(),"steps close without missing nesting");
    auto wrong=result;wrong.decisions[1].value=number(.5);NativeLedger fresh;for(const auto& x:declarations)fresh.declare(x);
    rejects([&]{import_board_floorplan_ledger(fresh,wrong,declarations);},"overridden assumption mismatch rejected");require(fresh.entries().empty(),"invalid stream preflight atomic");
    wrong=result;wrong.decisions.back().inputs[0].first="foreign";
    rejects([&]{import_board_floorplan_ledger(fresh,wrong,declarations);},"input drift rejects before import");
    rejects([&]{import_board_floorplan_ledger(fresh,result,{});},"unknown decision never auto-declared");
    rejects([&]{import_board_floorplan_ledger(fresh,{},declarations);},"missing decisions never pass");
    wrong=result;wrong.decisions.back().depth=4;rejects([&]{import_board_floorplan_ledger(fresh,wrong,declarations);},"invalid nesting rejects");
    wrong=result;wrong.decisions.erase(wrong.decisions.begin()+1);rejects([&]{import_board_floorplan_ledger(fresh,wrong,declarations);},"missing measured assumption cannot be blessed by step entry");
    wrong=result;wrong.decisions.insert(wrong.decisions.begin()+1,wrong.decisions[1]);rejects([&]{import_board_floorplan_ledger(fresh,wrong,declarations);},"duplicate assumption rejects");
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
    PcbPlacementResult p;p.zone_accounting_ownership=PcbZoneAccountingOwnership::IncludedInFloorplan;p.floorplan.plan.accounting.quantization_engagements={{"quant_credit",7}};p.zone_accounting.quantization_engagements={{"quant_credit",3}};p.placement_accounting.quantization_engagements={{"quant_credit",2}};
    require(inbox.merge_once("pcb/placement",pcb_placement_accounting(p)),"actual aggregate imported");require(!inbox.merge_once("pcb/placement",pcb_placement_accounting(p)),"same import idempotent");require(q.engagements().at("quant_credit")==AuditInteger(9),"no parent-child double count");
}
void policy(const JsonNode& reference){
    BoardPipelineResult empty;require(!empty.ok()&&!empty.complete(),"empty pipeline cannot pass");
    for(const auto& name:field(reference,"advisory").array_value)require(!board_pipeline_gate_mandatory(name.string_value),"independently captured advisory policy");
    for(const auto* name:{"cc","sheet_gates","pcb_drc","assembly","fanout","return_stitch","escape_lanes","quantize_census","fallbacks","stage_movement","ledger","manifest","si"})require(board_pipeline_gate_mandatory(name),"mandatory policy "+std::string(name));
    empty.quantization["large"]=AuditInteger::decimal("18446744073709551615");
    const auto rendered=board_pipeline_verdict_json(empty);require(rendered.find("18446744073709551615")!=std::string::npos,"machine report retains exact uint64 decimal");require(rendered.find("\"board_ok\": false")!=std::string::npos,"machine report derives final verdict");
}
void coverage(){
    CircuitSheetIr sheet;sheet.name="coverage";
    for(const auto* ref:{"U1","C1","R1"}){CircuitPartIr part;part.ref=ref;part.value="test";sheet.parts.push_back(part);}
    const auto contract=parse_json_text(R"({"structures":[{"ic":"U1","caps":["C1"]}],"free":[{"ref":"R1","why":"reviewed mechanical strap"}]})");
    const auto covered=check_board_contract_coverage({sheet},{{sheet.name,contract}},{});
    require(covered.ok()&&covered.parts==3&&covered.structured==2&&covered.free==1,
            "coverage counts structured and explicit free parts once");
    const auto missing=check_board_contract_coverage({sheet},{},{},true);
    require(!missing.ok()&&missing.ungated==3&&missing.report.find("(HARD)")!=std::string::npos,
            "unplaced wired parts remain visible when contracts are missing");
    const auto partial=parse_json_text(R"({"roles":{"U1":"controller"},"free":[{"ref":"U1","why":"redundant"},{"ref":"R1","why":"strap"}]})");
    const auto uncovered=check_board_contract_coverage({sheet},{{sheet.name,partial}},{{sheet.name,{{"C1","C42"}}}});
    require(!uncovered.ok()&&uncovered.structured==1&&uncovered.free==1&&uncovered.ungated==1,
            "redundant free entry cannot cover another part");
    require(uncovered.report.find("C42")!=std::string::npos&&uncovered.report.find("redundant")!=std::string::npos,
            "coverage preserves board references and redundant-entry diagnostics");
    rejects([&]{check_board_contract_coverage({sheet,sheet},{},{});},"duplicate sheets cannot hide coverage");
}
struct Temp{fs::path path;Temp(){auto s=(fs::temp_directory_path()/"schgen_pipeline_contract_XXXXXX").string();if(!::mkdtemp(s.data()))throw std::runtime_error("temp");path=s;}~Temp(){std::error_code e;fs::remove_all(path,e);}};
void golden(const fs::path& root){
    Temp tmp;const auto reference=parse_json_file((root/"native/tests/data/board_pipeline/golden_reference.json").string());
    for(const auto& sample:field(reference,"cases").array_value){
        const auto w=static_cast<unsigned>(field(sample,"w").number_value),h=static_cast<unsigned>(field(sample,"h").number_value);
        std::vector<unsigned char> pixels(static_cast<std::size_t>(w)*h*4);
        for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x){const auto i=(static_cast<std::size_t>(y)*w+x)*4;pixels[i]=(x*31+y*17)%256;pixels[i+1]=(x*7+y*47)%256;pixels[i+2]=(x*x+y*13)%256;pixels[i+3]=(x+y)%256;}
        png_image image{};image.version=PNG_IMAGE_VERSION;image.width=w;image.height=h;image.format=PNG_FORMAT_RGBA;
        const auto path=tmp.path/"sheet.png";
        require(png_image_write_to_file(&image,path.c_str(),0,pixels.data(),0,nullptr)!=0,"test PNG written");png_image_free(&image);
        require(board_png_average_hash(path)==field(sample,"hash").string_value,"independent Pillow hash "+std::to_string(w)+"x"+std::to_string(h));
    }
    // Invalid excluded PNGs prove that duplicate/ratsnest names are not decoded.
    for(const auto* name:{"sheet 2.png","sheet ٢.png","ratsnest_top.png","ignored.PNG"})publish_text(tmp.path/name,"not PNG");
    auto result=check_board_golden(tmp.path);require(!result.match&&!result.have_baseline&&!result.blessed,"missing golden is explicit drift");
    require(result.current.size()==1&&!fs::exists(tmp.path/"golden.json"),"no implicit golden blessing");
    result=check_board_golden(tmp.path,true);require(result.match&&result.blessed&&result.current.size()==1,"explicit bless writes only real sheets");
    const auto pinned=read(tmp.path/"golden.json");require(check_board_golden(tmp.path).match,"native golden comparison matches");
    auto hash=result.current.at("sheet");for(std::size_t i=0;i<12;++i)hash[i]=hash[i]=='0'?'1':'0';
    publish_text(tmp.path/"golden.json","{\"sheet\":\""+hash+"\"}\n");require(check_board_golden(tmp.path).match,"exactly twelve bits tolerated");
    hash[12]=hash[12]=='0'?'1':'0';const auto drift="{\"sheet\":\""+hash+"\"}\n";
    publish_text(tmp.path/"golden.json",drift);require(!check_board_golden(tmp.path).match,"thirteen bits reports drift");require(read(tmp.path/"golden.json")==drift,"drift never waived by replacing baseline");
    publish_text(tmp.path/"golden.json",pinned);fs::rename(tmp.path/"sheet.png",tmp.path/"new.png");
    result=check_board_golden(tmp.path);require(!result.match&&result.drift.size()==2,"new/missing sheets both reported");
    publish_text(tmp.path/"golden.json","{\"bad\":\"1\"}");rejects([&]{check_board_golden(tmp.path);},"invalid baseline rejected");
    require(check_board_golden(tmp.path,true).blessed,"explicit bless may replace invalid baseline");
    publish_text(tmp.path/"broken.png","not PNG");rejects([&]{check_board_golden(tmp.path,true);},"corrupt current render cannot be blessed");
}
void failed_inputs(const fs::path& root){
    Temp tmp;ProjectPaths p;p.repository_root=root;p.project_root=tmp.path/"source";p.subsystems_dir=p.project_root/"subsystems";p.sheet_index_file=p.project_root/"sheet_index.json";
    BoardPipelineOptions o;o.output_root=tmp.path/"out";o.no_render=true;
    const auto r=run_board_pipeline(p,o);require(!r.ok(),"missing project cannot claim board success");require(r.gates.size()>=40,"all mandatory downstream stages explicitly fail");
    const auto report=parse_json_file((o.output_root/"reports/board_verdicts.json").string());require(!field(report,"board_ok").bool_value,"published verdict includes final failure");
    for(const auto& g:r.gates)require(g.status==BoardGateStatus::failed,"missing prerequisite never implicit skip");
    // Test aggregation policy explicitly, not a simulated production build.
    auto policy_result=r;policy_result.sheets=1;for(auto& g:policy_result.gates)g.status=BoardGateStatus::passed;
    require(policy_result.ok(),"all required passed policy rows aggregate");
    for(std::size_t i=0;i<policy_result.gates.size();++i){auto mutation=policy_result;mutation.gates[i].status=BoardGateStatus::failed;mutation.gates[i].mandatory=false;
        require(!mutation.ok(),"mandatory status cannot be downgraded by caller bool: "+mutation.gates[i].name);
        mutation=policy_result;mutation.gates.erase(mutation.gates.begin()+static_cast<std::ptrdiff_t>(i));require(!mutation.ok(),"missing mandatory stage fails");}
    for(const auto* name:{"manual","scfw"}){auto mutation=policy_result;for(auto& g:mutation.gates)if(g.name==name)g.status=BoardGateStatus::skipped;require(mutation.ok(),"only explicit absent-input document skips allowed");}
    auto advisory=policy_result;advisory.gates.push_back({"return_path",false,BoardGateStatus::failed,"fixed SoM interface"});require(advisory.ok(),"legacy v1 return-path remains advisory");
    advisory.gates.push_back({"golden",false,BoardGateStatus::unavailable,"native capability missing"});require(advisory.ok()&&!advisory.complete(),"missing advisory remains explicit, not a fake PASS");
    advisory.gates.push_back(advisory.gates.front());require(!advisory.ok(),"duplicate result cannot mask gate");
    for(const auto& file:board_pipeline_audit_sources())require(fs::is_regular_file(root/file.path),"required native audit file exists: "+file.path);
}
void live_schematic(const fs::path& root){
    Temp tmp;auto paths=resolve_project_paths(root,fs::path("devkit_mini"));paths.project_root=tmp.path/"synthetic";paths.subsystems_dir=paths.project_root/"subsystems";
    BoardPipelineOptions o;o.output_root=tmp.path/"out";o.no_render=true;o.spice.allow_ngspice=false;
    // Real KiCad, never a success script. The contract is explicit opt-in below.
    Context c(paths,o);auto circuit=selftest_rc_fixture();c.circuits={{circuit.name,tmp.path/"circuit.json",circuit}};c.sheets={circuit};c.index={{circuit.name,1}};
    schematic_stage(c);
    for(const auto* name:{"sheet_gates","cc","board_schematic"}){const auto p=std::find_if(c.result.gates.begin(),c.result.gates.end(),[&](const auto& g){return g.name==name;});require(p!=c.result.gates.end()&&p->status==BoardGateStatus::passed,"live native stage "+std::string(name)+(p==c.result.gates.end()?" missing":": "+p->report));}
    require(fs::is_regular_file(o.output_root/"Zynq_Carrier.kicad_sch"),"actual hierarchy emitted in temporary tree");
    require(fs::is_regular_file(o.output_root/"reports/board.erc.rpt"),"actual root ERC report");
}
void live_electrical(const fs::path& root){
    Temp tmp;const auto paths=resolve_project_paths(root,fs::path("devkit_mini"));
    BoardPipelineOptions o;o.output_root=tmp.path/"out";o.no_render=true;o.spice.allow_ngspice=false;
    Context c(paths,o);c.circuits=load_project_circuits(paths);for(const auto& s:c.circuits)c.sheets.push_back(s.circuit);
    c.som=load_som_interface(paths.som_interface_file);c.link=link_sheets(c.sheets,parse_json_file(paths.som_interface_file.string()),parse_json_file((paths.project_root/"som_mapping.json").string()));
    electrical_stages(c);
    require(c.result.gates.size()==10,"composed electrical family executes every report");
    for(const auto& g:c.result.gates)if(g.mandatory)require(g.status==BoardGateStatus::passed,"live devkit electrical gate "+g.name+": "+g.report);
    require(c.power&&c.testpoints&&c.spice,"computed results retained for dependent docs; no recomputation required");
}
void authored_inputs(const fs::path& root){
    require(open_part_catalog((root/"native/catalog.bin").string()),"open repository part catalog");
    for(const auto* project:{"carrier","devkit_mini"}){
        const auto paths=resolve_project_paths(root,fs::path(project));
        auto authored=author_board_pipeline_inputs(paths);
        const auto reference=load_project_circuits(paths);
        require(authored.circuits.size()==reference.size(),"live native authoring sheet census");
        for(const auto& expected:reference){
            const auto found=std::find_if(authored.circuits.begin(),authored.circuits.end(),
                [&](const auto& actual){return actual.name==expected.name;});
            require(found!=authored.circuits.end(),"live native factory missing "+expected.name);
            require(json(authored_circuit_json(found->circuit))==json(authored_circuit_json(expected.circuit)),
                    "native factory differs from canonical hardware IR: "+expected.name);
        }
        Temp tmp;
        publish_board_pipeline_inputs(authored,paths,tmp.path);
        for(const auto& actual:authored.circuits){
            require(actual.path==tmp.path/"subsystems"/actual.name/"circuit.json","isolated authoring output path");
            require(json(authored_circuit_json(load_circuit_json(actual.path)))==json(authored_circuit_json(actual.circuit)),
                    "published snapshot differs from retained live IR");
        }
    }
}
}
int main(int argc,char** argv){
    try{
        if(argc<2||argc>3)throw std::runtime_error("usage: board_pipeline_contracts REPOSITORY [--live-kicad]");
        const fs::path root=argv[1];
        const auto reference=parse_json_file((root/"native/tests/data/board_pipeline/python_reference.json").string());
        cc(field(reference,"cc"));ledger();policy(reference);coverage();golden(root);
        failed_inputs(root);live_electrical(root);authored_inputs(root);
        if(argc==3){
            if(std::string(argv[2])!="--live-kicad")throw std::runtime_error("unknown mode");
            live_schematic(root);
        }
        std::cout<<"Board pipeline: "<<checks<<" contracts passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<"Board pipeline: "<<e.what()<<'\n';return 1;}
}
