#include "schgen/board_schematic.hpp"
#include "schgen/atomic_file.hpp"

#include <algorithm>
#include <cstdlib>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <set>
#include <thread>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
std::size_t checks = 0;
void require(bool value, const std::string& why) { ++checks; if (!value) throw std::runtime_error(why); }
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* found = object_field(n,key); if (!found) throw std::runtime_error("missing fixture field " + key); return *found;
}
std::string str(const JsonNode& n, const std::string& key) { return field(n,key).string_value; }
double num(const JsonNode& n, const std::string& key) { return field(n,key).number_value; }
std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary); require(bool(in),"cannot read " + path.string());
    return {std::istreambuf_iterator<char>(in),{}};
}
void write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path()); write_atomic_file(path.string(),{text.begin(),text.end()});
}
void equal_text(const std::string& a, const std::string& b, const std::string& why) {
    ++checks;
    if (a != b) { std::size_t i=0;while(i<a.size()&&i<b.size()&&a[i]==b[i])++i;
        throw std::runtime_error(why + " differs at " + std::to_string(i) + ": " + a.substr(i,100) + " != " + b.substr(i,100)); }
}
template<class F> void rejects(F call, const std::string& part) {
    bool rejected=false;
    try { call(); } catch(const std::exception& err) { rejected=true; require(std::string(err.what()).find(part)!=std::string::npos,"wrong error: "+std::string(err.what())); }
    require(rejected,"expected rejection: "+part);
}
struct Scratch {
    fs::path path;
    Scratch() { auto value=(fs::temp_directory_path()/"schgen_board_contracts_XXXXXX").string();require(::mkdtemp(value.data())!=nullptr,"mkdtemp");path=value; }
    ~Scratch(){std::error_code error;fs::remove_all(path,error);}
};
SchematicDesign design(const JsonNode& n) { return schematic_design_from_json(n,parse_circuit_ir(field(n,"circuit"))); }
std::vector<SchematicDesign> designs(const JsonNode& n) { std::vector<SchematicDesign> out;for(const auto& v:n.array_value)out.push_back(design(v));return out; }
SchematicSymbolResolver resolver(SymbolLibrary& lib) { return [&lib](const std::string& lid)->const SymbolDef&{return lib.get(lid);}; }
std::vector<BoardPlacedSheet> placed(const std::vector<SchematicDesign>& ds) {
    std::vector<BoardPlacedSheet> out;for(const auto& d:ds)out.push_back({d.circuit.name,d,"unused"});return out;
}
ExtractedNetlist netlist(const JsonNode& n) {
    ExtractedNetlist out;for(const auto& row:n.array_value){std::vector<KicadNetlistPin> pins;
        for(const auto& p:row.array_value[1].array_value)pins.push_back({p.array_value[0].string_value,p.array_value[1].string_value});
        out.emplace_back(row.array_value[0].string_value,pins);}return out;
}
std::vector<BoardSheetDesign> hierarchy_inputs(const JsonNode& row) {
    std::vector<BoardSheetDesign> out;
    if(const auto* synthetic=object_field(row,"synthetic")) {
        for(int i=0;i<num(*synthetic,"sheets");++i) {
            SchematicDesign d;d.circuit.schema="schgen.circuit/1";d.circuit.name="s"+std::to_string(i);d.circuit.title="Geometry fixture";
            for(int k=0;k<num(*synthetic,"ports");++k){
                auto name="P"+std::string(k<10?2:k<100?1:0,'0')+std::to_string(k);
                if(field(*synthetic,"markup").bool_value)name=std::vector<std::string>{"~{RESET_N}","Ω😀","quote'line"}.at(k);
                d.circuit.nets.push_back({name,"port",{}});
                d.hlabels.push_back({name,0,0,0,std::vector<std::string>{"input","output","tri_state"}.at(k%3)});
            }
            out.push_back({std::move(d),i+1});
        }
    }else for(const auto& sheet:field(row,"sheets").array_value)out.push_back({design(field(sheet,"design")),static_cast<std::int64_t>(num(sheet,"band"))});
    return out;
}
void ir_renaming(const SchematicDesign& input, const SchematicDesign& result, std::int64_t band) {
    require(!result.standalone,"hierarchical child");require(input.circuit.parts.size()==result.circuit.parts.size(),"part count");
    for(std::size_t i=0;i<input.circuit.parts.size();++i)equal_text(result.circuit.parts[i].ref,board_renamed_ref(input.circuit.parts[i].ref,band),"part band");
    require(result.circuit.nets.size()==input.circuit.nets.size(),"net count");
    for(std::size_t i=0;i<input.circuit.nets.size();++i){const auto& a=input.circuit.nets[i];const auto& b=result.circuit.nets[i];
        equal_text(a.name,b.name,"net order/name");equal_text(a.net_class,b.net_class,"net class");require(a.pins.size()==b.pins.size(),"pin count");
        for(std::size_t p=0;p<a.pins.size();++p){equal_text(b.pins[p].ref,board_renamed_ref(a.pins[p].ref,band),"net pin band");equal_text(a.pins[p].pin,b.pins[p].pin,"pin number");}}
    require(input.circuit.nc.size()==result.circuit.nc.size(),"NC count");
    for(std::size_t p=0;p<input.circuit.nc.size();++p){equal_text(result.circuit.nc[p].ref,board_renamed_ref(input.circuit.nc[p].ref,band),"NC band");equal_text(input.circuit.nc[p].pin,result.circuit.nc[p].pin,"NC pin");}
    require(input.circuit.port_types.size()==result.circuit.port_types.size(),"port metadata retained");
    require(input.circuit.waivers.size()==result.circuit.waivers.size(),"waivers retained");
}
BoardPreparedSheet prepared(const SchematicDesign& d, SymbolLibrary& lib, const JsonNode* source=nullptr) {
    BoardPreparedSheet out;auto& p=out.placement;
    p.parts=d.parts;p.powers=d.powers;p.hlabels=d.hlabels;p.llabels=d.llabels;p.no_connects=d.no_connects;p.paper=d.paper;
    if(source)for(const auto& b:field(*source,"boxes").array_value)p.boxes.push_back({num(b,"x0"),num(b,"y0"),num(b,"x1"),num(b,"y1"),str(b,"kind"),str(b,"owner")});
    // Frozen emission primitives have no net field. Recover the names from
    // authoritative pin/label/power anchors along those fixed wire endpoints;
    // this does not move, add or repair any wire in the independent geometry.
    std::map<std::pair<double,double>,std::string> names;
    for(const auto& h:d.hlabels)names[{h.x,h.y}]=h.name;
    for(const auto& h:d.llabels)names[{h.x,h.y}]=h.name;
    for(const auto& h:d.powers)names[{h.x,h.y}]=h.net_name();
    for(const auto& part:d.parts)for(const auto& pin:lib.get(part.lib_id).pins)
        for(const auto& net:d.circuit.nets)for(const auto& pr:net.pins)
            if(pr.ref==part.ref&&pr.pin==pin.number)names[pin_page_position(pin,part.x,part.y,part.rotation)]=net.name;
    for(std::size_t pass=0;pass<d.wires.size();++pass)for(const auto& w:d.wires){
        const auto a=std::make_pair(w.x0,w.y0),b=std::make_pair(w.x1,w.y1);
        if(names.count(a))names[b]=names[a];else if(names.count(b))names[a]=names[b];
    }
    for(const auto& w:d.wires){const auto at=names.find({w.x0,w.y0});require(at!=names.end(),"unclassified frozen wire");out.routed.segs.push_back({w.x0,w.y0,w.x1,w.y1,at->second});}
    for(const auto& j:d.junctions)out.routed.junctions.push_back({j.x,j.y});return out;
}
void write_hierarchy(const BoardHierarchy& h, SymbolLibrary& lib, const fs::path& dir,
                     const std::string& name,const std::string& subdir) {
    for(const auto& s:h.sheets)write(dir/subdir/(s.name+".kicad_sch"),emit_schematic(s.design,resolver(lib),
        {"/"+h.root_uuid+"/"+s.symbol_uuid,name,schematic_stable_uuid({name,"sheet",s.name})}).text);
    write(dir/(name+".kicad_sch"),emit_schematic(h.root,resolver(lib),{"",name,h.root_uuid}).text);
}
// Child-process fault injection tests transport/concurrency only. None of these
// responses supplies a successful netlist or a board connectivity oracle.
int process_probe(int argc,char** argv) {
    const char* state=std::getenv("SCHGEN_BOARD_PROCESS_PROBE");require(state!=nullptr,"process probe state");
    const fs::path dir=state;
    if(argc==8&&std::string(argv[2])=="erc") {
        require(std::string(argv[3])=="--severity-error"&&std::string(argv[4])=="--exit-code-violations"&&std::string(argv[5])=="-o","ERC argv");
        const fs::path output=argv[6],input=argv[7];write(dir/"erc.scratch",output.parent_path().string());
        if(input.filename()=="no-report")return 0;
        if(input.filename()=="signal"){::raise(SIGTERM);return 1;}
        std::cerr<<"ERC diagnostic";write(output,"ERC report (a volatile date Encoding UTF8)\nerror detail\n");return 5;
    }
    require(argc==9&&std::string(argv[2])=="export"&&std::string(argv[3])=="netlist"&&std::string(argv[4])=="--format"&&std::string(argv[5])=="kicadxml"&&std::string(argv[6])=="-o","netlist argv");
    const fs::path output=argv[7],input=argv[8];const auto name=input.stem().string();
    write(dir/(name+".scratch"),output.parent_path().string());write(dir/(name+".start"),"started");
    const auto mode=read(dir/"mode");
    if(mode=="parallel"&&name=="alpha.uniqcheck") {
        const auto limit=std::chrono::steady_clock::now()+std::chrono::seconds(3);
        while(!fs::exists(dir/"beta.uniqcheck.finish")&&std::chrono::steady_clock::now()<limit)std::this_thread::sleep_for(std::chrono::milliseconds(5));
        require(fs::exists(dir/"beta.uniqcheck.finish"),"second worker did not execute concurrently");
        write(dir/"parallel.confirmed","yes");
    }
    if(mode=="serial"&&name=="beta.uniqcheck")require(fs::exists(dir/"alpha.uniqcheck.finish"),"worker bound/order violated");
    write(dir/(name+".finish"),"finished");
    std::cerr<<(name=="alpha.uniqcheck"?"alpha-first":"beta-second");return 7;
}
struct ProbeEnvironment {
    std::optional<std::string> previous;
    explicit ProbeEnvironment(const fs::path& dir){if(const auto* p=std::getenv("SCHGEN_BOARD_PROCESS_PROBE"))previous=p;require(::setenv("SCHGEN_BOARD_PROCESS_PROBE",dir.c_str(),1)==0,"setenv");}
    ~ProbeEnvironment(){if(previous)::setenv("SCHGEN_BOARD_PROCESS_PROBE",previous->c_str(),1);else ::unsetenv("SCHGEN_BOARD_PROCESS_PROBE");}
};
void contracts(const fs::path& fixtures,const std::string& cli,const fs::path& self) {
    const auto data=parse_json_file((fixtures/"cases.json").string());std::vector<SymbolDef> symbols;
    for(const auto& s:field(data,"symbols").array_value)symbols.push_back(parse_symbol(str(s,"lib_id"),sexpr_loads(str(s,"raw"))));
    SymbolLibrary empty(std::vector<fs::path>{});auto lib=empty.with_definitions(symbols);
    for(const auto& r:field(data,"renames").array_value){
        if(field(r,"error").kind==JsonKind::Null)equal_text(board_renamed_ref(str(r,"ref"),num(r,"band"),str(r,"sheet")),str(r,"value"),"rename");
        else {bool failed=false;try{board_renamed_ref(str(r,"ref"),num(r,"band"),str(r,"sheet"));}catch(const BoardSchematicError& e){failed=true;equal_text(e.what(),str(r,"error"),"rename error");}require(failed,"rename must reject");}
    }
    rejects([]{board_renamed_ref("R1",-1);},"invalid board reference band");
    rejects([]{board_renamed_ref("R1",std::numeric_limits<std::int64_t>::max());},"invalid board reference band");
    for(const auto& r:field(data,"projects").array_value)equal_text(board_project_json(field(r,"existing"),str(r,"root_name")),str(r,"expected"),"project merge");
    equal_text(strip_board_report_timestamp("ERC report (2026-09-18 Encoding UTF8)\nbody\n"),"ERC report (Encoding UTF8)\nbody\n","timestamp");
    equal_text(strip_board_report_timestamp("untimestamped"),"untimestamped\n","no LF timestamp");
    equal_text(strip_board_report_timestamp("x (a Encoding B) y (c Encoding D)\n"),"x (Encoding B) y (Encoding D)\n","multiple timestamps");
    for(const auto& row:field(data,"hierarchies").array_value){
        const auto inputs=hierarchy_inputs(row);const auto h=make_board_hierarchy(inputs,lib,str(row,"root_name"),str(row,"subdir"));
        equal_text(h.root_uuid,str(row,"root_uuid"),"root UUID");equal_text(h.root.paper,str(row,"paper"),"root paper");
        equal_text(emit_schematic(h.root,resolver(lib),{"",str(row,"root_name"),h.root_uuid}).text,read(fixtures/str(row,"golden")),str(row,"name")+" root golden");
        require(h.sheets.size()==inputs.size(),"no omitted sheets");
        const auto& expected=field(row,"children").array_value;
        for(std::size_t i=0;i<h.sheets.size();++i){const auto& s=h.sheets[i];ir_renaming(inputs[i].design,s.design,inputs[i].reference_band);
            equal_text(s.symbol_uuid,str(expected[i],"uuid"),"sheet-symbol UUID");
            equal_text(emit_schematic(s.design,resolver(lib),{"/"+h.root_uuid+"/"+s.symbol_uuid,str(row,"root_name"),schematic_stable_uuid({str(row,"root_name"),"sheet",s.name})}).text,
                read(fixtures/str(expected[i],"golden")),str(row,"name")+" child "+s.name);
        }
        auto reversed=inputs;std::reverse(reversed.begin(),reversed.end());const auto reordered=make_board_hierarchy(reversed,lib,str(row,"root_name"),str(row,"subdir"));
        for(const auto& child:reordered.sheets){const auto old=std::find_if(h.sheets.begin(),h.sheets.end(),[&](const auto& x){return x.name==child.name;});equal_text(child.symbol_uuid,old->symbol_uuid,"UUID stable under page reorder");}
    }
    const auto& first=field(data,"hierarchies").array_value.front();const auto rc=hierarchy_inputs(first);
    rejects([&]{make_board_hierarchy({},lib);},"empty board");
    rejects([&]{make_board_hierarchy(rc,lib,"../escape");},"invalid board root");
    rejects([&]{make_board_hierarchy(rc,lib,"board","../escape");},"subdirectory");
    auto duplicate=rc;duplicate[1].reference_band=duplicate[0].reference_band;rejects([&]{make_board_hierarchy(duplicate,lib);},"duplicate board reference band");
    duplicate=rc;duplicate[1].design.circuit.name=duplicate[0].design.circuit.name;rejects([&]{make_board_hierarchy(duplicate,lib);},"duplicate board sheet");
    rejects([&]{make_board_hierarchy(rc,lib,"alpha");},"collides with child");
    auto too_tall=rc;for(int i=0;i<300;++i)too_tall[0].design.circuit.nets.push_back({"N"+std::to_string(i),"port",{}});
    rejects([&]{make_board_hierarchy(too_tall,lib);},"exceeds A1");
    auto collision=rc[0].design;collision.circuit.parts.push_back(collision.circuit.parts.front());collision.circuit.parts.back().ref="R01";
    rejects([&]{uniquify_board_design(collision,1);},"colliding reference");
    auto unknown=rc[0].design;unknown.parts.front().ref="U999";rejects([&]{uniquify_board_design(unknown,1);},"unknown reference");
    for(const auto& row:field(data,"flags").array_value){
        auto ds=designs(field(row,"designs"));const auto expected=designs(field(row,"expected"));strip_duplicate_board_flags(ds,lib);
        for(std::size_t i=0;i<ds.size();++i)equal_text(emit_schematic(ds[i],resolver(lib)).text,emit_schematic(expected[i],resolver(lib)).text,"flag guard "+str(row,"name"));
    }
    for(const auto& row:field(data,"gates").array_value){
        const auto ps=placed(designs(field(row,"designs")));const auto* xml=object_field(row,"xml");
        const auto nets=xml?parse_netlist_xml(read(fixtures/xml->string_value)):netlist(field(row,"extracted"));
        const auto gate=check_board_netlist(ps,nets,lib);equal_text(gate.summary(),str(row,"report"),"ordered board gate "+str(row,"name"));require(gate.failures==num(row,"failures"),"gate failure count");
    }
    for(const std::string mode:{"parallel","serial"}) {
        Scratch state;ProbeEnvironment environment(state.path);write(state.path/"mode",mode);
        std::vector<BoardSheetInput> inputs;for(const auto& sheet:rc)inputs.push_back({sheet.design.circuit,sheet.reference_band,prepared(sheet.design,lib)});
        BoardSchematicOptions options;options.extraction.kicad_cli=self.string();options.netlist_workers=mode=="parallel"?2:1;
        rejects([&]{build_board_schematic(inputs,lib,state.path/"outputs",options);},"alpha-first");
        require(fs::exists(state.path/"alpha.uniqcheck.finish")&&fs::exists(state.path/"beta.uniqcheck.finish"),"all workers joined after failure");
        if(mode=="parallel")require(fs::exists(state.path/"parallel.confirmed"),"actual parallel children");
        const auto a=read(state.path/"alpha.uniqcheck.scratch"),b=read(state.path/"beta.uniqcheck.scratch");require(a!=b,"separate exporter scratch paths");
        require(!fs::exists(a)&&!fs::exists(b),"export scratch cleanup on error");
        const auto erc=run_kicad_erc(state.path/"violation",{self.string()});require(erc.exit_code==5,"ERC nonzero returned");
        equal_text(erc.stderr_text,"ERC diagnostic","ERC stderr captured");require(erc.report.find("error detail")!=std::string::npos,"ERC report retained");
        require(!fs::exists(read(state.path/"erc.scratch")),"ERC scratch cleanup");
        rejects([&]{run_kicad_erc(state.path/"no-report",{self.string()});},"success without a report");
        require(run_kicad_erc(state.path/"signal",{self.string()}).exit_code==-SIGTERM,"ERC signal returned");
    }
    if(cli.empty())return;
    Scratch scratch;const NetlistExtractOptions extraction{cli};
    // Actual KiCad exports of independently frozen real project subsets.
    for(const auto& row:field(data,"hierarchies").array_value){
        if(object_field(row,"synthetic"))continue;
        const auto inputs=hierarchy_inputs(row);const auto h=make_board_hierarchy(inputs,lib,str(row,"root_name"),str(row,"subdir"));
        const auto dir=scratch.path/str(row,"name");write_hierarchy(h,lib,dir,str(row,"root_name"),str(row,"subdir"));
        const auto root=dir/(str(row,"root_name")+".kicad_sch");
        const auto actual=check_board_netlist(h.sheets,extract_netlist(root,extraction),lib);
        const auto frozen=check_board_netlist(h.sheets,parse_netlist_xml(read(fixtures/str(row,"name")/"board.xml")),lib);
        equal_text(actual.summary(),frozen.summary(),"live frozen hierarchy "+str(row,"name"));
        for(const auto& s:h.sheets){auto verify=s.design;verify.standalone=true;const auto path=dir/(s.name+".verify.kicad_sch");write(path,emit_schematic(verify,resolver(lib)).text);
            require(check_netlist(verify.circuit,path,extraction).ok,"live uniquified sheet "+s.name);}
    }
    std::vector<BoardSheetInput> live;
    for(const auto& s:rc)live.push_back({s.design.circuit,s.reference_band,prepared(s.design,lib)});
    BoardSchematicOptions options;options.root_name="Frozen Board";options.sheet_subdir="sheets";options.extraction=extraction;
    const auto dir=scratch.path/"full build ; literal";
    auto result=build_board_schematic(live,lib,dir,options);require(result.ok(),"complete native board build");require(result.board.erc_ran,"root ERC must run");
    equal_text(read(result.root_path),read(fixtures/str(first,"golden")),"full build frozen root");
    require(fs::exists(dir/"board_gate.txt")&&fs::exists(dir/"board.erc.rpt"),"reports written");
    for(std::size_t i=0;i<rc.size();++i)equal_text(read(dir/"sheets"/(rc[i].design.circuit.name+".kicad_sch")),read(fixtures/str(field(first,"children").array_value[i],"golden")),"full child bytes");
    const auto stable=read(result.root_path);result=build_board_schematic(live,lib,dir,options);equal_text(read(result.root_path),stable,"deterministic rerun");
    auto automatic=live;for(auto& in:automatic)in.prepared.reset();require(build_board_schematic(automatic,lib,scratch.path/"automatic",options).ok(),"real native automatic placement");
    // All faults go through production build/export/check, not injected gate results.
    auto missing=live;missing[0].prepared->placement.parts.erase(missing[0].prepared->placement.parts.begin());
    const auto absent=build_board_schematic(missing,lib,scratch.path/"missing_part",options);require(!absent.ok()&&!absent.per_sheet[0].netlist.ok,"missing part cannot pass");
    auto nc=live;nc[0].prepared->placement.no_connects.push_back({101.6,77.47});
    const auto cheated=build_board_schematic(nc,lib,scratch.path/"nc_cheat",options);require(!cheated.ok()&&!cheated.per_sheet[0].netlist.nc_cheats.empty(),"NC cheat cannot pass");
    auto open=live;auto& segments=open[0].prepared->routed.segs;
    const auto cut=std::find_if(segments.begin(),segments.end(),[](const auto& w){return w.x0==101.6&&w.y0==91.44&&w.x1==101.6&&w.y1==97.79;});
    require(cut!=segments.end(),"frozen open target present");segments.erase(cut);
    require(!build_board_schematic(open,lib,scratch.path/"open",options).ok(),"open cannot pass");
    auto shorted=live;shorted[0].prepared->routed.segs.push_back({101.6,77.47,101.6,85.09,"SHORT"});
    require(!build_board_schematic(shorted,lib,scratch.path/"short",options).ok(),"short cannot pass");
    auto visual=live;visual[0].prepared->placement.boxes={{500,500,510,510,"body","one"},{501,501,511,511,"body","two"}};
    const auto overlapped=build_board_schematic(visual,lib,scratch.path/"visual",options);
    require(!overlapped.ok()&&overlapped.report.find("BOARD: visual gate FAIL on alpha:")!=std::string::npos,"visual failures reported");
    auto undriven=live;for(auto& net:undriven[0].circuit.nets)if(net.name=="MID")net.net_class="signal";
    auto input_symbol=lib.get("Device:R");input_symbol.pins[0].etype="input";input_symbol.pins[1].etype="input";
    auto input_cap=lib.get("Device:C");for(auto& pin:input_cap.pins)pin.etype="input";
    auto no_driver=lib.with_definitions({input_symbol,input_cap});
    const auto electrical=build_board_schematic(undriven,no_driver,scratch.path/"electrical",options);
    require(!electrical.ok()&&electrical.report.find("BOARD: electrical gate FAIL on alpha:")!=std::string::npos,"electrical failures reported");
    const auto h=make_board_hierarchy(rc,lib,options.root_name,options.sheet_subdir);auto broken=h;
    broken.root.sheets[0].pins[0].name="WRONG";const auto wrong=scratch.path/"wrong_root_port";write_hierarchy(broken,lib,wrong,options.root_name,options.sheet_subdir);
    require(!check_board_netlist(broken.sheets,wrong/(options.root_name+".kicad_sch"),wrong,lib,extraction).ok(),"wrong root port fails");
    auto erc=run_kicad_erc(result.root_path,extraction);require(!erc.report.empty(),"actual ERC report");
    rejects([&]{run_kicad_erc(result.root_path,{"/definitely/missing/kicad-cli"});},"cannot execute");
    rejects([&]{run_kicad_erc(result.root_path,{std::string("bad\0executable",14)});},"embedded null");
}
}  // namespace
int main(int argc,char** argv) {
    try{if(argc>1&&std::string(argv[1])=="sch")return process_probe(argc,argv);
        require(argc==2||(argc==4&&std::string(argv[2])=="--kicad"),"usage: board_schematic_contracts DATA_DIR [--kicad CLI]");
        contracts(argv[1],argc==4?argv[3]:"",fs::absolute(argv[0]));std::cout<<"board schematic contracts: "<<checks<<" checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<"board schematic contracts: "<<e.what()<<'\n';return 1;}
}
