#pragma once
#include "schgen/authoring.hpp"
#include "board_aux_frozen_identity.hpp"
#include <algorithm>
#include <stdexcept>

// Test-only bridge to immutable migration oracles. Validate the reviewed live
// identity BEFORE projecting only enumerated reviewed changes; all other IR stays visible
// to the caller's independent full-IR or canonical-byte comparison.
namespace historical_input_contracts {
inline void require(bool ok, const std::string& why) {
    if (!ok) throw std::runtime_error(why);
}
inline schgen::CircuitSheetIr project(schgen::CircuitSheetIr live,
                                     const std::string& project_name) {
    if (project_name != "carrier" || live.name != "board_aux") return live;
    require(std::count_if(live.parts.begin(), live.parts.end(), [](const auto& p) {
        return p.ref == "C1"; }) == 1, "unique reviewed board_aux C1");
    auto& c1 = *std::find_if(live.parts.begin(), live.parts.end(), [](const auto& p) {
        return p.ref == "C1"; });
    require(c1.lib_id == "Device:C" && c1.value == "10u" &&
        c1.footprint == "Capacitor_SMD:C_0805_2012Metric", "reviewed board_aux C1 identity");
    require(std::count_if(c1.fields.begin(), c1.fields.end(), [](const auto& f) {
        return f.key == "LCSC"; }) == 1, "unique reviewed board_aux C1 LCSC");
    auto& code = *std::find_if(c1.fields.begin(), c1.fields.end(), [](const auto& f) {
        return f.key == "LCSC"; });
    require(code.value == "C15850", "reviewed board_aux C1 BOM identity");
    c1.value = "100n";
    c1.footprint = "Capacitor_SMD:C_0603_1608Metric";
    code.value = "C14663";
    // 18a73d9f corrected reference current limiting, EN wiring and the C5
    // filter. Validate the independent full pin/reference/NC oracle first;
    // never use this historical projection as hardware qualification.
    board_aux_frozen::verify(live);
    auto c5=std::find_if(live.parts.begin(),live.parts.end(),[](const auto& p){return p.ref=="C5";});
    require(c5!=live.parts.end()&&c5->lib_id=="Device:C"&&c5->value=="100p"&&
        c5->footprint=="Capacitor_SMD:C_0603_1608Metric","reviewed reference filter identity");
    require(std::count_if(c5->fields.begin(),c5->fields.end(),[](const auto& f){return f.key=="LCSC";})==1,"unique C5 BOM identity");
    auto c5_code=std::find_if(c5->fields.begin(),c5->fields.end(),[](const auto& f){return f.key=="LCSC";});
    require(c5_code->value=="C14858","reviewed reference filter BOM");
    c5->value="100n";c5_code->value="C14663";
    const auto restore_net=[&](const std::string& current,const std::vector<std::string>& from,
                             const std::string& original,const std::vector<std::string>& to) {
        require(std::count_if(live.nets.begin(),live.nets.end(),[&](const auto& n){return n.name==current;})==1,"unique reviewed reference net");
        auto& net=*std::find_if(live.nets.begin(),live.nets.end(),[&](const auto& n){return n.name==current;});
        std::vector<std::string> actual;for(const auto& pin:net.pins)actual.push_back(pin.ref+"."+pin.pin);
        require(actual==from,"reviewed reference net ordered preimage");
        net.name=original;net.pins.clear();
        for(const auto& pin:to){const auto dot=pin.find('.');net.pins.push_back({pin.substr(0,dot),pin.substr(dot+1)});}
    };
    restore_net("+3V3_AUX",{"U1.1","C2.1","C3.1","D1.2","U2.8","R4.1","R5.1","R6.1","TP1.1"},
        "+3V3_AUX",{"U1.1","C2.1","C3.1","D1.2","U2.7","R4.1","R5.1","R6.1","C5.1","TP1.1"});
    restore_net("AUX_ISO_REF",{"U2.7","R4.2","C5.1"},"AUX_ISO_EN",{"U2.8","R4.2"});
    return live;
}

// Exercise each consumer's actual comparator, including canonical bytes/hash.
// Reverted/ambiguous identities must fail, as must unrelated electrical drift.
template<class Matches> void check(const schgen::CircuitSheetIr& live,
                                  const std::string& project_name, Matches matches) {
    require(matches(project(live, project_name)), project_name + ":" + live.name +
        " differs beyond reviewed capacitor/reference-topology deltas from immutable historical input");
    if (project_name != "carrier" || live.name != "board_aux") return;
    auto rejects = [&](const auto& changed) {
        bool rejected = false;
        try { rejected = !matches(project(changed, project_name)); }
        catch (const std::runtime_error&) { rejected = true; }
        require(rejected, "historical input comparator accepted a C1/unrelated mutation");
    };
    for (int mutation = 0; mutation != 12; ++mutation) {
        auto changed = live;
        auto it = std::find_if(changed.parts.begin(), changed.parts.end(), [](const auto& p) {
            return p.ref == "C1"; });
        auto& c1 = *it;
        if (mutation == 0) c1.value = "100n";
        if (mutation == 1) c1.footprint = "Capacitor_SMD:C_0603_1608Metric";
        if (mutation == 2) for (auto& f : c1.fields) if (f.key == "LCSC") f.value = "C14663";
        if (mutation == 3) c1.lib_id = "Device:R";
        if (mutation == 4) c1.fields.push_back({"LCSC", "C15850"});
        if (mutation == 5) c1.fields.clear();
        if (mutation == 6) { const auto duplicate = c1; changed.parts.push_back(duplicate); }
        if (mutation == 7) changed.parts.erase(it);
        if (mutation == 8) {
            auto c2 = std::find_if(changed.parts.begin(), changed.parts.end(), [](const auto& p) {
                return p.ref == "C2"; });
            require(c2 != changed.parts.end() && c2->value == "100n", "unchanged C2 preimage");
            c2->value = "1n";
        }
        if (mutation == 9) { require(!changed.nets.empty(), "net preimage"); changed.nets.front().name += "_drift"; }
        if (mutation == 10) { require(!changed.nc.empty(), "NC preimage"); changed.nc.pop_back(); }
        if (mutation == 11) changed.title += " drift";
        rejects(changed);
    }
    for(int mutation=0;mutation<5;++mutation) {
        auto changed=live;
        auto& c5=*std::find_if(changed.parts.begin(),changed.parts.end(),[](const auto& p){return p.ref=="C5";});
        if(mutation==0)c5.value="100n";
        if(mutation==1)for(auto& f:c5.fields)if(f.key=="LCSC")f.value="C14663";
        if(mutation==2)c5.footprint="Capacitor_SMD:C_0805_2012Metric";
        if(mutation==3)c5.fields.push_back({"LCSC","C14858"});
        if(mutation==4){const auto copy=c5;changed.parts.push_back(copy);}
        rejects(changed);
    }
    for(const auto& target:std::vector<std::string>{"U2.7","U2.8","R4.2","C5.1"}) {
        auto changed=live;bool found=false;
        for(auto& net:changed.nets)for(auto& pin:net.pins)if(pin.ref+"."+pin.pin==target){pin.pin+="_drift";found=true;}
        require(found,"reference topology mutation preimage");rejects(changed);
    }
    // Identical sheet names in another project receive no projection.
    require(schgen::authoring_json_equal(schgen::authored_circuit_json(project(live, "devkit_mini")),
        schgen::authored_circuit_json(live)), "C1 projection crossed project boundary");
}
} // namespace historical_input_contracts
