#include "selftest_full_internal.hpp"
#include "schgen/circuit_helpers.hpp"
#include "schgen/design_rules.hpp"
#include "schgen/part_checks.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/spice.hpp"
#include "schgen/symbol_law.hpp"

namespace schgen {
using namespace selftesting;
namespace {
std::vector<ProjectCircuit> sheets(const CircuitSheetIr& c){return {{c.name,{},c}};}
std::vector<std::string> nets_of(const CircuitSheetIr& c,const std::string& ref){
    std::vector<std::string> out;for(const auto& n:c.nets)if(std::any_of(n.pins.begin(),n.pins.end(),[&](const auto& p){return p.ref==ref;}))out.push_back(n.name);return out;
}
std::optional<std::string> find_part(const CircuitSheetIr& c,const std::string& suffix,const std::vector<std::string>& have,bool ground){
    for(auto p:verification::ordered_parts(c)){if(!ends(p->lib_id,suffix))continue;auto names=nets_of(c,p->ref);
        if(std::all_of(have.begin(),have.end(),[&](const auto& n){return std::find(names.begin(),names.end(),n)!=names.end();})&&
            (!ground||std::any_of(names.begin(),names.end(),[](const auto& n){return starts(n,"GND");})))return p->ref;}return std::nullopt;
}
void delete_part(CircuitSheetIr& c,const std::string& ref){
    c.parts.erase(std::remove_if(c.parts.begin(),c.parts.end(),[&](const auto& p){return p.ref==ref;}),c.parts.end());
    for(auto& n:c.nets)n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[&](const auto& p){return p.ref==ref;}),n.pins.end());
}
void erase_pin(CircuitSheetIr& c,const CircuitPinRefIr& p){for(auto& n:c.nets)n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[&](const auto& x){return x.ref==p.ref&&x.pin==p.pin;}),n.pins.end());}
void load(CircuitSheetIr& c,double amps,const std::string& note){c.loads.erase(std::remove_if(c.loads.begin(),c.loads.end(),[](const auto& l){return l.rail=="+3V3";}),c.loads.end());c.loads.push_back({"+3V3",amps,note});}
bool contains(const std::vector<std::string>& v,const std::string& sub){return std::any_of(v.begin(),v.end(),[&](const auto& s){return s.find(sub)!=s.npos;});}
std::string matching(const std::vector<std::string>& v,const std::string& sub,const std::string& fallback){for(const auto& s:v)if(s.find(sub)!=s.npos)return s;return fallback;}
SelftestModelProof board_proof(const SelftestModelFixtures& f,SymbolLibrary& lib,const fs::path& tmp,const NetlistExtractOptions& extraction){
    std::vector<BoardSheetInput> input;for(std::size_t i=0;i<f.board.size();++i)input.push_back({f.board[i],static_cast<std::int64_t>(i+1),std::nullopt});
    BoardSchematicOptions options;options.root_name="board";options.extraction=extraction;
    const auto base=build_board_schematic(input,lib,tmp/"board_base",options);
    const auto mutant=build_board_schematic(input,lib,tmp/"board_mut",options);const auto root=mutant.root_path;
    auto text=read(root);std::regex label(R"label((\(global_label\s+)"SELFTEST_LINK")label");
    auto changed=std::regex_replace(text,label,"$1\"SELFTEST_LINK_BROKEN\"",std::regex_constants::format_first_only);
    if(changed==text)return {"port_rename",base.ok(),false,"port_rename: could not find a SELFTEST_LINK root label to rename"};
    publish(root,changed);std::vector<BoardPlacedSheet> placed;
    for(std::size_t i=0;i<f.board.size();++i){auto d=uniquify_board_design(design(place_and_route_schematic(f.board[i],lib)),static_cast<std::int64_t>(i+1));
        placed.push_back({f.board[i].name,std::move(d),schematic_stable_uuid({"board","sheet-symbol",f.board[i].name})});}
    const auto check=check_board_netlist(placed,root,tmp/"board_mut",lib,extraction);
    const bool killed=!check.ok()&&contains(check.lines,"FAIL port 'SELFTEST_LINK': extracted as");
    return {"port_rename",base.ok()&&mutant.ok(),killed,"port_rename: one SELFTEST_LINK root label -> SELFTEST_LINK_BROKEN (its sheet pin keeps the old name)\n            by board merge gate: "+
        (killed?"PORT no longer merges across the two sheets":first(check.lines,"(no board finding)"))};
}
}
SelftestModelResult selftest_model_gates(const SelftestModelFixtures& f,SymbolLibrary& lib,const fs::path& scratch,const NetlistExtractOptions& options){
    SelftestModelResult out;std::vector<std::string> log={"--- model-gate mutants (design_rules / thermal / powertree / spice / testpoints / board / placer) ---"};
    auto add=[&](SelftestModelProof p){++out.injected;
        if(!p.baseline_ok){out.problems.push_back("model-gate "+p.name+": BASELINE not green — the clean fixture already trips (or pre-fires) the gate; a gate that always fires proves nothing");log.push_back("  BASELINE-FAIL "+p.name+"   <-- fixture not clean");}
        else if(p.mutation_killed){++out.killed;log.push_back("  killed    "+p.diagnostic);}
        else {out.problems.push_back("model-gate "+p.name+": MUTANT SURVIVED its gate: "+first_line(p.diagnostic));log.push_back("  SURVIVED  "+first_line(p.diagnostic)+"   <-- HOLE IN THE MODEL GATE");}
        out.proofs.push_back(std::move(p));};
    auto resolve=[&](const std::string& id)->const SymbolDef&{return lib.get(id);};
    for(const auto& name:{"drop_decap","remove_pullup","break_reset"}){
        const std::string key=name;const auto base=check_design_rules({f.design_rules},resolve);auto mut=f.design_rules;
        auto member=key=="drop_decap"?&DesignRuleResult::decap:key=="remove_pullup"?&DesignRuleResult::i2c:&DesignRuleResult::reset;
        const std::string rule=key=="drop_decap"?"decap":key=="remove_pullup"?"i2c":"reset";
        const std::vector<std::string> have=key=="drop_decap"?std::vector<std::string>{"+VDD_CORE"}:key=="remove_pullup"?std::vector<std::string>{"SC_I2C_SCL","+3V3"}:std::vector<std::string>{"SYS_RST_N"};
        const auto ref=find_part(mut,key=="remove_pullup"?":R":":C",have,key=="drop_decap");const bool good=base.ok()&&(base.*member).empty();
        if(!ref){add({key,good,false,key+": target part not found in fixture"});continue;}
        delete_part(mut,*ref);const auto res=check_design_rules({mut},resolve);const auto& fired=res.*member;
        add({key,good,!fired.empty()&&!res.ok(),key+": delete "+*ref+" ("+join(have,"/")+")\n            by design_rules "+upper(rule)+": "+first(fired,"(no finding)")});
    }
    for(const auto& name:{"float_ep","ep_to_power"}){
        const std::string key=name;const auto base=check_design_rules({f.ep},resolve);auto mut=f.ep;erase_pin(mut,{"U1","6"});
        if(key=="float_ep")mut.nc.push_back({"U1","6"});else for(auto& n:mut.nets)if(n.name=="+3V3")n.pins.push_back({"U1","6"});
        const auto res=check_design_rules({mut},resolve);
        const std::string desc=key=="float_ep"?"float_ep: nc the TLV75725 EP (pin 6)":"ep_to_power: net the TLV75725 EP onto +3V3 (non-GND)";
        add({key,base.ok()&&base.ep.empty(),!res.ok()&&!res.ep.empty(),desc+"\n            by design_rules EP: "+first(res.ep,"(no finding)")});
    }
    {const auto base=analyze_part_rules(sheets(f.cap_voltage));auto mut=f.cap_voltage;for(auto& n:mut.nets)if(n.name=="HDMI_RX_5V")n.name="+VIN";
        const auto res=analyze_part_rules(sheets(mut));add({"cap_voltage",base.ok(),!res.ok()&&!res.findings.empty(),
            "cap_voltage: 25 V MLCC HDMI_RX_5V (ok) -> +VIN 20 V (25 < 2x20)\n            by part_rules: "+first(res.findings,"(no finding)")});}
    for(const auto& name:{"thermal_overrun","thermal_waiver"}){
        const std::string key=name;const auto base=analyze_thermal(sheets(f.buck));auto mut=f.buck;load(mut,2.5,"selftest declared load");
        if(key=="thermal_waiver")mut.waivers.push_back({"thermal_waivers","U1","selftest: copper-pour derate not in single RthJA"});
        const auto pt=analyze_power(sheets(mut));const auto res=analyze_thermal(sheets(mut),pt);const bool good=base.ok()&&base.errors.empty()&&base.notes.empty();
        if(key=="thermal_overrun"){
            auto by=first(res.errors,"(no error)");by=by.substr(0,by.find(" ["));add({key,good,pt.ok()&&!res.ok()&&contains(res.errors,"OVER Tj"),
                "thermal_overrun: +3V3 draw 0.5A -> 2.5A (Tj over limit, under 3 A current limit)\n            by thermal: "+by});}
        else add({key,good,res.ok()&&contains(res.notes,"WAIVED over-limit"),"thermal_waiver: same over-Tj + c.waive_thermal -> demoted to a note, gate stays green\n            by thermal waiver path: "+shorten(matching(res.notes,"WAIVED over-limit","(not demoted)"),90)});
    }
    {const auto base=analyze_power(sheets(f.buck));auto mut=f.buck;load(mut,4,"selftest overrun");const auto res=analyze_power(sheets(mut));
        add({"power_overrun",base.ok(),!res.ok()&&contains(res.errors,"OVERRUN"),"power_overrun: +3V3 load 0.5A -> 4.0A (> 3 A limit)\n            by powertree: "+first(res.errors,"(no error)")});}
    {const auto base=extract_spice_checks(sheets(f.buck));auto mut=f.buck;for(auto& p:mut.parts)if(p.ref=="R1")p.value="33k";const auto res=extract_spice_checks(sheets(mut));
        add({"divider_drift",base.ok(),!res.ok()&&contains(res.errors(),"FB"),"divider_drift: FB top 45k3 -> 33k (Vout leaves +/-3%)\n            by spice: "+first(res.errors(),"(no error)")});}
    {const auto base=check_testpoint_coverage({f.testpoints});auto mut=f.testpoints;std::optional<std::string> drop;
        for(const auto& p:mut.parts)if(p.lib_id=="Connector:TestPoint"){const auto names=nets_of(mut,p.ref);if(std::find(names.begin(),names.end(),"+3V3")!=names.end()){drop=p.ref;break;}}
        if(!drop)add({"tp_uncovered",base.ok(),false,"tp_uncovered: +3V3 test point not found"});
        else {delete_part(mut,*drop);const auto res=check_testpoint_coverage({mut});add({"tp_uncovered",base.ok(),!res.ok()&&contains(res.errors,"+3V3"),"tp_uncovered: drop the +3V3 probe point\n            by testpoints: "+matching(res.errors,"+3V3","(no error)")});}}
    {auto base=f.mounting_hole;const auto p=add_mounting_hole(base);const ModelSheetIndex idx(base);const auto* n=idx.net(p.ref,"1");const bool good=field(p,"BOM")=="exclude"&&n&&n->name=="CHASSIS_GND"&&n->net_class=="ground";
        auto mut=f.mounting_hole;bool killed=false;std::string by="(no raise — +3V3 mounting hole was ACCEPTED)";
        try{add_mounting_hole(mut,"+3V3");}catch(const CircuitAuthoringError& e){by=e.what();killed=by.find("GROUND")!=by.npos;}
        add({"mh_short",good,killed,"mh_short: c.mounting_hole('+3V3') on a POWER rail\n            by mounting_hole guard: "+by});}
    {const auto base=check_symbol_law({f.symbol_law},lib);auto mut=f.symbol_law;
        mut.parts.push_back({"U1","schgen:LM61460","LM61460","LM61460AANRJRR:LM61460AANRJRR",{},{},{}});
        mut.nets.push_back({"+VIN_SYS","power",{{"U1","8"}}});for(auto& n:mut.nets)if(n.name=="GND")n.pins.push_back({"U1","9"});
        const auto res=check_symbol_law({mut},lib,{});add({"symbol_law",base.ok()&&base.violations.empty(),!res.ok()&&contains(res.violations,"schgen:LM61460"),
            "symbol_law: re-add hand-built schgen:LM61460 real-part symbol (PENDING emptied)\n            by symbol_law: "+shorten(first(res.violations,"(no violation)"),110)});}
    add(board_proof(f,lib,scratch/"board",options));
    const auto rail=selftest_rail_decoup_dropped(f.rail_cap,lib);add({"rail_decoup_dropped",rail.baseline_ok,rail.mutation_killed,rail.diagnostic});
    const auto clamp=selftest_clamp_thresh_strict(f.esd_clamp,lib);add({"clamp_thresh_strict",clamp.baseline_ok,clamp.mutation_killed,clamp.diagnostic});
    for(const auto& name:{"ratsnest_offboard","ratsnest_dispersed"}){
        const std::string key=name;const auto base=check_ratsnest(PcbCheckInput(f.ratsnest));auto mut=f.ratsnest;
        if(key=="ratsnest_offboard"){for(auto& p:mut.insts)if(p.ref=="R6")p.x+=200;
            const auto res=check_ratsnest(PcbCheckInput(mut));add({key,base.ok,!res.ok&&!res.off_board.empty(),"ratsnest_offboard: shove R6 200 mm past Edge.Cuts\n            by LAW-5 gate: "+shorten(first(res.off_board,"(no off-board finding)"),90)});}
        else {const std::vector<std::pair<double,double>> points={{2,2},{55,2},{55,36},{2,36}};std::size_t i=0;
            for(auto& p:mut.insts)if(p.sheet=="subsys_a"){const auto [x,y]=points.at(i++);p.x=mut.origin_x+x;p.y=mut.origin_y+y;}
            const auto res=check_ratsnest(PcbCheckInput(mut));add({key,base.ok,!res.ok&&!res.dispersed.empty(),"ratsnest_dispersed: scatter subsys_a across the board\n            by LAW-5 gate: "+shorten(first(res.dispersed,"(no dispersion finding)"),90)});}
    }
    out.report=join(log);return out;
}
} // namespace schgen
