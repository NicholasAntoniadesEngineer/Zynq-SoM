#include "schgen/firmware_docs.hpp"
#include "bringup_internal.hpp"
#include "firmware_docs_templates.hpp"

namespace schgen {
using namespace bringup_detail;
using namespace bringup_text;

std::string render_bringup_manual(const FirmwareDocsInput& in) {
    const auto absent=manual_missing_requirements(in);
    if(!absent.empty())throw FirmwareDocsError("missing required subsystems: "+join(absent,", "));
    const auto& rails=required(in,"bringup_rails");
    const auto chain=regulator_chain(required(in,"power"),"+VIN",&required(in,"power_mon"));
    const auto rail_cells=cells(sheet(in,"bringup_en")),mod_cells=cells(sheet(in,"bringup_en_modules"));
    const auto gates=module_gates(required(in,"bringup_modules"));
    const auto exp=bringup_expander(rails);const auto monitors=ina3221_monitors(required(in,"power_mon"));
    std::map<std::string,std::vector<DipPosition>> dips;
    std::map<std::string,DipPosition> dip_of;
    for(const auto& ref:dip_switch_refs(rails)) {
        dips[ref]=dip_positions(rails,ref);for(const auto& p:dips[ref])dip_of[p.net]=p;
    }
    const auto boot=dip_positions(required(in,"debug_boot"),"SW1");
    std::map<std::string,std::vector<std::string>> tps;
    const auto circuits=sheets(in);
    for(const auto& [name,c]:circuits) {
        Index ix(*c);std::map<std::string,const CircuitPartIr*> parts;
        for(const auto& p:c->parts)parts[p.ref]=&p;
        for(const auto& [ref,p]:parts)if(starts(ref,"TP")||has(p->lib_id,"TestPoint"))
            for(const auto* n:ix.nets(ref))tps[n->name].push_back(name+"."+ref);
    }
    const auto probe=[&](const std::string& net){auto p=tps.find(net);return p==tps.end()?"net `"+net+"` (no test point landed yet)":join(p->second," / ");};
    std::map<std::string,std::string> mon_of;
    for(std::size_t k=0;k<monitors.size();++k)for(const auto& [ch,ns]:monitors[k].channels)if(ns.second!="GND")
        mon_of[ns.second]="INA3221 #"+std::to_string(k+1)+" (0x"+hex(monitors[k].addr)+") ch"+std::to_string(ch)+" ["+ns.first+" -> "+ns.second+"]";
    std::ostringstream o;o.imbue(std::locale::classic());o<<manual_intro;
    std::vector<std::string> descriptions;
    for(const auto& [ref,ps]:dips)descriptions.push_back("`bringup_rails."+ref+"` ("+std::to_string(ps.size())+" wired positions)");
    o<<"1. **All DIPs OPEN.** Bring-up DIPs "<<join(descriptions,", ")<<",\n   boot-request DIP `debug_boot.SW1` ("<<boot.size()<<" positions) — every position open.\n"<<manual_stage0_continuity;
    std::vector<std::string> check_rails{"`+VIN`"};for(const auto& st:chain)check_rails.push_back("`"+st.rail_out+"`");
    std::set<std::string> gated;for(const auto& g:gates)gated.insert(g.rail_out);
    for(const auto& r:gated)check_rails.push_back("`"+r+"`");check_rails.push_back("`+3V3_SC`");
    o<<"   "<<join(check_rails,", ")<<".\n"<<manual_stage1;
    o<<"- Probe: "<<probe("+VIN")<<".\n";
    std::vector<std::string> leds;for(const auto& st:chain)leds.push_back("`power."+py(st.pg_led)+"`");
    o<<"- Every rail PG LED **off** ("<<join(leds,", ")<<"), every module status LED off.\n- The always-on `+3V3_SC` domain is alive (probe: "<<probe("+3V3_SC")<<"):\n"<<manual_always_on_table;
    for(const auto& [name,c]:circuits) {
        if(starts(name,"som_j"))continue;
        std::vector<std::string> refs;
        for(const auto& n:c->nets)if(n.name=="+3V3_SC")for(const auto& p:n.pins)if(starts(p.ref,"U")&&!contains(refs,p.ref))refs.push_back(p.ref);
        if(refs.empty())continue;
        std::stable_sort(refs.begin(),refs.end(),[](const auto& a,const auto& b){return ref_key(a)<ref_key(b);});
        Index ix(*c);std::vector<std::string> ics;for(const auto& r:refs)ics.push_back(r+" ("+ix.part(r).value+")");
        o<<"  | "<<name<<" | "<<join(ics,", ")<<" |\n";
    }
    std::vector<std::string> addresses,refs;
    for(const auto& m:monitors){addresses.push_back("`0x"+hex(m.addr)+"`");refs.push_back("`power_mon."+m.ref+"`");}
    o<<"\nRail telemetry is already live at this point: "<<join(addresses,"/")<<" (INA3221, "<<join(refs,"/")<<") answer on `STM32_I2C2` with every\n"<<manual_stage2;
    const std::map<std::string,int> budgets{{"+5V",3000},{"+3V3",3000},{"+1V8",600},{"+VIN",3000}};
    for(std::size_t k=0;k<chain.size();++k) {
        const auto& st=chain[k];const auto& cell=rail_cells.at(st.enable);const auto& dip=dip_of.at(cell.dip_net);
        o<<"### 2."<<k+1<<" `"<<st.rail_out<<"` — close `bringup_rails."<<dip.switch_ref<<"` position "<<dip.position<<"\n\n";
        o<<"- Path: `"<<st.rail_in<<"` -> `power."<<st.ref<<"` ("<<st.value<<") -> `"<<st.rail_out<<"`.\n";
        o<<"- EN cell: `"<<cell.sheet<<'.'<<cell.gate<<"` — `"<<cell.dip_net<<"` AND `"<<cell.override_net<<"` -> `"<<st.enable<<"`. A blank SC leaves the override pulled high (veto inactive).\n";
        const auto vref=fb_vref(st.value);const auto source=vref?"FB divider vs the "+st.value+" "+general(*vref)+" V reference":"fixed-output LDO";
        o<<"- Expect **"<<(st.vout?fixed(*st.vout,2)+" V":"?")<<"** on `"<<st.rail_out<<"` (setpoint derived from the netlist: "<<source<<"). Probe: "<<probe(st.rail_out)<<".\n";
        o<<"- PG LED `power."<<py(st.pg_led)<<"` lights"<<(st.rail_out=="+1V8"?" (FET-sensed: a red LED cannot run from 1.8 V, so Q1 senses the rail — power.py)":"")<<".\n";
        if(budgets.count(st.rail_out))o<<"- Current-limit context: rail budget "<<general(budgets.at(st.rail_out)/1000.0)<<" A (power_mon dossier table 1; the regulator is the limit — no rail fuse).\n";
        if(mon_of.count(st.rail_out))o<<"- Telemetry: "<<mon_of.at(st.rail_out)<<".\n";
        o<<'\n';
    }
    auto user=std::find_if(gates.begin(),gates.end(),[](const auto& g){return g.module=="USER_LED";});
    if(user!=gates.end()) {
        const auto& dip=dip_of.at(mod_cells.at(user->enable).dip_net);
        o<<"## Stage 3 — user LEDs: close `bringup_rails."<<dip.switch_ref<<"` position "<<dip.position<<'\n'<<manual_user_sources;
        o<<"- The rail DIP's spare position gates `"<<user->rail_out<<"` through `bringup_modules."<<user->ref<<"` (SY6280, ILIM "<<py(user->ilim_ma)<<" mA).\n";
        o<<"- Status LED `bringup_modules."<<py(user->status_led)<<"` lights; the user LEDs themselves are PL-driven (active-LOW) and stay dark until gateware drives them.\n\n";
    }o<<manual_stage4;
    for(const auto& g:gates) {
        const auto cell=mod_cells.find(g.enable);if(cell==mod_cells.end()||!dip_of.count(cell->second.dip_net)||g.module=="USER_LED")continue;
        const auto& dip=dip_of.at(cell->second.dip_net);const auto cons=consumers(in,g.rail_out);
        o<<"| `"<<dip.switch_ref<<"` pos "<<dip.position<<" | "<<g.module<<" | `"<<g.rail_in<<"` | `"<<g.rail_out<<"` | "<<py(g.ilim_ma)<<" mA | `bringup_modules."<<py(g.status_led)<<"` | "<<(cons.empty()?"—":join(cons,", "))<<" |\n";
    }
    if(mod_cells.count("EN_LCD_BL")) {
        const auto& spare=mod_cells.at("EN_LCD_BL");
        if(dip_of.count(spare.dip_net)) {
            const auto& dip=dip_of.at(spare.dip_net);std::string bit="?";
            for(const auto& [p,n]:exp.ports)if(n==spare.override_net){bit=p;break;}
            o<<"\n`"<<dip.switch_ref<<"` position "<<dip.position<<" is the `EN_LCD_BL` provision: its override rides TCA9535 `"<<bit<<"`\n"<<manual_spare;
        }
    }
    o<<"\nSoftware vetoes for the module cells live on the TCA9535 expander at I2C `0x"<<hex(exp.addr)<<"`\n(`bringup_rails."<<exp.ref<<"`; POR state = all inputs = DIP rules). Port map is generated\n"<<manual_boot;
    const ProjectStrings boot_fn{{"STM32_BOOT0","closed + reset = STM32 USB DFU (100R vs the SoM 1k5 pull-down)"},{"STM32_GPIO7","BOOTSEL0 request strap (10k pull-up to +3V3_SC)"},{"STM32_GPIO8","BOOTSEL1 request strap (10k pull-up to +3V3_SC)"},{"BOOT_SPARE","spare (defined-high, reserved)"}};
    for(const auto& p:boot)o<<"| "<<p.position<<" | `"<<p.net<<"` | "<<lookup(boot_fn,p.net,p.net)<<" |\n";
    o<<manual_reset;std::vector<std::string> swd;
    for(const std::string name:{"STM32_GPIO5","STM32_GPIO6"}) {
        const auto& e=in.stm32.nets.at(name);const auto jp=e.j_pins.at(0);
        swd.push_back("`"+name+"` (J1."+jp.substr(jp.find('.')+1)+") = P"+e.port+std::to_string(e.pin));
    }
    o<<"DIP is closed. "<<join(swd,"; ")<<".\n"<<manual_services;
    o<<"1. **Enable.** Close `board_aux.SW1` pos 1; probe "<<probe("+3V3_AUX")<<" = 3.3 V (the rail status LED also lights).\n"<<manual_services_steps;
    return o.str();
}
} // namespace schgen
