// Independent Python snapshots plus native boundary/mutation contracts. No
// interpreter, symbol library, catalog global state, or live project outputs.
#include "schgen/power_checks.hpp"
#include "schgen/thermal_checks.hpp"
#include "schgen/part_checks.hpp"

#include <cmath>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>

namespace {
using namespace schgen;
namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool cond,const std::string& why){++checks;if(!cond)throw std::runtime_error(why);}
const JsonNode& at(const JsonNode& n,const std::string& key){auto p=object_field(n,key);require(p!=nullptr,"missing fixture key "+key);return *p;}
JsonNode& mut(JsonNode& n,const std::string& key){for(auto& [k,v]:n.object_value)if(k==key)return v;throw std::runtime_error("missing mutation field "+key);}
std::string str(const JsonNode& n){require(n.kind==JsonKind::String,"expected fixture string");return n.string_value;}
double num(const JsonNode& n){require(n.kind==JsonKind::Number,"expected fixture number");return n.number_value;}
std::string precise(double v){std::ostringstream s;s<<std::setprecision(17)<<v;return s.str();}
void eq(const JsonNode& a,const JsonNode& b,const std::string& where) {
    require(a.kind==b.kind,where+": kind mismatch");
    switch(b.kind) {
        case JsonKind::Null:break;
        case JsonKind::Bool:require(a.bool_value==b.bool_value,where+": bool mismatch");break;
        case JsonKind::Number:require(a.number_value==b.number_value,where+": "+precise(a.number_value)+" != "+precise(b.number_value));break;
        case JsonKind::String:require(a.string_value==b.string_value,where+": string mismatch\ngot: "+a.string_value+"\nexpected: "+b.string_value);break;
        case JsonKind::Array:
            require(a.array_value.size()==b.array_value.size(),where+": array count mismatch");
            for(std::size_t i=0;i<b.array_value.size();++i)eq(a.array_value[i],b.array_value[i],where+"["+std::to_string(i)+"]");break;
        case JsonKind::Object:
            require(a.object_value.size()==b.object_value.size(),where+": object count mismatch");
            for(std::size_t i=0;i<b.object_value.size();++i){require(a.object_value[i].first==b.object_value[i].first,where+": field order mismatch");eq(a.object_value[i].second,b.object_value[i].second,where+"."+b.object_value[i].first);}break;
    }
}
void text_eq(const std::string& a,const std::string& b,const std::string& where) {
    if(a!=b){auto pos=std::mismatch(a.begin(),a.end(),b.begin(),b.end()).first-a.begin();require(false,where+": text mismatch byte "+std::to_string(pos)+"\ngot: "+a.substr(pos,150)+"\nexpected: "+b.substr(pos,150));}
    ++checks;
}
template<class F> void fails(F&& f,const std::string& why){bool failed=false;try{f();}catch(const std::exception&){failed=true;}require(failed,why);}
std::string read(const fs::path& path){std::ifstream in(path,std::ios::binary);require(bool(in),"read "+path.string());return {(std::istreambuf_iterator<char>(in)),{}};}
void write(const fs::path& path,const std::string& s){std::ofstream out(path,std::ios::binary);out<<s;require(bool(out),"write "+path.string());}

std::vector<ProjectCircuit> selected(const JsonNode& entry,const JsonNode& corpus) {
    std::vector<ProjectCircuit> sheets;
    if(auto idx=object_field(entry,"indices"))for(const auto& x:idx->array_value){const auto& rec=corpus.array_value.at(std::size_t(num(x)));auto path=fs::path(str(at(rec,"source")));auto c=decode_intermediate_circuit_ir(at(rec,"circuit"));sheets.push_back({path.parent_path().filename().string(),path,std::move(c)});}
    if(auto cs=object_field(entry,"circuits"))for(const auto& ir:cs->array_value){auto c=decode_intermediate_circuit_ir(ir);sheets.push_back({c.name,{},std::move(c)});}
    return sheets;
}
void family(const std::vector<ProjectCircuit>& sheets,const JsonNode& expected,const std::string& name,const ThermalCopper* copper=nullptr,const std::string& source="",const PowerPolicy& policy=default_power_policy()) {
    eq(power_result_json(detect_power_regulators(sheets,policy)),at(expected,"detection"),name+" detector");
    auto power=analyze_power(sheets,policy);auto pj=power_result_json(power);
    eq(pj,at(expected,"power"),name+" power");
    text_eq(power_report(power,policy),str(at(expected,"power_report")),name+" power report");
    if(auto svg=object_field(expected,"svg"))text_eq(power_svg(power,policy),str(*svg),name+" SVG");
    else fails([&]{(void)power_svg(power,policy);},name+" reachable cycle must not hang SVG");
    auto power_copy=power_result_from_json(pj);eq(power_result_json(power_copy),pj,name+" power inverse");
    auto thermal=analyze_thermal(sheets,power_copy,copper,source,default_thermal_policy(),policy);
    auto tj=thermal_result_json(thermal);eq(tj,at(expected,"thermal"),name+" thermal");
    text_eq(thermal_report(thermal),str(at(expected,"thermal_report")),name+" thermal report");
    eq(thermal_result_json(thermal_result_from_json(tj)),tj,name+" thermal inverse");
    auto parts=analyze_part_rules(sheets,power_copy,default_part_ratings(),default_part_rule_policy,policy);
    auto rj=part_result_json(parts);eq(rj,at(expected,"parts"),name+" parts");
    text_eq(part_rules_report(parts),str(at(expected,"parts_report")),name+" part report");
    eq(part_result_json(part_result_from_json(rj)),rj,name+" part inverse");
    require(power.ok()==power.errors.empty()&&thermal.ok()==thermal.errors.empty()&&parts.ok()==parts.findings.empty(),name+" verdict definitions");
}
void parsers(const JsonNode& fixtures) {
    for(const auto& rec:at(fixtures,"parsers").array_value) {
        auto value=str(at(rec,"value"));
        for(const auto& [name,fn]:std::vector<std::pair<std::string,std::function<std::optional<double>(const std::string&)>>>{{"si",parse_si_value},{"ohms",parse_resistor_ohms}}) {
            const auto& expected=at(rec,name);
            if(expected.kind==JsonKind::Object){auto parse=fn;fails([&]{parse(value);},"parser expected error "+value);continue;}
            auto v=fn(value);
            if(expected.kind==JsonKind::Null)require(!v,"parser expected null "+name+" "+value);
            else if(expected.kind==JsonKind::String){require(v.has_value(),"special value missing");auto s=str(expected);require(s=="nan"?std::isnan(*v):std::isinf(*v),"parser special "+value);}
            else require(v&&*v==num(expected),name+" "+value+" parsed differently");
        }
    }
    for(const auto& [s,v]:at(fixtures,"rail_volts").object_value) {auto got=rail_volts(s);if(v.kind==JsonKind::Null)require(!got,"rail unknown "+s);else require(got&&*got==num(v),"rail voltage "+s);}
    auto& expected=at(fixtures,"ratings");require(default_part_ratings().size()==expected.object_value.size(),"complete ratings table");
    for(std::size_t i=0;i<default_part_ratings().size();++i){auto& r=default_part_ratings()[i];auto& e=expected.object_value[i];require(r.first==e.first,"rating insertion order");eq(part_ratings_json(r.second),e.second,"rating "+r.first);auto parsed=part_ratings_from_json(e.second);require(bool(parsed),"rating decode");eq(part_ratings_json(*parsed),e.second,"rating inverse "+r.first);}
}
void mutation_contracts() {
    // A supplied power result is authoritative, even when no circuit regulator
    // could be detected. No hidden analyze/reload can satisfy these assertions.
    PowerCheckResult power;power.regs.push_back({77,"caller","U7","AP2112K","ldo","+5V","+1V8",.6,1,"edited",.5,9});
    ProjectCircuit sheet;sheet.name="caller";sheet.circuit.name="different circuit name";
    CircuitPartIr part;part.ref="U7";part.value="not a regulator";part.fields={{"LCSC","C176944"}};sheet.circuit.parts={part};
    auto restored=power_result_from_json(power_result_json(power));auto thermal=analyze_thermal({sheet},restored);
    require(thermal.devices.size()==1&&thermal.devices[0].i_out==.5&&thermal.devices[0].pd==(5.-1.8)*.5,"supplied result not recomputed");
    require(thermal.devices[0].sheet=="caller"&&thermal.devices[0].ref=="U7","explicit sheet identity");
    require(analyze_part_rules({sheet},restored).checked==1,"parts consume supplied regulator");
    restored.regs[0].vin="+VIN";require(analyze_part_rules({sheet},restored).findings.size()==1,"mutable input power vin honored");
    sheet.circuit.waivers={{"thermal_waivers","U7","first"},{"thermal_waivers","U7","last"},{"part_rule_waivers","U7","part reason"}};
    auto wt=analyze_thermal({sheet},restored);require(wt.errors.empty()&&wt.waived.size()==1&&wt.waived.front().second.second=="last","last waiver wins");
    require(analyze_part_rules({sheet},restored).findings.empty(),"part waiver honored");
    auto before=power_result_json(restored);(void)analyze_thermal({sheet},restored);eq(power_result_json(restored),before,"immutable supplied result");
    PowerPolicy custom=default_power_policy();custom.voltage_patterns={{"^X",0},{"^X",99}};require(rail_volts("XYZ",custom)==0,"explicit first-match voltage policy");
    PowerPolicy copied=default_power_policy();
    require(rail_volts("+5V_SOM\n",copied)==4.65,"cached copied policy terminal newline");
    copied.voltage_patterns[3].second=4.7;
    require(rail_volts("+5V_SOM",copied)==4.7,"cached expression does not freeze voltage value");
    std::swap(copied.voltage_patterns[3],copied.voltage_patterns[5]);
    require(rail_volts("+5V_SOM",copied)==5,"copied reordered expressions preserve first match");
    sheet.circuit.loads.push_back({"+5V",std::numeric_limits<double>::quiet_NaN(),"detection must not visit"});
    auto det=detect_power_regulators({sheet});require(det.regs.empty()&&det.errors.empty()&&det.draws.empty()&&det.rails.empty()&&det.findings.empty()&&det.notes.empty()&&det.source_load.empty(),"detector independent of loads/audits");
    ThermalSpec ts;ts.rth_ja=100;ts.tj_max=125;ts.eff=.85;ts.rds_on=.1;
    require(thermal_dissipation("ldo",1,2,.4,ts)==0,"no negative LDO drop");
    require(thermal_dissipation("unknown",5,3,.4,ts)==0,"unknown dissipation kind");
    require(thermal_dissipation("efuse",5,3,.4,ts)==.4*.4*.1,"switch grouping");
    ts.eff=0;fails([&]{thermal_dissipation("buck",5,3,.4,ts);},"zero efficiency explicit failure");
    PartRatings cap;cap.kind="tant";cap.dielectric="np0";require(capacitor_derating(cap)==1.5,"dielectric precedence");
    PartRulePolicy rp{2,1.25,1.75,2};require(capacitor_derating(cap,rp)==1.25,"explicit derating policy");
    cap.dielectric={};require(capacitor_derating(cap,rp)==1.75,"tantalum policy");cap.kind="film";require(capacitor_derating(cap,rp)==2,"film baseline MLCC margin");
    auto invalid=power_result_json(restored);mut(invalid,"regs").array_value.front().object_value.pop_back();fails([&]{power_result_from_json(invalid);},"missing nested input");
    invalid=power_result_json(restored);mut(mut(invalid,"regs").array_value[0],"n").number_value=.5;fails([&]{power_result_from_json(invalid);},"fractional regulator index");
    invalid=power_result_json(restored);mut(mut(invalid,"regs").array_value[0],"i_out").number_value=std::numeric_limits<double>::infinity();fails([&]{power_result_from_json(invalid);},"nonfinite transport");
    invalid=power_result_json(restored);invalid.object_value.push_back(invalid.object_value.front());fails([&]{power_result_from_json(invalid);},"duplicate key transport");
    auto tj=thermal_result_json(wt);mut(tj,"devices").array_value.front().object_value.push_back({"extra",JsonNode{}});fails([&]{thermal_result_from_json(tj);},"unknown thermal field");
    auto pj=part_result_json(PartCheckResult{});mut(pj,"checked").number_value=-1;fails([&]{part_result_from_json(pj);},"negative checked count");
    pj=part_result_json(PartCheckResult{});mut(pj,"checked").kind=JsonKind::Bool;fails([&]{part_result_from_json(pj);},"bool not numeric count");
    require(!part_ratings_from_json(JsonNode{}),"absent RATINGS");
    auto jr=part_ratings_json(cap);mut(jr,"v_max").kind=JsonKind::String;fails([&]{part_ratings_from_json(jr);},"invalid RATINGS type");
    require(!thermal_pour_evidence(nullptr,default_thermal_policy().pour_needs[0].second).first,"no scan fail closed");
    ThermalCopper copper;copper.vias={{3,4,"GND"},{3,4.000000001,"GND"},{0,0,"OTHER"}};
    require(copper.gnd_vias_within(0,0,5)==1,"inclusive Euclidean via radius");
    copper.zones.push_back({"edge","GND",{"F.Cu"},false,true,{0,0,2,2}});
    require(copper.pour_at(2,2,"F.Cu")&&!copper.pour_at(2.000000001,2,"F.Cu"),"inclusive zone bounding box");
    copper.zones[0].keepout=true;require(!copper.pour_at(1,1,"F.Cu"),"keepout not pour");
    ThermalPourNeed need{"test",1,3,{"F.Cu","B.Cu","In1.Cu"}};
    require(thermal_pour_layers(need,"B.Cu")==std::vector<std::string>({"B.Cu","F.Cu","In1.Cu"}),"layer swap preserves inner");
    fails([&]{scan_thermal_copper(sexpr_loads("(kicad_pcb (via (net 1)))"));},"malformed via explicit error");
}
}

int main(int argc,char** argv) {
    try {
        fs::path root=argc>1?argv[1]:".";auto dir=root/"native/tests/data/model_checks";
        auto corpus=parse_json_file((dir/"circuits.json").string());
        auto projects=parse_json_file((dir/"projects.json").string());
        auto cases=parse_json_file((dir/"cases.json").string());
        parsers(parse_json_file((dir/"policies.json").string()));
        for(const auto& entry:projects.array_value) {
            auto name=str(at(entry,"name"));auto sheets=selected(entry,corpus);auto copper=thermal_copper_from_json(at(entry,"copper"));
            eq(thermal_copper_json(copper),at(entry,"copper"),name+" copper inverse");
            family(sheets,at(entry,"expected_bare"),name+" bare");family(sheets,at(entry,"expected_copper"),name+" emitted",&copper,copper.path);
        }
        for(const auto& entry:cases.array_value) {
            auto name=str(at(entry,"name"));auto sheets=selected(entry,corpus);PowerPolicy policy=default_power_policy();
            for(const auto& [k,v]:at(entry,"deferred").object_value)policy.known_deferred.emplace_back(k,str(v));
            std::optional<ThermalCopper> copper;if(auto c=object_field(entry,"copper"))copper=thermal_copper_from_json(*c);
            family(sheets,at(entry,"expected"),name,copper?&*copper:nullptr,copper?"frozen.kicad_pcb":"",policy);
        }
        auto scans=parse_json_file((dir/"copper_cases.json").string());
        for(const auto& entry:scans.array_value) {
            auto name=str(at(entry,"name"));auto copper=scan_thermal_copper(sexpr_loads(str(at(entry,"sexpr"))),"frozen.kicad_pcb");
            eq(thermal_copper_json(copper),at(entry,"expected"),name+" scanner");
            for(const auto& [key,need]:default_thermal_policy().pour_needs){auto ev=thermal_pour_evidence(&copper,need);auto& expected=at(at(entry,"evidence"),key).array_value;require(ev.first==expected[0].bool_value,"evidence verdict "+name);text_eq(ev.second,str(expected[1]),"evidence "+name);}
        }
        mutation_contracts();
        // Publication only below an isolated temporary directory, never the
        // shared project outputs. Test exact LF and explicit-root path policy.
        fs::path temp;
        for(unsigned i=0;i<100;++i) {
            auto tick=std::chrono::high_resolution_clock::now().time_since_epoch().count();
            auto candidate=fs::temp_directory_path()/("schgen-model-contracts-"+std::to_string(tick)+"-"+std::to_string(i));
            if(fs::create_directory(candidate)){temp=std::move(candidate);break;}
        }
        require(!temp.empty(),"create isolated test directory");
        auto sheets=selected(projects.array_value.front(),corpus);const auto& expected=at(projects.array_value.front(),"expected_bare");
        auto power=run_power_checks(sheets,temp/"reports",temp/"docs");
        text_eq(read(temp/"reports/power_tree.txt"),str(at(expected,"power_report"))+"\n","published power");
        text_eq(read(temp/"docs/power_tree.svg"),str(at(expected,"svg")),"published svg");
        (void)run_thermal_checks(sheets,temp/"reports",&power,temp/"missing.kicad_pcb",temp);
        text_eq(read(temp/"reports/thermal.txt"),str(at(expected,"thermal_report"))+"\n","published missing-copper thermal");
        (void)run_part_checks(sheets,temp/"reports",&power);text_eq(read(temp/"reports/part_rules.txt"),str(at(expected,"parts_report"))+"\n","published parts");
        write(temp/"scan.kicad_pcb",str(at(scans.array_value.front(),"sexpr")));
        auto scanned=scan_thermal_copper(temp/"scan.kicad_pcb");scanned.path="frozen.kicad_pcb";eq(thermal_copper_json(scanned),at(scans.array_value.front(),"expected"),"file scanner");
        auto rt=run_thermal_checks(sheets,temp/"reports",&power,temp/"scan.kicad_pcb",temp);require(rt.copper_src=="scan.kicad_pcb","explicit repository root relative evidence");
        fs::remove_all(temp);
        std::cout<<"model_checks_contracts: "<<checks<<" checks passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<"model_checks_contracts FAILED after "<<checks<<": "<<e.what()<<"\n";return 1;}
}
