#include "schgen/firmware_docs.hpp"
#include "bringup_internal.hpp"
#include "firmware_docs_templates.hpp"
#include <tuple>

namespace schgen {
using namespace bringup_detail;
using namespace bringup_text;
namespace {
std::vector<std::string> missing(const FirmwareDocsInput& in,const std::vector<std::string>& names) {
    std::vector<std::string> out;for(const auto& n:names)if(!sheet(in,n))out.push_back(n);return out;
}
const Stm32Net& gpio(const FirmwareDocsInput& in,const std::string& name) {
    const auto it=in.stm32.nets.find(name);
    if(it==in.stm32.nets.end())throw FirmwareDocsError("missing STM32 net: "+name);
    return it->second;
}
std::pair<std::string,int> jpin(const Stm32Net& e) {
    if(e.j_pins.empty())throw FirmwareDocsError("missing connector pin for "+e.net);
    const auto pos=e.j_pins.front().find('.');
    if(pos==std::string::npos)throw FirmwareDocsError("invalid connector pin: "+e.j_pins.front());
    return {e.j_pins.front().substr(0,pos),std::stoi(e.j_pins.front().substr(pos+1))};
}
}
std::vector<std::string> firmware_absent_inputs(const FirmwareDocsInput& in) {
    return missing(in,{"bringup_rails","bringup_en","bringup_en_modules","power","bringup_modules","power_mon","usb_pd","board_services"});
}
std::vector<std::string> manual_missing_requirements(const FirmwareDocsInput& in) {
    return missing(in,{"power","power_mon","bringup_rails","bringup_en","bringup_en_modules","bringup_modules","debug_boot"});
}
std::vector<std::string> scfw_missing_requirements(const FirmwareDocsInput& in) {
    return missing(in,{"power","power_mon","bringup_en","bringup_modules","bringup_rails","usb_pd","board_services","bringup_en_modules"});
}
std::vector<std::string> firmware_sources(const ProjectPaths& paths) {
    const auto proj=paths.project_root.filename().string();
    std::vector<std::string> out{proj+"/som_interface.json","som/Zynq_SoM.kicad_sch (U9 pin map, live kicad-cli extraction)"};
    for(const std::string name:{"power","power_mon","bringup_rails","bringup_en","bringup_en_modules","bringup_modules","debug_boot","board_aux","board_services"}) {
        auto path=paths.subsystems_dir/name/(name+".py");
        if(!std::filesystem::exists(path))path=paths.subsystems_dir/(name+".py");
        if(!std::filesystem::exists(path))continue;
        const auto resolved=std::filesystem::canonical(path), root=std::filesystem::canonical(paths.repository_root);
        const auto relative=resolved.lexically_relative(root);
        out.push_back(relative.empty()||starts(relative.string(),"../")?path.string():relative.string());
    }
    for(const auto& [rel,what]:ProjectStrings{{"research/debug_boot_pmod.md","BOOTSEL decode, SWD reservation"},{"research/power_mon.md","I2C address map"},{"research/bringup_power_gating.md","EN-cell semantics, GPIO plan"}})
        if(std::filesystem::exists(paths.project_root/rel))out.push_back(proj+"/"+rel+" ("+what+")");
    return out;
}
FirmwareDocsInput load_firmware_docs_input(const ProjectPaths& paths,const SomExtractOptions& options) {
    FirmwareDocsInput in;in.sheets=load_project_circuits(paths);
    in.stm32=stm32_pin_map(extract_som_zynq(paths.som_schematic,"U9",{"J1","J2","J3"},options),load_som_interface(paths.som_interface_file));
    in.firmware_sources=firmware_sources(paths);return in;
}

std::string render_firmware_contract(const FirmwareDocsInput& in) {
    const auto* rails=sheet(in,"bringup_rails"), *power=sheet(in,"power"), *pmon=sheet(in,"power_mon"), *mods=sheet(in,"bringup_modules"), *usbpd=sheet(in,"usb_pd"), *services=sheet(in,"board_services");
    const std::vector<std::tuple<std::string,std::string,int,std::string>> swd{{"STM32_GPIO6","A",13,"SWDIO"},{"STM32_GPIO5","A",14,"SWCLK"}};
    for(const auto& [net,port,pin,role]:swd) {
        auto live=in.stm32.nets.find(net);
        if(live==in.stm32.nets.end()||live->second.port!=port||live->second.pin!=pin)
            throw FirmwareDocsError("SWD reservation drift: dossier says "+net+" = P"+port+std::to_string(pin)+" ("+role+"), live SoM netlist says "+(live==in.stm32.nets.end()?"absent":"P"+live->second.port+std::to_string(live->second.pin)));
    }
    const auto chain=power?regulator_chain(*power,"+VIN",pmon):std::vector<RegulatorStage>{};
    const auto rail_cells=cells(sheet(in,"bringup_en"));
    const auto* enm=sheet(in,"bringup_en_modules");const auto mod_cells=enm?en_cells(*enm):std::vector<EnCell>{};
    const auto exp=rails?std::optional<BringupExpander>(bringup_expander(*rails)):std::nullopt;
    const auto monitors=pmon?ina3221_monitors(*pmon):std::vector<BringupMonitor>{};
    std::map<std::string,ModuleGate> gates;if(mods)for(const auto& g:module_gates(*mods))gates[g.enable]=g;
    ProjectStrings dips;
    if(rails)for(const auto& ref:dip_switch_refs(*rails))for(const auto& p:dip_positions(*rails,ref)) {
        const auto description=p.switch_ref+" pos "+std::to_string(p.position);
        auto existing=std::find_if(dips.begin(),dips.end(),[&](const auto& item){return item.first==p.net;});
        if(existing==dips.end())dips.emplace_back(p.net,description);
        else existing->second=description; // Dictionary assignment: last position wins.
    }
    if(usbpd&&!std::any_of(usbpd->parts.begin(),usbpd->parts.end(),[](const auto& p){return has(p.value,"FUSB302");}))throw FirmwareDocsError("usb_pd netlist no longer carries a FUSB302 — I2C address map stale");
    struct Address{std::string macro;int addr;std::string what;};std::vector<Address> addresses;
    if(exp)addresses.push_back({"ZC_I2C_ADDR_TCA9535",exp->addr,"bring-up override expander (bringup_rails; A2=A1=A0 straps read from the netlist)"});
    if(usbpd)addresses.push_back({"ZC_I2C_ADDR_FUSB302B",0x22,"USB-PD PHY (usb_pd; fixed address, onsemi DS)"});
    for(std::size_t k=0;k<monitors.size();++k)addresses.push_back({"ZC_I2C_ADDR_INA3221_"+std::to_string(k+1),monitors[k].addr,"rail monitor #"+std::to_string(k+1)+" (power_mon "+monitors[k].ref+"; A0 strap read from the netlist)"});
    if(services) {
        addresses.push_back({"ZC_I2C_ADDR_ID_EEPROM",bringup_id_eeprom_addr(*services),"board-ID EEPROM w/ EUI-48 MAC (board_services 24AA025E48; A1/A0 straps read from the netlist; on the board_aux-isolated AUX I2C)"});
        addresses.push_back({"ZC_I2C_ADDR_RTC",0x52,"RTC (board_services RV-3028; fixed address, Micro Crystal DS; on the board_aux-isolated AUX I2C). VBACKUP is a RECHARGEABLE ML1220 (Mn-Li) for a maintenance-free RTC: firmware SHOULD ENABLE the RV-3028 trickle charger (set TCE + a series resistance, e.g. 3k, in the EEPROM Backup register) so it tops up whenever the board is powered. Do NOT fit a primary CR1220 (it would be charged) or a LIR Li-ion (its 4.2 V target exceeds the 3.3 V supply)."});
    }
    std::set<int> unique;std::vector<std::string> collision;
    for(const auto& a:addresses){unique.insert(a.addr);collision.push_back(a.macro+"=0x"+hex(a.addr,0,false));}
    if(unique.size()!=addresses.size())throw FirmwareDocsError("I2C address collision: "+join(collision,", "));
    std::ostringstream o;o.imbue(std::locale::classic());o<<firmware_intro;
    for(const auto& s:in.firmware_sources)o<<" *   "<<s<<'\n';
    const auto absent=firmware_absent_inputs(in);if(!absent.empty())o<<" * absent on this project (their sections are omitted):\n *   "<<join(absent,", ")<<'\n';
    o<<" *\n * system controller: SoM U9 = "<<in.stm32.value<<'\n'<<firmware_live;
    for(const auto& net:std::vector<std::string>{"STM32_GPIO5","STM32_GPIO6"}) {
        const auto& e=gpio(in,net);const auto [conn,jp]=jpin(e);
        o<<"/* !!   "<<net<<" ("<<conn<<'.'<<jp<<") = P"<<e.port<<e.pin<<" = "<<(net=="STM32_GPIO5"?"SWCLK":"SWDIO")<<" */\n";
    }o<<firmware_swd_footer;
    for(const auto& [name,e]:in.stm32.nets) {
        std::vector<std::string> notes;
        if(name=="STM32_GPIO5"||name=="STM32_GPIO6")notes.push_back(std::string("RESERVED: ")+(name=="STM32_GPIO5"?"SWCLK":"SWDIO")+" (see above)");
        if(name=="STM32_GPIO7")notes.push_back("BOOTSEL0 request strap (debug_boot SW1 pos 2)");
        if(name=="STM32_GPIO8")notes.push_back("BOOTSEL1 request strap (debug_boot SW1 pos 3)");
        for(const auto& [port,g]:rail_override_gpio)if(name==g)notes.push_back("rail-EN override veto -> "+port);
        if(name=="STM32_GPIO4")notes.push_back("TCA9535 INT# (open-drain, 10k to +3V3_SC)");
        o<<"/* "<<name<<(notes.empty()?"":" — "+join(notes,"; "))<<" */\n";
        const auto prefix="ZC_"+bringup_c_ident(e.net);
        if(!e.j_pins.empty()) {
            const auto [conn,pin]=jpin(e);o<<"#define "<<prefix<<'_'<<conn<<"_PIN "<<pin;
            if(e.j_pins.size()>1)o<<"  /* also "<<join({e.j_pins.begin()+1,e.j_pins.end()},", ")<<" */";
            o<<'\n';
        }o<<"#define "<<prefix<<"_GPIO_PORT '"<<e.port<<"'\n#define "<<prefix<<"_GPIO_PIN "<<e.pin<<"U\n";
    }o<<firmware_internal;
    for(const auto& [name,e]:in.stm32.internal)if(starts(name,"ZYNQ_"))o<<"/* "<<name<<" — SoM-internal */\n#define ZC_SOM_"<<bringup_c_ident(name)<<"_GPIO_PORT '"<<e.port<<"'\n#define ZC_SOM_"<<bringup_c_ident(name)<<"_GPIO_PIN "<<e.pin<<"U\n";
    o<<firmware_bootsel;
    for(int k=0;k<2;++k) {
        const auto name="STM32_GPIO"+std::to_string(k+7);const auto& e=gpio(in,name);const auto [conn,pin]=jpin(e);
        o<<"#define ZC_BOOTSEL"<<k<<"_GPIO_PORT '"<<e.port<<"'   /* "<<name<<", "<<conn<<'.'<<pin<<" */\n#define ZC_BOOTSEL"<<k<<"_GPIO_PIN "<<e.pin<<"U\n";
    }
    const std::vector<std::string> modes{"JTAG","QSPI","SD","RESERVED"};for(int i=0;i<4;++i)o<<"#define ZC_BOOT_REQ_"<<modes[i]<<" 0x"<<hex(i,0)<<'\n';
    o<<firmware_i2c;
    for(const auto& a:addresses)o<<"#define "<<a.macro<<" 0x"<<hex(a.addr)<<"  /* "<<a.what<<" */\n";
    o<<firmware_bitbang;
    for(int i=0;i<2;++i) {
        const auto& e=gpio(in,i?"STM32_DAC2":"STM32_DAC1");const auto bus=i?"SCL":"SDA";
        o<<"#define ZC_I2C_BITBANG_"<<bus<<"_GPIO_PORT '"<<e.port<<"'   /* STM32_I2C2_"<<bus<<" = STM32_DAC"<<(i+1)<<", J1."<<(i?55:49)<<" */\n#define ZC_I2C_BITBANG_"<<bus<<"_GPIO_PIN "<<e.pin<<"U\n";
    }o<<'\n';
    if(power) {
        o<<firmware_rail<<"#define ZC_RAIL_COUNT "<<chain.size()<<'\n';
        for(std::size_t k=0;k<chain.size();++k) {
            const auto& st=chain[k];auto cell=rail_cells.find(st.enable);const auto gname=cell==rail_cells.end()?"":lookup(rail_override_gpio,cell->second.override_net);
            const auto dip=cell==rail_cells.end()?"?":lookup(dips,cell->second.dip_net,"?");
            o<<"/* stage "<<k<<": "<<st.rail_in<<" -> "<<st.rail_out<<" ("<<st.value<<' '<<st.ref<<", power sheet; DIP "<<dip<<"; PG LED "<<st.pg_led.value_or("-")<<") */\n";
            o<<"#define ZC_RAIL"<<k<<"_NAME \""<<st.rail_out<<"\"\n#define ZC_RAIL"<<k<<"_VOUT_MV "<<(st.vout?rounded(*st.vout*1000):0)<<"\n#define ZC_RAIL"<<k<<"_EN_NET \""<<st.enable<<"\"\n";
            if(!gname.empty()&&in.stm32.nets.count(gname)) {
                const auto& e=gpio(in,gname);o<<"#define ZC_RAIL"<<k<<"_OVERRIDE_GPIO_PORT '"<<e.port<<"'   /* "<<cell->second.override_net<<" -> "<<gname<<" */\n#define ZC_RAIL"<<k<<"_OVERRIDE_GPIO_PIN "<<e.pin<<"U\n";
            }
        }
    }
    if(exp){const auto& e=gpio(in,"STM32_GPIO4");o<<"#define ZC_BRINGUP_INT_GPIO_PORT '"<<e.port<<"'   /* SC_INT_N (TCA9535 INT# wire-OR FUSB302 INT) -> STM32_GPIO4 */\n#define ZC_BRINGUP_INT_GPIO_PIN "<<e.pin<<"U\n";}
    if(power||exp)o<<'\n';
    if(exp) {
        o<<firmware_expander;auto ports=exp->ports;std::sort(ports.begin(),ports.end());
        const ProjectStrings input_notes{{"P11","INA3221 CRITICAL wire-OR (power_mon, 10k PU +3V3_SC)"},{"P14","TPS2051C fault (usbc_otg, 100k PU re-railed +3V3_SC)"},{"P15","TPS26631 +VIN eFuse fault (pd_input, 100k PU +3V3_SC)"}};
        for(const auto& port:ports) {
            const auto& pname=port.first;
            const auto& net=port.second;
            int bit=(pname[1]-'0')*8+pname[2]-'0';
            auto cell=std::find_if(mod_cells.begin(),mod_cells.end(),[&](const auto& c){return c.override_net==net;});
            if(cell!=mod_cells.end()) {
                const auto g=gates.find(cell->enable);const auto dip=lookup(dips,cell->dip_net,"?");
                std::string ctx=net+" -> "+cell->enable;
                if(g!=gates.end())ctx+=" ("+g->second.rail_out+", ILIM "+py(g->second.ilim_ma)+" mA, DIP "+dip+")";
                else ctx+=" (DIP "+dip+")";
                o<<"#define ZC_TCA9535_BIT_"<<bringup_c_ident(cell->enable)<<' '<<bit<<"  /* "<<pname<<": "<<ctx<<" */\n";
            }else{
                const auto note=lookup(input_notes,pname);o<<"/* "<<pname<<" (bit "<<bit<<"): "<<net<<(note.empty()?" — spare, 100k to GND":" — INPUT: "+note)<<" */\n";
            }
        }o<<'\n';
    }
    if(pmon) {
        o<<firmware_pmon;
        for(std::size_t k=0;k<monitors.size();++k) {
            const auto& m=monitors[k];o<<"/* monitor #"<<k+1<<": "<<m.ref<<" @ 0x"<<hex(m.addr)<<" */\n";
            for(const auto& [ch,ns]:m.channels) {
                const auto& [inp,inn]=ns;if(inp=="GND"&&inn=="GND"){o<<"/* "<<m.ref<<" ch"<<ch<<": unused (inputs tied to GND per TI DS) */\n";continue;}
                o<<"#define ZC_PMON"<<k+1<<"_CH"<<ch<<"_RAIL \""<<inn<<"\"  /* "<<inp<<" -> "<<inn<<" */\n";
                auto shunt=bringup_shunt_mohm(*pmon,inp,inn);if(shunt)o<<"#define ZC_PMON"<<k+1<<"_CH"<<ch<<"_SHUNT_MOHM "<<*shunt<<'\n';
            }
        }o<<'\n';
    }o<<"#endif /* ZYNQ_CARRIER_CONTRACT_H */\n";return ascii(o.str());
}
} // namespace schgen
