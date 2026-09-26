#include "schgen/firmware_docs.hpp"
#include "schgen/design_rules.hpp"
#include "schgen/process.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace {
using namespace schgen;
std::size_t assertions=0;
std::size_t generated_c_units=0, generated_c_maps=0;
void require(bool ok,const std::string& why) {++assertions;if(!ok)throw std::runtime_error(why);}
const JsonNode& field(const JsonNode& n,const std::string& k) {auto p=object_field(n,k);if(!p)throw std::runtime_error("missing fixture field "+k);return *p;}
std::string str(const JsonNode& n,const std::string& k) {return field(n,k).string_value;}
double num(const JsonNode& n,const std::string& k) {return field(n,k).number_value;}
std::optional<double> optnum(const JsonNode& n,const std::string& k) {const auto& v=field(n,k);return v.kind==JsonKind::Null?std::nullopt:std::optional<double>(v.number_value);}
std::optional<std::string> optstr(const JsonNode& n,const std::string& k) {const auto& v=field(n,k);return v.kind==JsonKind::Null?std::nullopt:std::optional<std::string>(v.string_value);}
std::vector<std::string> strings(const JsonNode& n) {std::vector<std::string> out;for(const auto& v:n.array_value)out.push_back(v.string_value);return out;}
ProjectStrings pairs(const JsonNode& n) {ProjectStrings out;for(const auto& [k,v]:n.object_value)out.emplace_back(k,v.string_value);return out;}
std::string read(const std::filesystem::path& p) {std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("cannot read "+p.string());return {std::istreambuf_iterator<char>(f),{}};}
void replace_once(std::string& text,const std::string& old,const std::string& replacement) {
    const auto pos=text.find(old);
    require(pos!=std::string::npos&&text.find(old,pos+old.size())==std::string::npos,
            "known legacy correction must match exactly once");
    text.replace(pos,old.size(),replacement);
}
std::string corrected_legacy_output(std::string expected,const std::string& artifact) {
    // The immutable Python baselines/mutants intentionally record two known
    // defects. Correct ONLY these three complete literal spans in EXPECTED
    // output, after frozen mutant byte edits have been applied. Never normalize
    // actual output or replace whole artifacts with freshly generated text.
    if(artifact=="BRINGUP.md")replace_once(expected,
        "   `0x52` **RTC** (`board_services.U2` RV-3028-C7), `BT1` CR1220 backup. **Keep\n"
        "   the trickle charger OFF** — `BT1` is a PRIMARY cell (see the firmware contract).\n",
        "   `0x52` **RTC** (`board_services.U2` RV-3028-C7), `BT1` rechargeable ML1220 backup.\n"
        "   **Enable the RV-3028 trickle charger** (TCE + ~3k series resistance) so the\n"
        "   cell tops up whenever powered. Do **not** fit a primary CR1220 or a LIR Li-ion\n"
        "   cell (see the firmware contract).\n");
    else if(artifact=="sc_tables.c")replace_once(expected,
        "    { \"FMC mezzanine ID EEPROM\", ZC_I2C_ADDR_FMC_EEPROM },\n", "");
    else if(artifact=="sc_tables.h")replace_once(expected,
        "#define SC_I2C_DEV_COUNT 7\n", "#define SC_I2C_DEV_COUNT 6\n");
    return expected;
}
void exact(const std::string& actual,const std::filesystem::path& expected,const std::filesystem::path& scratch) {
    const auto wanted=corrected_legacy_output(read(expected),expected.filename().string());
    std::filesystem::create_directories(scratch.parent_path());std::ofstream f(scratch,std::ios::binary);f<<actual;f.close();
    if(actual!=wanted) {
        const auto pos=std::mismatch(actual.begin(),actual.end(),wanted.begin(),wanted.end()).first-actual.begin();
        throw std::runtime_error("byte parity failed: "+expected.string()+" at byte "+std::to_string(pos)+"; actual saved to "+scratch.string());
    }++assertions;
}
void write_private(const std::filesystem::path& path,const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path,std::ios::binary);out<<text;out.close();
    require(bool(out),"write isolated generated C input "+path.string());
}
void strict_generated_c(const std::map<std::string,std::string>& artifacts,
                        const std::filesystem::path& scratch) {
    // The contract is the ACTUAL render for this same live/mutated input, not
    // a copied baseline or a synthetic missing-macro/compiler workaround.
    const auto& contract=artifacts.at("zynq_carrier_contract.h");
    std::vector<std::pair<std::string,unsigned>> addresses;
    const std::regex definition(R"(^#define (ZC_I2C_ADDR_[A-Z0-9_]+) (0x[0-9A-Fa-f]+) .*$)");
    std::istringstream lines(contract);std::string line;std::smatch match;
    while(std::getline(lines,line))if(std::regex_match(line,match,definition)) {
        const auto address=static_cast<unsigned>(std::stoul(match[2].str(),nullptr,16));
        require(address<=0x7f,"contract must define 7-bit I2C addresses");
        addresses.emplace_back(match[1].str(),address);
    }
    require(!addresses.empty(),"real generated contract has no I2C devices");
    require(contract.find("#define ZC_I2C_ADDR_FMC_EEPROM")==std::string::npos,
            "fixture hardware must not invent an FMC EEPROM address");
    const auto& table=artifacts.at("sc/sc_tables.c");
    const auto table_start=table.find("const sc_i2c_dev_t sc_i2c_devices[SC_I2C_DEV_COUNT] = {");
    require(table_start!=std::string::npos,"SC scan table missing");
    std::istringstream rows(table.substr(table_start));std::vector<std::string> macros;
    const std::regex row(R"SC(^    \{ "[^"]+", (ZC_I2C_ADDR_[A-Z0-9_]+) \},$)SC");
    while(std::getline(rows,line))if(std::regex_match(line,match,row))macros.push_back(match[1].str());
    require(macros.size()==addresses.size(),"scan count differs from real contract device count");
    for(std::size_t i=0;i<addresses.size();++i)
        require(macros[i]==addresses[i].first,"SC scan entry does not come from the hardware contract");
    require(table.find("ZC_I2C_ADDR_FMC_EEPROM")==std::string::npos,"unsupported FMC scan entry retained");
    require(artifacts.at("sc/sc_tables.h").find("#define SC_I2C_DEV_COUNT "+std::to_string(addresses.size())+"\n")!=std::string::npos,
            "SC header count differs from actual contract");
    const auto compiler=find_executable("cc");require(compiler.has_value(),"strict generated-C proof requires a C compiler");
    for(const auto& [path,text]:artifacts)write_private(scratch/path,text);
    const auto compile=[&](std::vector<std::string> arguments) {
        std::vector<std::string> argv{compiler->string(),"-std=c11","-Wall","-Wextra","-Wpedantic","-Werror",
            "-I",scratch.string(),"-I",(scratch/"sc").string()};
        argv.insert(argv.end(),arguments.begin(),arguments.end());
        const auto result=run_process(argv);
        require(result.exit_code==0,"strict generated C compilation failed:\n"+result.stdout_text+result.stderr_text);
    };
    std::size_t units=0;
    for(const auto& [path,text]:artifacts) {
        (void)text;
        if(std::filesystem::path(path).extension()==".c") {
            compile({"-fsyntax-only",(scratch/path).string()});++units;++generated_c_units;
        }
    }
    require(units==6,"all six portable SC C translation units must be compiled");
    std::ostringstream probe;
    probe<<"#include \"zynq_carrier_contract.h\"\n#include \"sc_tables.h\"\n"
         <<"_Static_assert(SC_I2C_DEV_COUNT == "<<addresses.size()<<", \"contract scan size\");\n"
         <<"int main(void) {\n";
    for(std::size_t i=0;i<addresses.size();++i)
        probe<<"    if (sc_i2c_devices["<<i<<"].addr7 != "<<addresses[i].second<<"U || "
             <<"sc_i2c_devices["<<i<<"].addr7 != "<<addresses[i].first<<") return 1;\n";
    probe<<"    return 0;\n}\n";
    write_private(scratch/"contract_probe.c",probe.str());
    compile({(scratch/"contract_probe.c").string(),(scratch/"sc/sc_tables.c").string(),"-o",(scratch/"contract_probe").string()});
    const auto executed=run_process({(scratch/"contract_probe").string()});
    require(executed.exit_code==0,"compiled SC device addresses disagree with live contract");++generated_c_maps;
}
template<class F> void throws(F fn,const std::string& fragment) {
    bool caught=false;try{fn();}catch(const std::exception& e){caught=true;require(std::string(e.what()).find(fragment)!=std::string::npos,"unexpected exception: "+std::string(e.what()));}
    require(caught,"expected rejection: "+fragment);
}
SomZynq live(const JsonNode& n) {
    SomZynq out;out.value=str(n,"value");out.zynq_ref=str(n,"zynq_ref");out.source=str(n,"source");
    out.pin_names=pairs(field(n,"pin_names"));out.ball_net=pairs(field(n,"ball_net"));out.jpin_net=pairs(field(n,"jpin_net"));return out;
}
SpiceResult spice(const JsonNode& n) {
    SpiceResult out;out.engine=str(n,"engine");
    for(const auto& c:field(n,"checks").array_value)out.checks.push_back({str(c,"name"),str(c,"sheet"),str(c,"kind"),str(c,"detail"),num(c,"value"),str(c,"unit"),optnum(c,"lo"),optnum(c,"hi"),str(c,"engine"),optnum(c,"spice_value")});
    return out;
}
PowerCheckResult power(const JsonNode& n) {
    PowerCheckResult out;out.errors=strings(field(n,"errors"));
    for(const auto& r:field(n,"regs").array_value)out.regs.push_back({static_cast<int>(num(r,"n")),str(r,"sheet"),str(r,"ref"),str(r,"value"),str(r,"kind"),str(r,"vin"),str(r,"vout"),num(r,"limit_a"),num(r,"eff"),str(r,"note"),num(r,"i_out"),num(r,"i_in")});
    for(const auto& b:field(n,"bridges").array_value){const auto& a=b.array_value;out.bridges.push_back({a.at(0).string_value,a.at(1).string_value,a.at(2).string_value,a.at(3).string_value});}
    return out;
}
void check_stm32(const Stm32PinMap& m,const JsonNode& expected) {
    require(m.value==str(expected,"value"),"STM32 value");
    for(const auto& label:{"nets","internal"}) {
        const auto& got=std::string(label)=="nets"?m.nets:m.internal;const auto& want=field(expected,label);
        require(got.size()==want.object_value.size(),"STM32 net count");
        for(const auto& [name,n]:want.object_value){const auto& e=got.at(name);require(e.net==str(n,"net")&&e.port==str(n,"port")&&e.pin==num(n,"pin")&&e.j_pins==strings(field(n,"j_pins")),"STM32 map mismatch: "+name);}
    }
}
void facts(const FirmwareDocsInput& in,const JsonNode& expected) {
    for(const auto& sc:in.sheets) {
        const auto& f=field(expected,sc.name);const auto& c=sc.circuit;
        const auto refs=dip_switch_refs(c);require(refs.size()==field(f,"dips").object_value.size(),sc.name+": DIP count");
        for(const auto& ref:refs) {
            auto got=dip_positions(c,ref);const auto& want=field(field(f,"dips"),ref).array_value;require(got.size()==want.size(),"DIP positions");
            for(std::size_t i=0;i<got.size();++i)require(got[i].switch_ref==str(want[i],"switch")&&got[i].position==num(want[i],"position")&&got[i].net==str(want[i],"net"),"DIP mapping");
        }
        const auto cells=en_cells(c);const auto& ec=field(f,"en_cells").array_value;require(cells.size()==ec.size(),"EN count");
        for(std::size_t i=0;i<cells.size();++i){const auto& a=cells[i];const auto& b=ec[i];require(a.sheet==str(b,"sheet")&&a.gate==str(b,"gate")&&a.enable==str(b,"enable")&&a.dip_net==str(b,"dip_net")&&a.override_net==str(b,"override_net"),"EN mapping");}
        const auto gates=module_gates(c);const auto& gs=field(f,"module_gates").array_value;require(gates.size()==gs.size(),"gate count");
        for(std::size_t i=0;i<gates.size();++i){const auto& a=gates[i];const auto& b=gs[i];const auto limit=optnum(b,"ilim_ma");require(a.ref==str(b,"ref")&&a.module==str(b,"module")&&a.rail_in==str(b,"rail_in")&&a.rail_out==str(b,"rail_out")&&a.enable==str(b,"enable")&&a.status_led==optstr(b,"status_led")&&a.ilim_ma.has_value()==limit.has_value()&&(!limit||*a.ilim_ma==*limit),"module gate mapping");}
        const auto monitors=ina3221_monitors(c);const auto& ms=field(f,"monitors").array_value;require(monitors.size()==ms.size(),"monitor count");
        for(std::size_t i=0;i<ms.size();++i){const auto& a=monitors[i];const auto& b=ms[i];require(a.ref==str(b,"ref")&&a.addr==num(b,"addr"),"monitor address");for(const auto& [ch,ns]:field(b,"channels").object_value)require(a.channels.at(std::stoi(ch))==std::make_pair(ns.array_value[0].string_value,ns.array_value[1].string_value),"monitor channels");}
        if(auto e=object_field(f,"expander")){const auto got=bringup_expander(c);require(got.ref==str(*e,"ref")&&got.addr==num(*e,"addr")&&got.ports==pairs(field(*e,"ports")),"expander");}
        if(auto cs=object_field(f,"chain")) {
            const CircuitSheetIr* monitor=nullptr;for(const auto& s:in.sheets)if(s.name=="power_mon")monitor=&s.circuit;
            auto got=regulator_chain(c,"+VIN",monitor);require(got.size()==cs->array_value.size(),"chain size");
            for(std::size_t i=0;i<got.size();++i){const auto& a=got[i];const auto& b=cs->array_value[i];require(a.ref==str(b,"ref")&&a.value==str(b,"value")&&a.enable==str(b,"enable")&&a.rail_in==str(b,"rail_in")&&a.rail_out==str(b,"rail_out")&&a.vout==optnum(b,"vout")&&a.pg_led==optstr(b,"pg_led"),"chain mapping");}
        }
    }
}
CircuitSheetIr& sheet(FirmwareDocsInput& in,const std::string& name) {for(auto& sc:in.sheets)if(sc.name==name)return sc.circuit;throw std::runtime_error("missing test sheet "+name);}
CircuitPartIr& part(CircuitSheetIr& c,const std::string& ref) {for(auto& p:c.parts)if(p.ref==ref)return p;throw std::runtime_error("missing test part "+ref);}
std::string named_pin(const CircuitPartIr& p,const std::string& name) {for(const auto& pn:p.pin_names)if(pn.name==name)return pn.numbers.at(0);throw std::runtime_error("missing test pin "+name);}
void rewire(CircuitSheetIr& c,const std::string& ref,const std::string& pin,const std::string& net) {
    for(auto& n:c.nets)n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[&](const auto& p){return p.ref==ref&&p.pin==pin;}),n.pins.end());
    if(net.empty())return;
    for(auto& n:c.nets)if(n.name==net){n.pins.push_back({ref,pin});return;}
    c.nets.push_back({net,"signal",{{ref,pin}}});
}
void frozen_mutants(const FirmwareDocsInput& original,const std::filesystem::path& dir,const std::filesystem::path& scratch) {
    const auto cases=parse_json_file((dir/"mutants.json").string());
    for(const auto& test:cases.array_value) {
        auto in=original;const auto name=str(test,"name");
        for(const auto& m:field(test,"mutations").array_value) {
            const auto op=str(m,"op");
            if(op=="part_value")part(sheet(in,str(m,"sheet")),str(m,"ref")).value=str(m,"value");
            else if(op=="gpio_pin")in.stm32.nets.at(str(m,"net")).pin=static_cast<int>(num(m,"value"));
            else if(op=="remove_sheet")in.sheets.erase(std::remove_if(in.sheets.begin(),in.sheets.end(),[&](const auto& s){return s.name==str(m,"sheet");}),in.sheets.end());
            else if(op=="rewire_named") {auto& c=sheet(in,str(m,"sheet"));const auto ref=str(m,"ref");rewire(c,ref,named_pin(part(c,ref),str(m,"pin")),str(m,"net"));}
            else throw std::runtime_error("unknown fixture mutation "+op);
        }
        std::map<std::string,std::string> rendered;
        const auto selected=object_field(test,"renderers");
        const auto renderers=selected?strings(*selected):std::vector<std::string>{"firmware","manual","scfw"};
        for(const auto& kind:renderers) {
            bool caught=false;const auto error=object_field(field(test,"errors"),kind);
            try {
                if(kind=="firmware")rendered["zynq_carrier_contract.h"]=render_firmware_contract(in);
                else if(kind=="manual")rendered["BRINGUP.md"]=render_bringup_manual(in);
                else for(const auto& f:render_scfw(in))rendered["sc/"+f.path]=f.text;
            }catch(const std::exception& e) {
                caught=true;require(error!=nullptr,name+": unexpected "+kind+" failure: "+e.what());
                // Python's direct generator raises KeyError; the public native
                // API reports the missing subsystem explicitly before rendering.
                if(name=="missing_expander")require(std::string(e.what()).find("bringup_rails")!=std::string::npos,"missing subsystem diagnostic");
                else require(e.what()==error->string_value,name+": exception bytes changed: "+e.what());
            }
            require(caught==(error!=nullptr),name+": rejection mismatch for "+kind);
        }
        const auto& artifacts=field(test,"edits").object_value;
        require(rendered.size()==artifacts.size(),name+": rendered artifact count");
        for(const auto& [path,edits]:artifacts) {
            auto wanted=read(dir/path);
            // Frozen byte edits encode the COMPLETE legacy mutant output using
            // its unchanged baseline spans; no expected values are recomputed.
            for(auto i=edits.array_value.rbegin();i!=edits.array_value.rend();++i) {
                const auto& a=i->array_value;const auto first=static_cast<std::size_t>(a[0].number_value),last=static_cast<std::size_t>(a[1].number_value);
                wanted.replace(first,last-first,a[2].string_value);
            }
            wanted=corrected_legacy_output(std::move(wanted),std::filesystem::path(path).filename().string());
            require(rendered.at(path)==wanted,name+": frozen mutant byte parity failed: "+path);
        }
        // SWD/collision mutants intentionally fail contract generation; do not
        // substitute a good baseline header to pretend those inputs compile.
        // Their complete surviving outputs and exact errors were checked above.
        if(rendered.count("zynq_carrier_contract.h")&&rendered.count("sc/sc_tables.c"))
            strict_generated_c(rendered,scratch/name);
    }
}
void live_i2c_contract_mutations(const FirmwareDocsInput& original,const std::filesystem::path& scratch) {
    for(const std::string name:{"id_eeprom_strap","monitor_strap","monitor_removed"}) {
        auto in=original;
        if(name=="id_eeprom_strap") {
            auto& services=sheet(in,"board_services");std::string ref;
            for(const auto& p:services.parts)if(p.lib_id.find("24AA025E48")!=std::string::npos)ref=p.ref;
            require(!ref.empty(),"live ID EEPROM required for strap mutation");
            rewire(services,ref,"5","GND");
            require(bringup_id_eeprom_addr(services)==0x50,"real ID EEPROM strap was not changed");
        } else {
            auto& monitors=sheet(in,"power_mon");const auto before=ina3221_monitors(monitors);
            require(before.size()==2,"monitor mutation baseline");const auto ref=before.back().ref;
            if(name=="monitor_strap") {
                const auto& device=part(monitors,ref);const auto sda=named_pin(device,"SDA");std::string net;
                for(const auto& n:monitors.nets)for(const auto& p:n.pins)if(p.ref==ref&&p.pin==sda)net=n.name;
                require(!net.empty(),"live monitor SDA net required");
                rewire(monitors,ref,named_pin(device,"A0"),net);
                require(ina3221_monitors(monitors).back().addr==0x42,"real monitor strap was not changed");
            } else {
                monitors.parts.erase(std::remove_if(monitors.parts.begin(),monitors.parts.end(),[&](const auto& p){return p.ref==ref;}),monitors.parts.end());
                for(auto& net:monitors.nets)net.pins.erase(std::remove_if(net.pins.begin(),net.pins.end(),[&](const auto& p){return p.ref==ref;}),net.pins.end());
                monitors.nc.erase(std::remove_if(monitors.nc.begin(),monitors.nc.end(),[&](const auto& p){return p.ref==ref;}),monitors.nc.end());
                require(ina3221_monitors(monitors).size()==1,"monitor removal must affect device count");
            }
        }
        std::map<std::string,std::string> artifacts{{"zynq_carrier_contract.h",render_firmware_contract(in)}};
        for(const auto& artifact:render_scfw(in))artifacts["sc/"+artifact.path]=artifact.text;
        strict_generated_c(artifacts,scratch/name);
    }
}
void mutants(const FirmwareDocsInput& original,const SpiceResult& sp,const ProjectStrings& probes,const PowerCheckResult& pr) {
    require(testplan_i2c_devices({}).empty(),"empty scan helper");
    const auto scan=testplan_i2c_devices(original.sheets);
    require(std::is_sorted(scan.begin(),scan.end()),"scan rows ordered");
    auto scan_sheets=original.sheets;
    scan_sheets.erase(std::remove_if(scan_sheets.begin(),scan_sheets.end(),[](const auto& s){return s.name=="board_services";}),scan_sheets.end());
    const auto no_aux=testplan_i2c_devices(scan_sheets);
    require(std::none_of(no_aux.begin(),no_aux.end(),[](const auto& d){return std::get<3>(d);}),"optional AUX removed");
    scan_sheets.push_back({"bringup_rails",{}, {}});
    const auto invalid=testplan_i2c_devices(scan_sheets);
    require(std::none_of(invalid.begin(),invalid.end(),[](const auto& d){return std::get<2>(d)=="TCA9535 I/O expander";}),"last duplicate optional sheet wins and invalid section skips");
    auto in=original;const auto baseline=render_firmware_contract(original);
    in.stm32.nets.at("STM32_GPIO6").pin=12;throws([&]{render_firmware_contract(in);},"SWD reservation drift");
    in=original;in.stm32.nets.erase("STM32_GPIO5");throws([&]{render_firmware_contract(in);},"live SoM netlist says absent");
    in=original;in.stm32.nets.at("STM32_DAC1").pin=9;require(render_firmware_contract(in).find("ZC_I2C_BITBANG_SDA_GPIO_PIN 9U")!=std::string::npos,"live GPIO mutation ignored");
    in=original;auto& rails=sheet(in,"bringup_rails");auto e=bringup_expander(rails);auto a1=named_pin(part(rails,e.ref),"A1");
    rewire(rails,e.ref,a1,"+3V3_SC");throws([&]{render_firmware_contract(in);},"I2C address collision");
    rewire(rails,e.ref,a1,"BAD_STRAP");throws([&]{bringup_expander(rails);},"not a valid GND/VCC strap");
    auto optional_plan=render_test_plan(in,sp,probes);require(optional_plan.find("| TCA9535 I/O expander | ")==std::string::npos,"invalid optional expander wasn't omitted");
    in=original;auto& pm=sheet(in,"power_mon");auto m=ina3221_monitors(pm).front();rewire(pm,m.ref,named_pin(part(pm,m.ref),"A0"),"BAD_STRAP");throws([&]{render_firmware_contract(in);},"unknown strap");
    in=original;auto& svc=sheet(in,"board_services");std::string eref;for(const auto& p:svc.parts)if(p.lib_id.find("24AA025E48")!=std::string::npos)eref=p.ref;
    rewire(svc,eref,"5","");throws([&]{render_firmware_contract(in);},"A0 strap (pin 5) floats");
    rewire(svc,eref,"5","GND");rewire(svc,eref,"4","+3V3_AUX");require(bringup_id_eeprom_addr(svc)==0x52,"EEPROM A1 mutation");throws([&]{render_firmware_contract(in);},"I2C address collision");
    part(svc,eref).lib_id="MUTATED:UNKNOWN";throws([&]{bringup_id_eeprom_addr(svc);},"no longer carries a 24AA025E48");
    in=original;for(auto& p:sheet(in,"usb_pd").parts)if(p.value.find("FUSB302")!=std::string::npos)p.value="unknown";
    throws([&]{render_firmware_contract(in);},"FUSB302");throws([&]{render_scfw(in);},"PD hooks would be stale");
    in=original;for(auto& p:sheet(in,"board_services").parts)if(p.value.find("TPS3823")!=std::string::npos||p.lib_id.find("TPS3823")!=std::string::npos){p.value="unknown";p.lib_id="unknown";}
    throws([&]{render_scfw(in);},"watchdog hooks would be stale");
    in=original;auto& pw=sheet(in,"power");const auto* monitor=&sheet(in,"power_mon");auto chain=regulator_chain(pw,"+VIN",monitor);bool changed=false;
    for(auto& p:pw.parts)if(p.ref[0]=='R') {const auto old=p.value;p.value="100k";const auto trial=regulator_chain(pw,"+VIN",monitor);if(trial.front().vout!=chain.front().vout){changed=true;break;}p.value=old;}
    require(changed,"no FB mutation exercised");require(render_firmware_contract(in)!=baseline,"FB value wasn't used");require(render_bringup_manual(in)!=render_bringup_manual(original),"manual FB value wasn't used");
    in=original;auto& probe_power=sheet(in,"power");probe_power.parts.push_back({"PROBE1","Connector:TestPoint","EN probe","",{},{{"1",{"1"}}},{"1"}});rewire(probe_power,"PROBE1","1","EN_5V0");
    require(render_firmware_contract(in)==baseline,"enable testpoint became regulator");
    in=original;auto& modules=sheet(in,"bringup_modules");const auto before=module_gates(modules);bool limit_changed=false;
    for(auto& p:modules.parts)if(p.ref[0]=='R'){const auto old=p.value;p.value="10k";const auto after=module_gates(modules);for(std::size_t i=0;i<before.size();++i)limit_changed|=before[i].ilim_ma!=after[i].ilim_ma;if(limit_changed)break;p.value=old;}
    require(limit_changed&&render_firmware_contract(in)!=baseline,"module ILIM mutation ignored");
    in=original;auto& shunts=sheet(in,"power_mon");for(auto& p:shunts.parts)if(p.ref.rfind("RS",0)==0)p.value="20m";
    require(render_firmware_contract(in).find("SHUNT_MOHM 20")!=std::string::npos,"shunt mutation ignored");
    in=original;in.sheets.erase(std::remove_if(in.sheets.begin(),in.sheets.end(),[](const auto& s){return s.name=="bringup_rails";}),in.sheets.end());
    require(render_firmware_contract(in).find("#define ZC_I2C_ADDR_TCA9535")==std::string::npos,"missing optional rails not omitted");
    throws([&]{render_bringup_manual(in);},"missing required");throws([&]{render_scfw(in);},"missing required");
    auto altered=sp;altered.checks.front().name="divider MUTANT_NET [fixture]";altered.checks.front().value=1.23456;altered.checks.front().lo.reset();altered.checks.front().hi=8.76543;
    auto plan=render_test_plan(original,altered,{{"MUTANT_NET","fixture.TP42"}});require(plan.find("`MUTANT_NET` | fixture.TP42 | 1.23456")!=std::string::npos,"testplan did not join mutated check/probe");
    auto cyclic=pr;PowerReg cycle;cycle.vin="+VBUS_IN";cycle.vout="+VBUS_IN";cyclic.regs.push_back(cycle);throws([&]{build_power_sequence(original.sheets,cyclic);},"reachable regulator cycle");
    auto seq=build_power_sequence(original.sheets,pr);require(!seq.chain.empty(),"chain fixture empty");seq.chain.front().load=99;seq.chain.front().enable="EN_<&>";
    // Give the overloaded node a visible parent, so an arrow is rendered.
    seq.chain.front().vin=seq.stage0.at(0);
    const auto svg=render_power_sequence_svg(seq,false);require(svg.find("#dc2626")!=std::string::npos&&svg.find("(FAIL)")!=std::string::npos&&svg.find("EN_&amp;lt;&amp;amp;&amp;gt;")!=std::string::npos,"SVG overload/status/escaping policy");
    require(render_firmware_contract(original)==baseline,"mutation contaminated original input");
}
}
int main(int argc,char** argv) {
    try {
        require(argc==3||argc==4,"usage: firmware_docs_contracts REPOSITORY SCRATCH [--live]");const auto root=std::filesystem::absolute(argv[1]);const auto scratch=std::filesystem::absolute(argv[2]);
        std::filesystem::create_directories(scratch);
        std::filesystem::current_path(scratch); // Caller cwd is intentionally outside the repository.
        require(bringup_parse_value_ohms(" 4k7 ")==4700&&bringup_parse_value_ohms("10mR")==.01&&bringup_parse_value_ohms("1M5")==1500000&&!bringup_parse_value_ohms("4K7")&&!bringup_parse_value_ohms("-2k")&&!bringup_parse_value_ohms("1e3"),"resistor parsing");
        require(bringup_c_ident("+3V3-A/B")=="P3V3_A_B"&&bringup_c_ident("5V")=="_5V","C identifier");
        require(bringup_c_ident("²µ—中文🐙")=="_²µ_中文_"&&bringup_c_ident("９V")=="_９V","Unicode C identifier semantics");
        require(bringup_parse_value_ohms("\u00a0４k７\u2003")==4700&&bringup_parse_value_ohms("١٠ mR")==.01,"Unicode numeric semantics");
        for(const std::string name:{"carrier","devkit_mini"}) {
            const auto dir=root/"native/tests/data/firmware_docs"/name;const auto snapshot=parse_json_file((dir/"inputs.json").string());
            const auto paths=resolve_project_paths(root,name);FirmwareDocsInput in{load_project_circuits(paths),stm32_pin_map(live(field(snapshot,"live")),load_som_interface(paths.som_interface_file)),strings(field(snapshot,"sources"))};
            check_stm32(in.stm32,field(snapshot,"stm32"));facts(in,field(snapshot,"facts"));
            require(firmware_absent_inputs(in)==strings(field(snapshot,"firmware_absent")),"absent firmware inputs");
            require(manual_missing_requirements(in)==strings(field(snapshot,"manual_missing")),"manual missing requirements");
            require(scfw_missing_requirements(in)==strings(field(snapshot,"scfw_missing")),"scfw missing requirements");
            exact(render_firmware_contract(in),dir/"zynq_carrier_contract.h",scratch/name/"zynq_carrier_contract.h");
            const auto sp=spice(field(snapshot,"spice"));const auto probes=pairs(field(snapshot,"probes"));
            exact(render_test_plan(in,sp,probes),dir/"TEST_PLAN.md",scratch/name/"TEST_PLAN.md");
            const auto pr=power(field(snapshot,"power"));const auto seq=build_power_sequence(in.sheets,pr);
            require(seq.stage0==strings(field(field(snapshot,"sequence"),"stage0")),"stage0 ordering");
            exact(render_power_sequence_svg(seq,pr.ok()),dir/"power_sequence.svg",scratch/name/"power_sequence.svg");
            exact(render_power_sequence_svg(seq,false),dir/"power_sequence_fail.svg",scratch/name/"power_sequence_fail.svg");
            // Join the migrated analysis APIs, independently of the frozen input transport.
            std::vector<CircuitSheetIr> circuits;for(const auto& sc:in.sheets)circuits.push_back(sc.circuit);
            const auto coverage=check_testpoint_coverage(circuits);ProjectStrings native_probes;
            for(const auto& [net,locations]:coverage.have){std::string joined;for(const auto& loc:locations){if(!joined.empty())joined+=", ";joined+=loc;}native_probes.emplace_back(net,joined);}
            exact(render_test_plan(in,extract_spice_checks(in.sheets),native_probes),dir/"TEST_PLAN.md",scratch/name/"native-TEST_PLAN.md");
            const auto native_power=analyze_power(in.sheets);
            exact(render_power_sequence_svg(build_power_sequence(in.sheets,native_power),native_power.ok()),dir/"power_sequence.svg",scratch/name/"native-power_sequence.svg");
            if(argc==4){require(std::string(argv[3])=="--live","unknown test option");const auto loaded=load_firmware_docs_input(paths);check_stm32(loaded.stm32,field(snapshot,"stm32"));require(render_firmware_contract(loaded)==render_firmware_contract(in),"live loader parity");}
            if(name=="carrier") {
                exact(render_bringup_manual(in),dir/"BRINGUP.md",scratch/name/"BRINGUP.md");
                const auto docs=render_scfw(in);require(docs.size()==14,"SC file count");for(const auto& f:docs)exact(f.text,dir/"sc"/f.path,scratch/name/"sc"/f.path);
                std::map<std::string,std::string> generated{{"zynq_carrier_contract.h",render_firmware_contract(in)}};
                for(const auto& f:docs)generated["sc/"+f.path]=f.text;
                strict_generated_c(generated,scratch/name/"compiled-baseline");
                live_i2c_contract_mutations(in,scratch/name/"compiled-live-mutations");
                const auto manual=render_bringup_manual(in);
                require(manual.find("rechargeable ML1220 backup")!=std::string::npos&&
                        manual.find("**Enable the RV-3028 trickle charger**")!=std::string::npos&&
                        manual.find("BT1` is a PRIMARY cell")==std::string::npos,"manual contradicts rechargeable hardware policy");
                require(manual.find("Do **not** fit a primary CR1220 or a LIR Li-ion")!=std::string::npos,
                        "unsafe replacement-cell warning missing");
                require(generated.at("zynq_carrier_contract.h").find("RECHARGEABLE ML1220")!=std::string::npos&&
                        generated.at("sc/sc_rtc.c").find("bk |= (uint8_t)(SC_RTC_TCE |")!=std::string::npos,
                        "manual correction must preserve real contract and existing charger enable code");
                mutants(in,sp,probes,pr);
            }else {
                throws([&]{render_bringup_manual(in);},"missing required");throws([&]{render_scfw(in);},"missing required");
            }
            frozen_mutants(in,dir,scratch/name/"compiled-frozen-mutations");
            std::cout<<name<<": typed facts, exact generated outputs, missing-input contracts passed\n";
        }
        std::cout<<assertions<<" assertions passed; "<<generated_c_units<<" generated C11 units compiled, "
                 <<generated_c_maps<<" compiled contract address maps executed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
