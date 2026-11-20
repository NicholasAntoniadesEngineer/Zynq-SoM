#include "schgen/bringup_facts.hpp"
#include "schgen/firmware_docs.hpp"
#include "schgen/subsystem_data.hpp"
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
struct Joined {
    int firmware_address=0;
    std::vector<Device> manifest;
};
Joined join(const CircuitSheetIr& services){
    return {bringup_id_eeprom_addr(services),manifest_devices({{"board_services",{},services}})};
}
using Findings=std::set<std::string>;
Findings policy(const Joined& in,int eeprom){
    Findings out;const auto check=[&](bool ok,const std::string& code){if(!ok)out.insert(code);};
    check(in.firmware_address==eeprom,"firmware-helper-address");
    check(in.manifest.size()==2,"manifest-population");
    for(const auto& expected:std::vector<std::tuple<std::string,std::string,int>>{
            {"24AA025E48","U1",eeprom},{"RV-3028","U2",0x52}}){
        const auto& kind=std::get<0>(expected);const auto& ref=std::get<1>(expected);const auto address=std::get<2>(expected);
        const auto m=std::find_if(in.manifest.begin(),in.manifest.end(),[&](const auto& d){return d.kind==kind;});
        check(m!=in.manifest.end(),"manifest-device");
        if(m!=in.manifest.end()){
            check(m->addr==address,"manifest-address");check(m->ref==ref&&m->sheet=="board_services","manifest-owner");
            check(m->bus=="AUX_I2C","manifest-aux");
        }
    }
    return out;
}
void killed(const Joined& in,const std::string& code){++mutations;require(policy(in,0x51).count(code)!=0,"output mutant survived: "+code);}
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
void bad_input(const CircuitSheetIr& c,const std::string& reason){
    const std::vector<ProjectCircuit> sheets{{"board_services",{},c}};
    rejects([&]{(void)bringup_id_eeprom_addr(c);},reason);
    rejects([&]{(void)manifest_devices(sheets);},reason);
    rejects([&]{check_i2c_address_collisions(sheets);},reason);
}
void mutants(const CircuitSheetIr& services,const Joined& baseline){
    for(const auto& [a1,a0,expected]:std::vector<std::tuple<bool,bool,int>>{
            {false,false,0x50},{false,true,0x51},{true,false,0x52},{true,true,0x53}}){
        auto c=services;rewire(c,"4",a1?"+3V3_AUX":"GND");rewire(c,"5",a0?"+3V3_AUX":"GND");
        require(bringup_id_eeprom_addr(c)==expected,"live strap truth table");
        if(expected==0x52){
            const std::vector<ProjectCircuit> sheets{{"board_services",{},c}};const auto m=manifest_devices(sheets);
            require(m.size()==2&&m[0].addr==0x52&&m[1].addr==0x52,"manifest must not collapse colliding devices");
            rejects([&]{check_i2c_address_collisions(sheets);},"I2C address collision");
        }else require(policy(join(c),expected).empty(),"manifest join did not observe live strap "+hex(expected));
    }
    for(const auto* pin:{"4","5"}){auto c=services;rewire(c,pin,"");bad_input(c,"floats");}
    auto c=services;const auto eeprom=std::find_if(c.parts.begin(),c.parts.end(),[](const auto& p){return p.ref=="U1";});
    require(eeprom!=c.parts.end(),"real EEPROM missing");eeprom->lib_id="UNKNOWN:DEVICE";
    bad_input(c,"no longer carries a 24AA025E48");
    c=services;c.parts.erase(std::remove_if(c.parts.begin(),c.parts.end(),[](const auto& p){return p.ref=="U1";}),c.parts.end());
    bad_input(c,"no longer carries a 24AA025E48");
    auto out=baseline;out.firmware_address=0x50;killed(out,"firmware-helper-address");
    out=baseline;out.manifest.pop_back();killed(out,"manifest-population");
    out=baseline;out.manifest.front().kind="unknown";killed(out,"manifest-device");
    out=baseline;out.manifest.front().addr=0x50;killed(out,"manifest-address");
    out=baseline;out.manifest.front().sheet="always_on";killed(out,"manifest-owner");
    out=baseline;out.manifest.front().bus="STM32_I2C2";killed(out,"manifest-aux");
}
void aux_boundary(const CircuitSheetIr& services,const CircuitSheetIr& usb){
    std::vector<ProjectCircuit> sheets{{"board_services",{},services},{"usb_pd",{},usb}};
    auto m=manifest_devices(sheets);
    require(m.size()==3,"mixed live AUX/always-on device census");
    for(const auto& d:m)require(d.bus==(d.sheet=="board_services"?"AUX_I2C":"STM32_I2C2"),"mixed manifest bus ownership");
    sheets.erase(sheets.begin());m=manifest_devices(sheets);
    require(m.size()==1&&m.front().addr==0x22&&m.front().bus=="STM32_I2C2","removing AUX must remove manifest rows");
    sheets={{"renamed_services",{},services}};
    require(manifest_devices(sheets).empty(),"consumers must not infer board_services from stale circuit name");
    require(bringup_id_eeprom_addr(services)==0x51,"standalone firmware helper changed with sheet selection");
    sheets.clear();require(manifest_devices({}).empty(),"empty inputs fabricated devices");
}
} // namespace
int main(int argc,char** argv){
    try{
        require(argc==2,"usage: downstream_i2c_contracts REPOSITORY");const std::filesystem::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"native catalog unavailable");
        struct Close{~Close(){close_part_catalog();}}close;
        std::size_t lookups=0;ProjectAuthoringInput author;author.project_root=root/"carrier";author.context.library=root/subsystem_library_folder;
        author.context.part=[&](const std::string& name){++lookups;return lookup_part_catalog(name);};
        const auto services=author_project_subsystem("carrier","board_services",author);
        const auto usb=author_project_subsystem("carrier","usb_pd",author);require(lookups>0,"fresh circuits bypassed real catalog");
        const auto before=authored_circuit_json(services);const auto baseline=join(services);
        require(policy(baseline,0x51).empty(),"fresh board_services manifest join failed");
        mutants(services,baseline);aux_boundary(services,usb);
        require(authoring_json_equal(before,authored_circuit_json(services)),"mutants changed original IR");
        const auto again=join(services);require(policy(again,0x51).empty(),"repeated native consumers changed original outputs");
        std::cout<<"PASS: "<<checks<<" downstream I2C assertions, "<<mutations<<" rejected mutations; fresh circuits -> manifest\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
