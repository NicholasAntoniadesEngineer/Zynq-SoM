#include "schgen/example_devkit.hpp"
#include "schgen/board_pipeline.hpp"
#include "schgen/design_rules.hpp"
#include "schgen/part_checks.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/validation.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <set>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs=std::filesystem;
std::size_t checks=0;
std::set<std::string> families;
void require(bool value,const std::string& why){++checks;if(!value)throw std::runtime_error(why);}
const JsonNode& at(const JsonNode& value,const std::string& key){const auto* p=object_field(value,key);if(!p)throw std::runtime_error("missing reference field "+key);return *p;}
std::set<std::string> strings(const JsonNode& value){std::set<std::string> out;for(const auto& s:value.array_value)out.insert(s.string_value);return out;}
void exact(const JsonNode& a,const JsonNode& b,const std::string& label){
    require(a.kind==b.kind,label+": kind");
    if(a.kind==JsonKind::Object){
        require(a.object_value.size()==b.object_value.size(),label+": fields");
        for(std::size_t i=0;i<a.object_value.size();++i){require(a.object_value[i].first==b.object_value[i].first,label+": insertion order");exact(a.object_value[i].second,b.object_value[i].second,label+"."+a.object_value[i].first);}
    }else if(a.kind==JsonKind::Array){
        require(a.array_value.size()==b.array_value.size(),label+": length");
        for(std::size_t i=0;i<a.array_value.size();++i)exact(a.array_value[i],b.array_value[i],label+"["+std::to_string(i)+"]");
    }else require(authoring_json_equal(a,b),label+": value");
}
template<class F>void rejects(F fn,const std::string& snippet){
    bool rejected=false;
    try{fn();}catch(const std::exception& e){rejected=true;require(std::string(e.what()).find(snippet)!=std::string::npos,"wrong failure: "+std::string(e.what()));}
    require(rejected,"expected rejection: "+snippet);
}
const CircuitNetIr& net(const CircuitSheetIr& c,const std::string& name){
    const auto it=std::find_if(c.nets.begin(),c.nets.end(),[&](const auto& n){return n.name==name;});
    require(it!=c.nets.end(),c.name+": missing net "+name);return *it;
}
std::set<std::string> external(const CircuitSheetIr& c){std::set<std::string> out;for(const auto& n:c.nets)if(n.net_class!="signal")out.insert(n.name);return out;}
std::vector<std::string> refs(const CircuitSheetIr& c){std::vector<std::string> out;for(const auto& p:c.parts)out.push_back(p.ref);return out;}
std::set<std::string> nc(const CircuitSheetIr& c){std::set<std::string> out;for(const auto& p:c.nc)out.insert(p.ref+"."+p.pin);return out;}
AuthoringStrings bindings(const JsonNode& meta){AuthoringStrings out;for(const auto& [key,val]:at(meta,"bind").object_value)out.emplace_back(key,val.string_value);return out;}
std::string mapped(const AuthoringStrings& bindings,const std::string& name){const auto it=std::find_if(bindings.begin(),bindings.end(),[&](const auto& kv){return kv.first==name;});return it==bindings.end()?name:it->second;}
struct Scratch {
    fs::path path;
    Scratch(){auto value=(fs::canonical(fs::temp_directory_path())/"schgen-example-devkit-XXXXXX").string();require(::mkdtemp(value.data())!=nullptr,"private directory");path=value;}
    ~Scratch(){std::error_code ignored;fs::remove_all(path,ignored);}
};
std::string read(const fs::path& path){std::ifstream file(path,std::ios::binary);require(bool(file),"read "+path.string());return {std::istreambuf_iterator<char>(file),{}};}

void authoring(const fs::path& root,SymbolLibrary& library,const AuthoringContext& context){
    const auto& defs=example_devkit_definitions();const auto sheets=author_example_devkit(context);
    families.insert("all_project_subsystems_are_covered");
    const std::vector<std::string> names{"usb_pd","usbc_otg","microsd","uart_bridge"};
    require(defs.size()==4 && sheets.size()==4,"four-sheet example distinct from project");
    const std::set<std::string> carrier_names{"+3V3_SC","+3V3","+3V3_SD","+5V_USB","+1V8","+VBUS_IN","USB_D+","USB_D-", "SC_INT_N","VBUS_OUT_EN","USBOTG_FLT_N","SD_CARD_DETECT","USB_UART_VBUS","USB_UART_DP","USB_UART_DM"};
    const auto resolve=[&](const std::string& id)->const SymbolDef&{return library.get(id);};
    for(std::size_t i=0;i<defs.size();++i){
        const auto& def=defs[i];const auto& c=sheets[i];
        require(def.name==names[i] && c.name==names[i],"original PROJECT ordering");
        const auto reference=parse_json_file((root/"native/tests/data/example_devkit"/(def.name+".json")).string());
        exact(def.metadata,at(reference,"meta"),def.name+": four metadata records");
        exact(authored_circuit_json(c),at(reference,"bound"),def.name+": original wrapper IR");
        const auto base=author_subsystem(def.name,SubsystemMeta{},context);
        exact(authored_circuit_json(base),at(reference,"base"),def.name+": unbound library IR");
        const auto& variant=at(reference,"variant");
        exact(authored_circuit_json(author_example_devkit_subsystem(def.name,context,at(variant,"meta"))),at(variant,"circuit"),def.name+": live alternate metadata");
        const auto mapped_all=author_example_devkit(context,{{def.name,at(variant,"meta")}});
        exact(authored_circuit_json(mapped_all[i]),at(variant,"circuit"),def.name+": project override");
        for(std::size_t j=0;j<sheets.size();++j)if(j!=i)require(authoring_json_equal(authored_circuit_json(mapped_all[j]),authored_circuit_json(sheets[j])),"override did not alter sibling");
        families.insert("subsystem_builds_under_devkit_bind");require(!c.parts.empty(),def.name+": actual parts");
        const auto bind=bindings(def.metadata);std::set<std::string> expected;
        for(const auto& [abstract,real]:bind){(void)abstract;expected.insert(real);}
        families.insert("devkit_names_present_no_abstract_or_carrier_leak");require(external(c)==expected,def.name+": complete bound interface");
        for(const auto& actual:external(c)){
            require(!carrier_names.count(actual),def.name+": carrier name leaked");
            for(const auto* prefix:{"STM32","SDIO_","ZYNQ_PS"})require(actual.rfind(prefix,0)!=0,def.name+": carrier prefix leaked");
            if(strings(at(reference,"interface")).count(actual))require(mapped(bind,actual)==actual,"non-identity abstract name leaked");
        }
        families.insert("rail_and_port_net_classes_preserved");
        for(const auto& rail:strings(at(reference,"rails")))require(net(c,mapped(bind,rail)).net_class==(rail=="GND"||rail=="CHASSIS_GND"?"ground":"power"),def.name+": rail class");
        for(const auto& port:strings(at(reference,"ports")))require(net(c,mapped(bind,port)).net_class=="port",def.name+": port class");
        families.insert("bind_rejects_unknown_name");CircuitAuthor unknown(base,context);
        rejects([&]{unknown.bind({{"NOT_A_REAL_PORT","+3V3_MINI"}});},"not a net");
        families.insert("bind_rejects_signal_net");CircuitAuthor signal("t","t",context);
        signal.part("R1","Device:R","1k");signal.part("R2","Device:R","1k");signal.net("PRIVATE_MID",{"R1.2","R2.1"});
        require(signal.view().nets[0].net_class=="signal","private signal classification");rejects([&]{signal.bind({{"PRIVATE_MID","SOMETHING"}});},"SIGNAL");
        families.insert("bind_rejects_collision");CircuitAuthor collision(base,context);const auto& ports=at(reference,"ports").array_value;
        const auto before=authored_circuit_json(collision.view());
        rejects([&]{collision.bind({{ports[0].string_value,"SHARED_BAD"},{ports[1].string_value,"SHARED_BAD"}});},"merge");
        require(authoring_json_equal(before,authored_circuit_json(collision.view())),"failed bind is atomic");
        families.insert("bound_subsystem_passes_local_design_rules");
        const auto dr=check_design_rules({c},resolve);require(dr.decap.empty() && dr.ep.empty() && dr.strap.empty(),def.name+": local design rules");
        families.insert("bound_subsystem_passes_part_rules");
        const auto parts=analyze_part_rules(std::vector<ProjectCircuit>{{c.name,{},c}});require(parts.ok(),def.name+": part ratings");
        families.insert("bound_subsystem_model_is_complete");validate_circuit(c,library);require(check_circuit_electrical(c,library).ok(),def.name+": electrical completeness");
        families.insert("bind_is_byte_stable_rename");require(refs(c)==refs(base) && nc(c)==nc(base),def.name+": part/NC rename stability");
        require(c.nets.size()==base.nets.size(),"net count stability");
        for(std::size_t n=0;n<c.nets.size();++n)require(c.nets[n].name==mapped(bind,base.nets[n].name),"net insertion order stable");
        families.insert("draw_budget_follows_renamed_rail");
        for(const auto& load:c.loads)require(expected.count(load.rail),def.name+": budget uses bound rail");
        for(const auto& rail:strings(at(reference,"rails")))if(mapped(bind,rail)!=rail)
            for(const auto& load:c.loads)require(load.rail!=rail,def.name+": abstract load rail leaked");
    }
    families.insert("meta_rejects_unknown_top_level_key");
    rejects([&]{author_example_devkit_subsystem("usb_pd",context,parse_json_text("{\"binds\":{}}"));},"unknown subsystem meta key");
    rejects([&]{author_example_devkit_subsystem("power",context);},"unknown four-sheet");
    rejects([&]{author_example_devkit(context,{{"power",parse_json_text("{}")}});},"unknown four-sheet");
    families.insert("project_aggregate_exercises_decap_rule");const auto aggregate=check_design_rules(sheets,resolve);
    require(aggregate.decap.empty() && aggregate.ep.empty() && aggregate.strap.empty(),"aggregate local rules");
    const auto decap=std::find_if(aggregate.checked.begin(),aggregate.checked.end(),[](const auto& x){return x.first=="decap";});
    require(decap!=aggregate.checked.end() && decap->second>=1,"aggregate actually exercised decap rule");
    families.insert("shared_logic_rail_and_gnd_are_one_net_across_subsystems");
    std::map<std::string,std::set<std::string>> owners,classes;
    for(const auto& c:sheets)for(const auto& n:c.nets)if(n.net_class!="signal"){owners[n.name].insert(c.name);classes[n.name].insert(n.net_class);}
    for(const auto& rail:example_devkit_shared_rails())require(owners[rail].size()>=2 && classes[rail].size()==1,"shared rail contract");
    require(owners["+3V3_MINI"]==std::set<std::string>(names.begin(),names.end()),"all four use shared logic rail");
    require(classes["+3V3_MINI"]==std::set<std::string>{"power"} && classes["GND"]==std::set<std::string>{"ground"},"shared rail classes");
    families.insert("no_devkit_net_collides_across_subsystems_by_accident");std::set<std::string> shared;
    for(const auto& [name,who]:owners)if(who.size()>1)shared.insert(name);
    require(shared==std::set<std::string>{"+3V3_MINI","GND"},"only intentional rails are shared");
    families.insert("same_library_binds_to_carrier_or_devkit_from_one_source");
    const auto carrier_meta=parse_json_text(R"({"bind":{"+VDD_LOGIC":"+3V3_SC","+VBUS_SENSE":"+VBUS_IN","GND":"GND","CC1":"STM32_USB_CC1","CC2":"STM32_USB_CC2","I2C_SDA":"STM32_I2C2_SDA","I2C_SCL":"STM32_I2C2_SCL","INT_N":"SC_INT_N"}})");
    const auto carrier=author_subsystem("usb_pd",SubsystemMeta(carrier_meta),context);const auto dev=author_example_devkit_subsystem("usb_pd",context);
    const auto ca=external(carrier),da=external(dev);std::set<std::string> common;
    std::set_intersection(ca.begin(),ca.end(),da.begin(),da.end(),std::inserter(common,common.end()));
    require(common==std::set<std::string>{"GND"} && refs(carrier)==refs(dev),"one source, two separate bindings");
    families.insert("devkit_uart_crossover_lives_in_the_bind_not_the_library");const auto uart_bind=bindings(defs[3].metadata);
    for(const auto& [from,to]:AuthoringStrings{{"UART_TXD","FPGA_UART0_RXD"},{"UART_RXD","FPGA_UART0_TXD"},{"UART_RTS_N","FPGA_UART0_CTS_N"},{"UART_CTS_N","FPGA_UART0_RTS_N"}}){
        require(mapped(uart_bind,from)==to && external(sheets[3]).count(to),"UART null-modem binding");}
    auto live=context;live.part=[](const std::string& mpn){auto p=lookup_part_catalog(mpn);p.lcsc="LIVE_EXAMPLE_PROVIDER";return p;};
    const auto changed=author_example_devkit(live);std::size_t altered=0;
    for(const auto& c:changed)for(const auto& p:c.parts)for(const auto& f:p.fields)if(f.key=="LCSC" && f.value=="LIVE_EXAMPLE_PROVIDER")++altered;
    require(altered>=4,"live catalog edits affect actual authored components, not a frozen circuit");

    families.insert("devkit_subsystems_compose_no_shorts_or_opens");
    for(const auto& c:sheets){
        auto page=place_and_route_schematic(c,library);const auto cc=check_board_sheet_cc(c,page.placement,page.routed,resolve);
        require(cc.ok(),c.name+": live CC failed: "+cc.summary());require(cc.n_declared==c.nets.size() && cc.n_components>0,"actual CC geometry census");
        auto open=page.routed;open.segs.clear();
        require(!check_board_sheet_cc(c,page.placement,open,resolve).ok(),c.name+": erased real wires cannot pass CC");
        auto missing=page.placement;missing.parts.erase(missing.parts.begin());
        require(!check_board_sheet_cc(c,missing,page.routed,resolve).ok(),c.name+": missing placed part cannot pass CC");
        const auto tip=[&](const CircuitPinRefIr& pin){
            const auto part=std::find_if(page.placement.parts.begin(),page.placement.parts.end(),[&](const auto& p){return p.ref==pin.ref;});
            require(part!=page.placement.parts.end(),"short mutation placed part");
            const auto& symbol=library.get(part->lib_id);
            const auto terminal=std::find_if(symbol.pins.begin(),symbol.pins.end(),[&](const auto& p){return p.number==pin.pin;});
            require(terminal!=symbol.pins.end(),"short mutation real library pin");
            return pin_page_position(*terminal,part->x,part->y,part->rotation);
        };
        std::vector<CircuitPinRefIr> selected;
        for(const auto& n:c.nets)if(!n.pins.empty()){selected.push_back(n.pins.front());if(selected.size()==2)break;}
        require(selected.size()==2,"two real nets for short mutation");
        const auto a=tip(selected[0]),b=tip(selected[1]);auto shorted=page.routed;
        if(a.first!=b.first)shorted.segs.push_back({a.first,a.second,b.first,a.second,"deliberately wrong annotation"});
        if(a.second!=b.second)shorted.segs.push_back({b.first,a.second,b.first,b.second,"deliberately wrong annotation"});
        require(!check_board_sheet_cc(c,page.placement,shorted,resolve).shorts.empty(),c.name+": actual short must fail regardless of segment net annotation");
    }
    require(families.size()==19,"all original 19 test families executed");
}

void live_build(const std::vector<CircuitSheetIr>& sheets,SymbolLibrary& library,const fs::path& output){
    ExampleDevkitOptions options;options.no_render=true;options.netlist_workers=2;
    const auto result=build_example_devkit(sheets,library,output,options);
    require(result.ok(),"actual four-sheet standalone and hierarchy build failed:\n"+result.report);
    require(result.hierarchy.board.erc_ran,"root ERC really ran");
    for(std::size_t i=0;i<sheets.size();++i){
        const auto& standalone=result.standalone[i];
        require(standalone.electrical_ok && standalone.cc_ok && standalone.netlist_ok && standalone.erc_ok && standalone.visual_ok,"standalone mandatory gates");
        require(!standalone.rendered,"no-render respected");
        const auto& sheet=result.hierarchy.per_sheet[i];
        require(sheet.name==sheets[i].name && sheet.ok(),"uniquified child gates");
        const auto text=read(output/"schematic"/(sheets[i].name+".kicad_sch"));
        require(text.find(board_renamed_ref(sheets[i].parts[0].ref,static_cast<std::int64_t>(i+1)))!=text.npos,"positional reference band emitted");
    }
    const auto root_text=read(output/"devkit_mini.kicad_sch");
    for(const auto& c:sheets)require(root_text.find("schematic/"+c.name+".kicad_sch")!=root_text.npos,"root references live child");
    require(fs::is_regular_file(output/"devkit_mini.kicad_pro"),"real project publication");
    require(!fs::exists(output/"renders"),"no-render emits no PNGs");
    // Run real extraction on a corrupted emitted child, not a fabricated XML
    // fixture. A geometry edit must be caught even though authored IR is unchanged.
    auto corrupted=read(output/"schematic/usb_pd.kicad_sch");
    const auto pos=corrupted.find("MINI_I2C0_SDA");require(pos!=corrupted.npos,"mutation target exists");
    for(std::size_t at=0;(at=corrupted.find("MINI_I2C0_SDA",at))!=corrupted.npos;at+=22)corrupted.replace(at,13,"BROKEN_EXTERNAL_SIGNAL");
    publish_text(output/"schematic/usb_pd.kicad_sch",corrupted);
    auto renamed=sheets[0];
    for(auto& p:renamed.parts)p.ref=board_renamed_ref(p.ref,1);
    for(auto& n:renamed.nets)for(auto& p:n.pins)p.ref=board_renamed_ref(p.ref,1);
    for(auto& p:renamed.nc)p.ref=board_renamed_ref(p.ref,1);
    const auto mutant=check_netlist(renamed,output/"schematic/usb_pd.kicad_sch",options.extraction);
    require(!mutant.ok,"actual emitted label mutation cannot pass netlist gate");
}
}

int main(int argc,char** argv){
    try{
        require(argc==2 || argc==3,"usage: example_devkit_contracts REPOSITORY [--live]");
        if(argc==3)require(std::string(argv[2])=="--live","only --live enables KiCad checks");
        const fs::path root=fs::absolute(argv[1]);
        require(open_part_catalog((root/"native/catalog.bin").string()),"open existing catalog");
        SymbolLibrary library(root);auto context=make_authoring_context(root);
        authoring(root,library,context);
        require(!ExampleDevkitResult{}.ok(),"unexecuted example cannot pass");
        const auto sheets=author_example_devkit(context);Scratch scratch;
        rejects([&]{build_example_devkit({},library,scratch.path);},"exactly four");
        rejects([&]{build_example_devkit(sheets,library,{});},"explicit");
        auto reordered=sheets;std::swap(reordered[0],reordered[1]);
        rejects([&]{build_example_devkit(reordered,library,scratch.path);},"order");
        if(argc==3)live_build(sheets,library,scratch.path/"live");
        close_part_catalog();std::cout<<checks<<" example contracts passed; "<<families.size()<<" original test families"<<(argc==3?"; real KiCad hierarchy and mutation PASS":"")<<'\n';
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
