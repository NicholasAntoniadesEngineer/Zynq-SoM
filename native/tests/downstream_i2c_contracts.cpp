// Fresh native board_services through actual manifest, test-plan and firmware
// consumers. Independent policy constants come from test_downstream_i2c.py.
// No Python, cached circuit IR, process launch or repository writes.
#include "schgen/firmware_docs.hpp"
#include "schgen/manufacturing_exports.hpp"
#include "schgen/project_authoring.hpp"

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>

namespace {
using namespace schgen;
std::size_t checks=0, mutations=0;
void require(bool v,const std::string& why){++checks;if(!v)throw std::runtime_error(why);}
const JsonNode& field(const JsonNode& n,const std::string& key){
    const auto* p=object_field(n,key);require(p!=nullptr,"missing field "+key);return *p;
}
std::string text(const JsonNode& n,const std::string& key){
    const auto& p=field(n,key);require(p.kind==JsonKind::String,"non-string "+key);return p.string_value;
}
std::string hex(int value){std::ostringstream out;out<<"0x"<<std::hex<<std::setw(2)<<std::setfill('0')<<value;return out.str();}
Stm32PinMap pin_map(const std::filesystem::path& root){
    // Existing independent live-U9 INPUT fixture, not expected firmware output.
    // No circuit from this fixture is used: board_services is freshly authored.
    const auto raw=parse_json_file((root/"native/tests/data/firmware_docs/carrier/inputs.json").string());
    const auto& node=field(raw,"stm32");Stm32PinMap map;map.value=text(node,"value");
    for(const auto* name:{"nets","internal"})for(const auto& [key,row]:field(node,name).object_value){
        Stm32Net n;n.net=text(row,"net");n.port=text(row,"port");n.pin=static_cast<int>(field(row,"pin").number_value);
        for(const auto& pin:field(row,"j_pins").array_value)n.j_pins.push_back(pin.string_value);
        (std::string(name)=="nets"?map.nets:map.internal).emplace(key,std::move(n));
    }
    return map;
}
struct Device { int addr;std::string kind,ref,sheet,bus; };
std::vector<Device> manifest_devices(const std::vector<ProjectCircuit>& sheets){
    ManufacturingManifestInput input;input.sheets=sheets;
    // Exercise the published JSON representation, not just an internal helper.
    const auto rendered=render_manufacturing_manifest(input);
    const auto node=parse_json_text(rendered,"generated manifest");const auto& rows=field(node,"i2c_map");
    require(rows.kind==JsonKind::Array,"manifest i2c_map is not an array");std::vector<Device> out;
    for(const auto& row:rows.array_value){
        const auto& addr=field(row,"addr");require(addr.kind==JsonKind::Number&&addr.number_value>=0&&
            addr.number_value<128&&addr.number_value==static_cast<int>(addr.number_value),"manifest address is not 7-bit integer");
        Device d{static_cast<int>(addr.number_value),text(row,"device"),text(row,"ref"),text(row,"sheet"),text(row,"bus")};
        require(text(row,"addr_hex")==hex(d.addr),"manifest numeric/hex address diverges");out.push_back(std::move(d));
    }
    return out;
}
std::optional<int> macro(const std::string& header,const std::string& name){
    std::istringstream in(header);std::string line;std::optional<int> value;
    while(std::getline(in,line)){
        std::istringstream tokens(line);std::string directive,key,number;tokens>>directive>>key>>number;
        if(directive!="#define"||key!=name)continue;
        require(!value,"duplicate firmware macro "+name);std::size_t end=0;
        const auto parsed=std::stoi(number,&end,0);require(end==number.size()&&parsed>=0&&parsed<128,"invalid address macro "+name);value=parsed;
    }
    return value;
}
struct Joined {
    int firmware_address=0;
    std::vector<Device> manifest;
    std::vector<TestplanI2cDevice> plan;
    std::string header,markdown;
};
Joined join(const CircuitSheetIr& services,const Stm32PinMap& pins){
    FirmwareDocsInput input;input.sheets={{"board_services",{},services}};input.stm32=pins;
    return {bringup_id_eeprom_addr(services),manifest_devices(input.sheets),testplan_i2c_devices(input.sheets),
        render_firmware_contract(input),render_test_plan(input,{}, {})};
}
using Findings=std::set<std::string>;
Findings policy(const Joined& in,int eeprom){
    Findings out;const auto check=[&](bool ok,const std::string& code){if(!ok)out.insert(code);};
    check(in.firmware_address==eeprom,"firmware-helper-address");
    check(macro(in.header,"ZC_I2C_ADDR_ID_EEPROM")==eeprom&&macro(in.header,"ZC_I2C_ADDR_RTC")==0x52,"firmware-header-address");
    check(in.manifest.size()==2,"manifest-population");check(in.plan.size()==2,"testplan-population");
    for(const auto& expected:std::vector<std::tuple<std::string,std::string,int>>{
            {"24AA025E48","U1",eeprom},{"RV-3028","U2",0x52}}){
        const auto& kind=std::get<0>(expected);const auto& ref=std::get<1>(expected);const auto address=std::get<2>(expected);
        const auto m=std::find_if(in.manifest.begin(),in.manifest.end(),[&](const auto& d){return d.kind==kind;});
        check(m!=in.manifest.end(),"manifest-device");
        if(m!=in.manifest.end()){
            check(m->addr==address,"manifest-address");check(m->ref==ref&&m->sheet=="board_services","manifest-owner");
            check(m->bus=="AUX_I2C","manifest-aux");
        }
        const auto p=std::find_if(in.plan.begin(),in.plan.end(),[&](const auto& d){return std::get<2>(d).find(kind)!=std::string::npos;});
        check(p!=in.plan.end(),"testplan-device");
        if(p!=in.plan.end()){
            check(std::get<0>(*p)==address,"testplan-address");check(std::get<1>(*p)==ref,"testplan-owner");
            check(std::get<3>(*p),"testplan-aux");
            const auto expected_line="| `"+hex(address)+"` | "+std::get<2>(*p)+" | `"+ref+"` | Stage 6 (+3V3_AUX on) | [ ] |";
            check(in.markdown.find(expected_line)!=std::string::npos,"testplan-published-aux");
        }
    }
    check(in.markdown.find("They must NOT ACK while +3V3_AUX is OFF")!=std::string::npos,"aux-off-boundary");
    return out;
}
void killed(const Joined& in,const std::string& code){++mutations;require(policy(in,0x51).count(code)!=0,"output mutant survived: "+code);}
void replace_once(std::string& value,const std::string& from,const std::string& to){
    const auto at=value.find(from);require(at!=std::string::npos,"missing mutation target "+from);value.replace(at,from.size(),to);
}
void rewire(CircuitSheetIr& c,const std::string& pin,const std::string& net){
    std::size_t removed=0;
    for(auto& n:c.nets){const auto size=n.pins.size();n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),
        [&](const auto& p){return p.ref=="U1"&&p.pin==pin;}),n.pins.end());removed+=size-n.pins.size();}
    require(removed==1,"strap mutation must remove one actual EEPROM pin");
    if(net.empty())return;
    for(auto& n:c.nets)if(n.name==net){n.pins.push_back({"U1",pin});return;}
    throw std::runtime_error("strap destination absent: "+net);
}
template<class F>void rejects(F&& fn,const std::string& reason){
    bool failed=false;try{fn();}catch(const FirmwareDocsError& e){failed=true;require(std::string(e.what()).find(reason)!=std::string::npos,"unexpected domain failure: "+std::string(e.what()));}
    ++mutations;require(failed,"bad circuit accepted: "+reason);
}
void bad_input(const CircuitSheetIr& c,const Stm32PinMap& pins,const std::string& reason){
    const std::vector<ProjectCircuit> sheets{{"board_services",{},c}};
    rejects([&]{(void)bringup_id_eeprom_addr(c);},reason);
    rejects([&]{(void)manifest_devices(sheets);},reason);
    FirmwareDocsInput input;input.sheets=sheets;input.stm32=pins;
    rejects([&]{(void)render_firmware_contract(input);},reason);
    // Preserve the documented optional-section transport policy, not a fake
    // successful device/address: this consumer omits both invalid AUX rows.
    require(testplan_i2c_devices(sheets).empty(),"invalid optional AUX section manufactured rows");
    const auto md=render_test_plan(input,{},{});
    require(md.find("| `0x51` |")==std::string::npos&&md.find("| `0x52` |")==std::string::npos,"invalid AUX rows survived published testplan");
}
void mutants(const CircuitSheetIr& services,const Stm32PinMap& pins,const Joined& baseline){
    // Independent truth table for A1(pin 4)/A0(pin 5), including the collision.
    for(const auto& [a1,a0,expected]:std::vector<std::tuple<bool,bool,int>>{
            {false,false,0x50},{false,true,0x51},{true,false,0x52},{true,true,0x53}}){
        auto c=services;rewire(c,"4",a1?"+3V3_AUX":"GND");rewire(c,"5",a0?"+3V3_AUX":"GND");
        require(bringup_id_eeprom_addr(c)==expected,"live strap truth table");
        if(expected==0x52){
            const std::vector<ProjectCircuit> sheets{{"board_services",{},c}};const auto m=manifest_devices(sheets);const auto p=testplan_i2c_devices(sheets);
            require(m.size()==2&&m[0].addr==0x52&&m[1].addr==0x52,"manifest must not collapse colliding devices");
            require(p.size()==2&&std::get<0>(p[0])==0x52&&std::get<0>(p[1])==0x52,"testplan must not hide address collision");
            FirmwareDocsInput input;input.sheets=sheets;input.stm32=pins;
            rejects([&]{(void)render_firmware_contract(input);},"I2C address collision");
        }else require(policy(join(c,pins),expected).empty(),"three-way join did not observe live strap "+hex(expected));
    }
    for(const auto* pin:{"4","5"}){auto c=services;rewire(c,pin,"");bad_input(c,pins,"floats");}
    auto c=services;const auto eeprom=std::find_if(c.parts.begin(),c.parts.end(),[](const auto& p){return p.ref=="U1";});
    require(eeprom!=c.parts.end(),"real EEPROM missing");eeprom->lib_id="UNKNOWN:DEVICE";
    bad_input(c,pins,"no longer carries a 24AA025E48");
    c=services;c.parts.erase(std::remove_if(c.parts.begin(),c.parts.end(),[](const auto& p){return p.ref=="U1";}),c.parts.end());
    bad_input(c,pins,"no longer carries a 24AA025E48");
    auto out=baseline;out.firmware_address=0x50;killed(out,"firmware-helper-address");
    out=baseline;replace_once(out.header,"#define ZC_I2C_ADDR_ID_EEPROM 0x51","#define ZC_I2C_ADDR_ID_EEPROM 0x50");killed(out,"firmware-header-address");
    out=baseline;out.manifest.pop_back();killed(out,"manifest-population");
    out=baseline;out.manifest.front().kind="unknown";killed(out,"manifest-device");
    out=baseline;out.manifest.front().addr=0x50;killed(out,"manifest-address");
    out=baseline;out.manifest.front().sheet="always_on";killed(out,"manifest-owner");
    out=baseline;out.manifest.front().bus="STM32_I2C2";killed(out,"manifest-aux");
    out=baseline;out.plan.pop_back();killed(out,"testplan-population");
    out=baseline;std::get<2>(out.plan.front())="unknown";killed(out,"testplan-device");
    out=baseline;std::get<0>(out.plan.front())=0x50;killed(out,"testplan-address");
    out=baseline;std::get<1>(out.plan.front())="U99";killed(out,"testplan-owner");
    out=baseline;std::get<3>(out.plan.front())=false;killed(out,"testplan-aux");
    out=baseline;replace_once(out.markdown,"Stage 6 (+3V3_AUX on)","always-on");killed(out,"testplan-published-aux");
    out=baseline;replace_once(out.markdown,"They must NOT ACK while +3V3_AUX is OFF","wrong off-state policy");killed(out,"aux-off-boundary");
}
void aux_boundary(const CircuitSheetIr& services,const CircuitSheetIr& usb,const Stm32PinMap& pins){
    FirmwareDocsInput input;input.sheets={{"board_services",{},services},{"usb_pd",{},usb}};input.stm32=pins;
    auto m=manifest_devices(input.sheets);auto p=testplan_i2c_devices(input.sheets);
    require(m.size()==3&&p.size()==3,"mixed live AUX/always-on device census");
    for(const auto& d:m)require(d.bus==(d.sheet=="board_services"?"AUX_I2C":"STM32_I2C2"),"mixed manifest bus ownership");
    for(const auto& d:p)require(std::get<3>(d)==(std::get<0>(d)!=0x22),"mixed scan AUX distinction");
    auto md=render_test_plan(input,{},{});
    require(md.find("| `0x22` | FUSB302B PD PHY (fixed addr) | `U1` | always-on |")!=std::string::npos,"PD moved to AUX in published plan");
    input.sheets.erase(input.sheets.begin());m=manifest_devices(input.sheets);p=testplan_i2c_devices(input.sheets);
    require(m.size()==1&&m.front().addr==0x22&&m.front().bus=="STM32_I2C2","removing AUX must remove manifest rows");
    require(p.size()==1&&std::get<0>(p.front())==0x22&&!std::get<3>(p.front()),"removing AUX must remove scan rows");
    const auto header=render_firmware_contract(input);
    require(!macro(header,"ZC_I2C_ADDR_ID_EEPROM")&&!macro(header,"ZC_I2C_ADDR_RTC")&&
        macro(header,"ZC_I2C_ADDR_FUSB302B")==0x22,"removing AUX must remove firmware macros only for AUX");
    input.sheets={{"renamed_services",{},services}};
    require(manifest_devices(input.sheets).empty()&&testplan_i2c_devices(input.sheets).empty(),"consumers must not infer board_services from stale circuit name");
    require(!macro(render_firmware_contract(input),"ZC_I2C_ADDR_ID_EEPROM"),"renamed sheet left stale firmware address");
    require(bringup_id_eeprom_addr(services)==0x51,"standalone firmware helper changed with sheet selection");
    input.sheets.clear();require(manifest_devices({}).empty()&&testplan_i2c_devices({}).empty(),"empty inputs fabricated devices");
}
} // namespace
int main(int argc,char** argv){
    try{
        require(argc==2,"usage: downstream_i2c_contracts REPOSITORY");const std::filesystem::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"native catalog unavailable");
        struct Close{~Close(){close_part_catalog();}}close;
        std::size_t lookups=0;ProjectAuthoringInput author;author.project_root=root/"carrier";
        author.context.part=[&](const std::string& name){++lookups;return lookup_part_catalog(name);};
        const auto services=author_project_subsystem("carrier","board_services",author);
        const auto usb=author_project_subsystem("carrier","usb_pd",author);require(lookups>0,"fresh circuits bypassed real catalog");
        const auto before=authored_circuit_json(services);const auto pins=pin_map(root);const auto baseline=join(services,pins);
        require(policy(baseline,0x51).empty(),"fresh board_services three-way I2C join failed");
        mutants(services,pins,baseline);aux_boundary(services,usb,pins);
        require(authoring_json_equal(before,authored_circuit_json(services)),"mutants changed original IR");
        const auto again=join(services,pins);require(policy(again,0x51).empty()&&again.header==baseline.header&&again.markdown==baseline.markdown,"repeated native consumers changed original outputs");
        std::cout<<"PASS: "<<checks<<" downstream I2C assertions, "<<mutations<<" rejected mutations; fresh circuits -> manifest/testplan/firmware\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
