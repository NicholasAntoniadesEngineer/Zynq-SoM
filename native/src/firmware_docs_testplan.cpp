#include "schgen/firmware_docs.hpp"
#include "bringup_internal.hpp"
#include "firmware_docs_templates.hpp"
#include "verification_internal.hpp"
#include <regex>
#include <tuple>

namespace schgen {
using namespace bringup_detail;
using namespace bringup_text;
namespace {
// These optional derived sections historically skip ordinary domain failures.
// Do not turn allocation/process failures into successful empty sections.
template<class F> void optional_section(F fn) {
    try {fn();} catch(const FirmwareDocsError&) {} catch(const std::out_of_range&) {} catch(const std::invalid_argument&) {}
}
std::optional<std::string> check_net(const SpiceCheck& ch) {
    std::smatch m;
    // Python's regex \s is Unicode-aware. Preserve net bytes while recognizing
    // the same whitespace boundaries, including in synthetic caller inputs.
    for(const std::string prefix:{"divider","RC"})if(starts(ch.name,prefix)) {
        const auto tail=verification::utf8(ch.name.substr(prefix.size()));
        if(tail.empty()||!verification::space(tail.front().first))continue;
        std::size_t i=0;while(i<tail.size()&&verification::space(tail[i].first))++i;
        std::string net;while(i<tail.size()&&!verification::space(tail[i].first)&&tail[i].first!='[')net+=tail[i++].second;
        if(!net.empty())return net;
    }
    static const std::regex fb(R"(FB \(([^)]+)\))"),voltage(R"(([+\-][0-9A-Z_]+)=\S+V)");
    if(std::regex_search(ch.name,m,fb))return m[1];
    if(starts(ch.name,"BOOT0"))return "BOOT0_SET";
    std::string detail;for(const auto& [cp,bytes]:verification::utf8(ch.detail))detail+=verification::space(cp)?" ":bytes;
    if(std::regex_search(detail,m,voltage))return m[1];
    return std::nullopt;
}
std::string fmt(const std::optional<double>& v,const std::string& unit) {
    if(!v)return "—";
    return verification::strip(general(*v)+" "+unit);
}
}
std::vector<TestplanI2cDevice> testplan_i2c_devices(const std::vector<ProjectCircuit>& circuits) {
    std::map<std::string,const CircuitSheetIr*> by_name;
    for(const auto& sc:circuits)by_name[sc.name]=&sc.circuit;
    const auto optional=[&](const std::string& name)->const CircuitSheetIr* {
        const auto it=by_name.find(name);return it==by_name.end()?nullptr:it->second;
    };
    std::vector<TestplanI2cDevice> devs;
    if(const auto* c=optional("bringup_rails"))optional_section([&]{auto e=bringup_expander(*c);devs.emplace_back(e.addr,e.ref,"TCA9535 I/O expander",false);});
    if(const auto* c=optional("power_mon"))optional_section([&]{for(const auto& m:ina3221_monitors(*c))devs.emplace_back(m.addr,m.ref,"INA3221 rail monitor",false);});
    if(optional("usb_pd"))devs.emplace_back(0x22,"U1","FUSB302B PD PHY (fixed addr)",false);
    if(const auto* c=optional("board_services"))optional_section([&]{devs.emplace_back(bringup_id_eeprom_addr(*c),"U1","24AA025E48 ID-EEPROM (EUI-48 MAC)",true);devs.emplace_back(0x52,"U2","RV-3028 RTC",true);});
    std::sort(devs.begin(),devs.end());
    return devs;
}
std::string render_test_plan(const FirmwareDocsInput& in,const SpiceResult& result,const ProjectStrings& probes) {
    std::map<std::string,int> stages{{"+3V3_SC",1},{"+VIN",1},{"+VBUS_IN",1},{"USB_UART_VBUS",1},{"CP2102N_VBUS_SNS",1},{"PD_OVP_SET",1}};
    if(const auto* power=sheet(in,"power"))optional_section([&]{
        for(const auto& st:regulator_chain(*power,"+VIN",sheet(in,"power_mon")))stages.emplace(st.rail_out,2);
        for(const auto& n:power->nets)if(starts(n.name,"PG_"))stages.emplace(n.name,2);
    });
    if(const auto* mods=sheet(in,"bringup_modules"))optional_section([&]{for(const auto& g:module_gates(*mods))stages.emplace(g.rail_out,g.module=="USER_LED"?3:4);});
    stages.emplace("BOOT0_SET",5);stages.emplace("STM32_NRST",5);stages["+3V3_AUX"]=6;stages.emplace("HDMI_RX_5V",4);stages.emplace("HDMI_RX_5V_DET",4);
    using Row=std::pair<std::optional<std::string>,const SpiceCheck*>;std::map<int,std::vector<Row>> rows;
    for(const auto& ch:result.checks) {auto net=check_net(ch);int stage=net&&stages.count(*net)?stages.at(*net):2;rows[stage].emplace_back(net,&ch);}
    for(auto& [stage,rs]:rows){(void)stage;std::stable_sort(rs.begin(),rs.end(),[](const Row& a,const Row& b){return std::make_pair(a.first.value_or("~"),a.second->name)<std::make_pair(b.first.value_or("~"),b.second->name);});}
    const std::vector<std::string> titles{"Stage 0 — power-off continuity","Stage 1 — first power: PD + always-on +3V3_SC domain","Stage 2 — rails, one DIP at a time","Stage 3 — user IO","Stage 4 — module load switches","Stage 5 — boot modes, JTAG, SWD","Stage 6 — board services (+3V3_AUX): ID-EEPROM, RTC, watchdog, QWIIC"};
    std::ostringstream o;o<<testplan_intro<<"Source spice gate: "<<result.checks.size()<<" checks, "<<result.engine<<".\n"<<testplan_electrical;
    for(int st=0;st<7;++st) {
        if(!rows.count(st)||rows.at(st).empty())continue;const auto& rs=rows.at(st);
        o<<"### "<<titles[st]<<'\n'<<testplan_columns;
        for(std::size_t i=0;i<rs.size();++i) {
            const auto& [net,ch]=rs[i];const auto pad=net?lookup(probes,*net,"—"):"—";
            o<<"| "<<st<<'.'<<i+1<<' '<<ch->name<<" | "<<(net?"`"+*net+"`":"—")<<" | "<<pad<<" | "<<fmt(ch->value,ch->unit)<<" | "<<fmt(ch->lo,ch->unit)<<" | "<<fmt(ch->hi,ch->unit)<<" | `______` | [ ] |\n";
        }o<<testplan_rationale;
        for(std::size_t i=0;i<rs.size();++i){const auto& ch=*rs[i].second;o<<"- **"<<st<<'.'<<i+1<<' '<<ch.name<<"** ("<<ch.sheet<<"): "<<ch.detail<<'\n';}
        o<<testplan_rationale_end;
    }
    const auto devs=testplan_i2c_devices(in.sheets);o<<testplan_i2c;std::vector<std::string> on,aux;
    for(const auto& [addr,ref,kind,is_aux]:devs) {
        o<<"| `0x"<<hex(addr)<<"` | "<<kind<<" | `"<<ref<<"` | "<<(is_aux?"Stage 6 (+3V3_AUX on)":"always-on")<<" | [ ] |\n";
        (is_aux?aux:on).push_back("0x"+hex(addr));
    }
    o<<"\nAlways-on set (with `+3V3_SC`): "<<join(on,"/")<<". Any EXTRA address, or any of these missing, means a strap or bus fault.\n";
    if(!aux.empty())o<<"\nWith `+3V3_AUX` enabled (Stage 6), the board_aux PCA9306 isolator joins the AUX segment and additionally "<<join(aux,"/")<<" must ACK (ID-EEPROM, RTC). They must NOT ACK while +3V3_AUX is OFF (proves the isolator). Cross-check `carrier/docs/BRINGUP.md`.\n";
    o<<testplan_functional;std::vector<ModuleGate> gates;
    if(const auto* c=sheet(in,"bringup_modules"))optional_section([&]{gates=module_gates(*c);});
    const ProjectStrings hints{{"HDMI_TX","drive a display / read sink EDID over DDC"},{"HDMI_RX","detect a source's cable +5V, read its EDID"},{"LCD","panel backlight + touch (CTP I2C) respond"},{"LCD_BL","panel backlight current per the SY7201 ISET law"},{"USER_LED","PL-driven user LEDs (dark until gateware drives them)"},{"CAM","MIPI camera link enumerates"},{"CAMERA","MIPI camera link enumerates"}};
    std::stable_sort(gates.begin(),gates.end(),[](const auto& a,const auto& b){return a.module<b.module;});
    for(const auto& g:gates) {
        const auto cons=consumers(in,g.rail_out);const auto fallback="module on "+(cons.empty()?"—":join(cons,", "))+" powers and responds";
        o<<"| "<<g.module<<" | `"<<g.rail_out<<"` | "<<(g.status_led?"`bringup_modules."+*g.status_led+"`":"—")<<" | "<<lookup(hints,g.module,fallback)<<" |\n";
    }o<<'\n';return o.str();
}
} // namespace schgen
