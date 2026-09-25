#include "schgen/subsystem_authoring.hpp"
#include "schgen/symbols.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>

namespace {
using namespace schgen;
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
const JsonNode& at(const JsonNode& n,const std::string& k){auto p=object_field(n,k);require(p!=nullptr,"missing field "+k);return *p;}
void compare(const JsonNode& a,const JsonNode& b,const std::string& path) {
    require(a.kind==b.kind,path+": JSON kind mismatch");
    if(a.kind==JsonKind::Array) {
        require(a.array_value.size()==b.array_value.size(),path+": array size mismatch");
        for(std::size_t i=0;i<a.array_value.size();++i)compare(a.array_value[i],b.array_value[i],path+"["+std::to_string(i)+"]");
    } else if(a.kind==JsonKind::Object) {
        require(a.object_value.size()==b.object_value.size(),path+": object size mismatch");
        // Unlike semantic IR equality, also pin the Python insertion order.
        for(std::size_t i=0;i<a.object_value.size();++i) {
            require(a.object_value[i].first==b.object_value[i].first,path+": key order mismatch");
            compare(a.object_value[i].second,b.object_value[i].second,path+"."+a.object_value[i].first);
        }
    } else require(authoring_json_equal(a,b),path+": value mismatch ["+a.string_value+"] != ["+b.string_value+"]");
}
template<class F> void rejects(F&& f,const std::string& snippet) {
    try{f();}catch(const std::exception& e){require(std::string(e.what()).find(snippet)!=std::string::npos,std::string("wrong failure: ")+e.what());return;}
    throw std::runtime_error("accepted invalid authoring: "+snippet);
}
void helpers() {
    CircuitAuthor c("live");
    c.part("R1","Device:R","4k7"); c.part("R8","Device:R","1k");
    require(c.auto_ref("R")=="R2","auto_ref must not jump to highest explicit ref");
    require(c.auto_ref("R")=="R3","reserved refs must advance even before part insertion");
    c.net("+VIN",{"R1.1"});c.net("GND",{"R8.2"});c.port("SIG",{"R1.2","R8.1"});
    c.draws("+VIN",.05,"load");c.hint("SIG","trunk");c.waive("reset_waivers","SIG","  explicit reason  ");
    c.testpoint("SIG");c.mounting_hole("GND");
    c.decouple("R1.1",{"100n","10u"});c.pullup("R1.2","10k","+VIN");c.series("SIG","GND","220R");
    const auto before=authored_circuit_json(c.view());
    rejects([&]{c.bind({{"SIG","GND"}});},"collides");
    rejects([&]{c.bind({{"SIG","X"},{"GND","X"}});},"merge");
    require(authoring_json_equal(before,authored_circuit_json(c.view())),"failed bind changed source");
    c.bind({{"SIG","RENAMED"},{"+VIN","SUPPLY"}});
    auto done=c.finish();require(done.parts[2].value=="RENAMED","testpoint must rename");
    require(done.loads[0].rail=="SUPPLY"&&done.hints[0].net=="RENAMED"&&done.waivers[0].key=="RENAMED","metadata must rename");
    CircuitAuthor restored(done);require(restored.auto_ref("R")=="R9","restored counters must follow highest IR ref");
    rejects([&]{c.mounting_hole("SUPPLY");},"only GROUND");
    rejects([&]{c.nc({"R1.1"});},"carries a net");
    rejects([&]{c.net("OTHER",{"R1.1"});},"already on net");
    rejects([&]{c.part("R1","Device:R","22k");},"duplicate reference");
    rejects([&]{c.draws("GND",.1);},"not a POWER");
    rejects([&]{c.waive("tp_waivers","RENAMED","  ");},"reason");
    rejects([&]{c.expand_pin("R1");},"bad pin spec");
    CircuitAuthor p("pairs");p.part("U1","unknown:part","part");p.port("P",{"U1.1"});p.port("N",{"U1.2"});
    AuthoringPort t;t.kind="usb_hs_pair";t.pair_with="N";t.speed_hz=100;t.level_v=1.8;t.expect="peer";p.port_type("P",t);
    p.bind({{"P","N"},{"N","P"}});auto pair=p.finish();
    require(pair.port_types[0].pair_with=="P"&&pair.port_types[0].impedance==90,"pair rename/default impedance");
    require(!pair.port_types[1].has_speed_hz&&!pair.port_types[1].has_level_v,"reciprocal metadata must be asymmetric");
    AuthoringContext cat;cat.part=[](const auto& safe){CatalogPart rec;rec.safe_name=safe;rec.mpn="STACK";rec.lib_id="Part:STACK";rec.prefix="U";rec.pins={{"1","VDD","power_in"},{"2","GND","power_in"},{"3","GND","power_in"}};return rec;};
    CircuitAuthor stack("stack","",cat);stack.use_part("STACK");stack.net("GND",{"U1.GND"});
    require(stack.view().nets[0].pins.size()==2,"stacked symbolic pins lost");
    rejects([&]{stack.decouple("U1.GND",{"1u"});},"stacked pins");
    rejects([&]{stack.net("GND",{"U1.99"});},"no pin number or name");
    stack.net("+VDD",{"U1.1"});stack.validate({{"U1",{"1","2","3"}}});
    rejects([&]{stack.validate({{"U1",{"1","2","3","4"}}});},"U1.4: UNASSIGNED");
    auto page=c.subset({"R1","TP1"},7);
    require(page.name=="live.7"&&page.parts[0].ref=="R1"&&page.parts[1].ref=="TP1","subset sorted part order");
    require(page.loads.size()==1&&page.waivers.size()==1&&page.hints.size()==1,"subset metadata retained");
    CircuitAuthor private_net("private");private_net.part("R1","Device:R","1k");private_net.part("R2","Device:R","1k");
    private_net.net("MID",{"R1.1","R2.1"});rejects([&]{private_net.subset({"R1"},1);},"would be CUT");
    require(!private_net.port_type_of("MISSING").has_expect&&private_net.port_type_of("MISSING").kind=="single","missing port type default");
    CircuitAuthor underscores("underscores");underscores.part("R_A17","Device:R","1k");
    CircuitAuthor reload(underscores.finish());require(reload.auto_ref("R_A")=="R_A18","underscore reference counter restore");
    JsonNode bad;bad.kind=JsonKind::Object;JsonNode items;items.kind=JsonKind::Array;
    bad.object_value.emplace_back("bind",items);rejects([&]{SubsystemMeta m(bad);},"must be a dict");
    bad.object_value[0].first="bus";rejects([&]{SubsystemMeta m(bad);},"unknown subsystem meta key");
    rejects([&]{SubsystemMeta m(items);},"meta must be a dict");
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: subsystem_authoring_contracts REPOSITORY");
        const std::filesystem::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"cannot open part catalog");
        SymbolLibrary symbols(root);AuthoringContext context;
        context.pins=[&](const auto& lib)->std::optional<std::set<std::string>>{try{return symbols.pin_numbers(lib);}catch(const SymbolError&){return std::nullopt;}};
        require(subsystem_definitions().size()==17,"library coverage");
        std::size_t cases=0;
        for(const auto& def:subsystem_definitions()) {
            const auto fixture=parse_json_file((root/"native/tests/data/authoring"/(def.name+".json")).string());
            const auto& iface=at(fixture,"interface").array_value;require(iface.size()==def.interface.size(),def.name+": interface size");
            for(std::size_t i=0;i<iface.size();++i)require(iface[i].string_value==def.interface[i],def.name+": interface declaration");
            for(const auto& row:at(fixture,"cases").array_value) {
                const SubsystemMeta meta(at(row,"meta"));
                if(auto expected=object_field(row,"error")) {
                    bool failed=false;try{(void)author_subsystem(def.name,meta,context);}catch(const CircuitAuthoringError& e){failed=true;require(e.what()==expected->string_value,def.name+": failure text differs: "+e.what());}
                    require(failed,def.name+": expected original Python error");
                } else compare(authored_circuit_json(author_subsystem(def.name,meta,context)),at(row,"circuit"),def.name+".case"+std::to_string(cases));
                ++cases;
            }
        }
        helpers();
        // Runtime part catalog edits affect builders: no compiled default IR.
        auto changed=context;changed.part=[](const auto& mpn){auto p=lookup_part_catalog(mpn);p.lcsc="CUSTOM_RUNTIME_LCSC";return p;};
        require(author_subsystem("usb_pd",SubsystemMeta{},changed).parts[0].fields[0].value=="CUSTOM_RUNTIME_LCSC","builder froze live catalog fields");
        rejects([]{author_subsystem("missing");},"unknown subsystem");
        close_part_catalog();
        std::cout<<"PASS: "<<cases<<" independent Python authoring cases, 17 interfaces, live catalog and helper mutation contracts\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
