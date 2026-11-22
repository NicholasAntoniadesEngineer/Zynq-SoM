#pragma once
#include "schgen/authoring.hpp"
#include "board_aux_frozen_identity.hpp"
#include <algorithm>
#include <iterator>
#include <stdexcept>
#include <utility>

// Test-only bridge to immutable migration oracles. Validate the reviewed live
// identity BEFORE projecting only enumerated reviewed changes; all other IR stays visible
// to the caller's independent full-IR or canonical-byte comparison.
namespace historical_input_contracts {
inline void require(bool ok, const std::string& why) {
    if (!ok) throw std::runtime_error(why);
}
inline schgen::CircuitPartIr& unique_part(schgen::CircuitSheetIr& sheet, const std::string& ref) {
    require(std::count_if(sheet.parts.begin(), sheet.parts.end(), [&](const auto& p) { return p.ref == ref; }) == 1,
            "unique reviewed part " + sheet.name + "." + ref);
    return *std::find_if(sheet.parts.begin(), sheet.parts.end(), [&](const auto& p) { return p.ref == ref; });
}
inline std::string lcsc_code(const schgen::CircuitPartIr& part) {
    require(std::count_if(part.fields.begin(), part.fields.end(), [](const auto& f) { return f.key == "LCSC"; }) == 1,
            "unique reviewed LCSC " + part.ref);
    return std::find_if(part.fields.begin(), part.fields.end(), [](const auto& f) { return f.key == "LCSC"; })->value;
}
inline void require_capacitor(const schgen::CircuitPartIr& part, const std::string& value,
                              const std::string& footprint, const std::string& code) {
    require(part.lib_id == "Device:C" && part.value == value && part.footprint == "Capacitor_SMD:" + footprint &&
            lcsc_code(part) == code, "reviewed capacitor identity " + part.ref);
}
inline void restore_capacitor(schgen::CircuitSheetIr& live, const std::string& ref) {
    auto& part = unique_part(live, ref);
    require_capacitor(part, "10u", "C_0805_2012Metric", "C15850");
    part.value = "100n";
    part.footprint = "Capacitor_SMD:C_0603_1608Metric";
    for (auto& f : part.fields) if (f.key == "LCSC") f.value = "C14663";
}
inline void drop_pin(schgen::CircuitSheetIr& live, const std::string& net_name, const std::string& ref, const std::string& pin) {
    require(std::count_if(live.nets.begin(), live.nets.end(), [&](const auto& n) { return n.name == net_name; }) == 1,
            "unique reviewed net " + net_name);
    auto& net = *std::find_if(live.nets.begin(), live.nets.end(), [&](const auto& n) { return n.name == net_name; });
    require(!net.pins.empty() && net.pins.back().ref == ref && net.pins.back().pin == pin,
            "reviewed trailing pin " + ref + "." + pin + " on " + net_name);
    net.pins.pop_back();
}
inline void drop_clamp_capacitor(schgen::CircuitSheetIr& live, const std::string& ref,
                                 const std::string& supply_net) {
    require_capacitor(unique_part(live, ref), "100n", "C_0603_1608Metric", "C14663");
    drop_pin(live, supply_net, ref, "1");
    drop_pin(live, "GND", ref, "2");
    live.parts.erase(std::find_if(live.parts.begin(), live.parts.end(), [&](const auto& p) { return p.ref == ref; }));
}
inline void drop_centre_tap_capacitor(schgen::CircuitSheetIr& live, const std::string& ref) {
    require_capacitor(unique_part(live, ref), "100n", "C_0603_1608Metric", "C14663");
    require(live.nc.empty(), "reviewed centre taps already unconnected");
    const std::vector<schgen::CircuitPinRefIr> taps{{"T1", "1"}, {"T1", "10"}, {"T1", "4"}, {"T1", "7"}};
    const auto drop_net = [&](const std::string& name, const std::vector<std::string>& pins) {
        const auto net = std::find_if(live.nets.begin(), live.nets.end(), [&](const auto& n) { return n.name == name; });
        require(net != live.nets.end() && net->pins.size() == pins.size(), "reviewed net " + name);
        for (std::size_t i = 0; i < pins.size(); ++i)
            require(net->pins[i].ref + "." + net->pins[i].pin == pins[i], "reviewed pin " + pins[i] + " on " + name);
        live.nets.erase(net);
    };
    drop_net("ETH_TCT", {"T1.1", "T1.4", "T1.7", "T1.10", ref + ".1"});
    drop_net("GND", {ref + ".2"});
    live.parts.erase(std::find_if(live.parts.begin(), live.parts.end(), [&](const auto& p) { return p.ref == ref; }));
    live.nc = taps;
}
inline void restore_reset_button(schgen::CircuitSheetIr& live) {
    require(std::none_of(live.parts.begin(), live.parts.end(), [](const auto& p) { return p.ref == "SW5" || p.ref == "C4"; }),
            "reviewed reset button already absent");
    const auto sw4 = unique_part(live, "SW4");
    const auto c3 = unique_part(live, "C3");
    require_capacitor(c3, "100n", "C_0603_1608Metric", "C14663");
    auto sw5 = sw4; sw5.ref = "SW5";
    auto c4 = c3; c4.ref = "C4";
    const auto r9 = std::find_if(live.parts.begin(), live.parts.end(), [](const auto& p) { return p.ref == "R9"; });
    require(r9 != live.parts.end() && r9 != live.parts.begin() && std::prev(r9)->ref == "R8", "reviewed reset button slot");
    const auto slot = live.parts.insert(r9, sw5);
    live.parts.insert(std::next(slot), c4);
    auto gnd = std::find_if(live.nets.begin(), live.nets.end(), [](const auto& n) { return n.name == "GND"; });
    require(gnd != live.nets.end(), "reviewed ground net");
    const auto c3_ground = std::find_if(gnd->pins.begin(), gnd->pins.end(), [](const auto& p) { return p.ref == "C3" && p.pin == "2"; });
    require(c3_ground != gnd->pins.end(), "reviewed debounce ground pin");
    gnd->pins.insert(std::next(c3_ground), {{"SW5", "3"}, {"SW5", "4"}, {"C4", "2"}});
    const auto before = std::find_if(live.nets.begin(), live.nets.end(), [](const auto& n) { return n.name == "PUDC_34"; });
    require(before != live.nets.end() && before != live.nets.begin() && std::prev(before)->name == "PL_BTN1" &&
            std::none_of(live.nets.begin(), live.nets.end(), [](const auto& n) { return n.name == "STM32_NRST"; }),
            "reviewed reset net slot");
    schgen::CircuitNetIr reset;
    reset.name = "STM32_NRST"; reset.net_class = "port"; reset.pins = {{"SW5", "1"}, {"SW5", "2"}, {"C4", "1"}};
    live.nets.insert(before, reset);
}
inline void restore_module_connector(schgen::CircuitSheetIr& live, const std::string& ref) {
    auto& part = unique_part(live, ref);
    require(part.lib_id == "DF40C-100DP-0.4V_51:DF40C-100DP-0.4V_51_module_mate" &&
            part.footprint == "Mylibrary:HRS_DF40C-100DP-0.4V_51_" && lcsc_code(part) == "C531031",
            "reviewed module connector identity " + live.name + "." + ref);
    part.lib_id = "DF40C-100DP-0.4V_51:DF40C-100DP-0.4V_51";
    part.footprint = "DF40C-100DP-0.4V_51:DF40C-100DP-0.4V_51";
    const std::vector<std::pair<std::string, std::string>> pads{{"S4", "101"}, {"S3", "102"}, {"S2", "103"}, {"S1", "104"}};
    for (const auto& [mate, symbol] : pads) {
        require(std::count(part.pin_numbers.begin(), part.pin_numbers.end(), mate) == 1, "reviewed mate pad " + ref + "." + mate);
        *std::find(part.pin_numbers.begin(), part.pin_numbers.end(), mate) = symbol;
        for (auto& name : part.pin_names)
            for (auto& number : name.numbers)
                if (number == mate) number = symbol;
        for (auto& pin : live.nc)
            if (pin.ref == ref && pin.pin == mate) pin.pin = symbol;
    }
}
inline schgen::CircuitSheetIr project_reviewed_circuit(schgen::CircuitSheetIr live, const std::string& project_name) {
    if (live.name == "som_j1") restore_module_connector(live, "J1");
    if (live.name == "som_j2") restore_module_connector(live, "J2");
    if (live.name == "som_j3") restore_module_connector(live, "J3");
    if (project_name == "carrier" && live.name == "bringup_modules") {
        for (const auto* ref : {"C1", "C3", "C5", "C7", "C9", "C11", "C13", "C15", "C17", "C19", "C4", "C12", "C16", "C18"})
            restore_capacitor(live, ref);
    }
    if (project_name == "carrier" && live.name == "motor_pwm") restore_capacitor(live, "C2");
    if (project_name == "carrier" && live.name == "board_qwiic") drop_clamp_capacitor(live, "C1", "+3V3");
    if (project_name == "carrier" && live.name == "lcd") drop_clamp_capacitor(live, "C6", "+3V3");
    if (live.name == "pd_input") drop_clamp_capacitor(live, "C4", "+3V3_SC");
    if (project_name == "carrier" && live.name == "bringup_rails") restore_reset_button(live);
    if (project_name == "carrier" && live.name == "ethernet") drop_centre_tap_capacitor(live, "C6");
    return live;
}
inline schgen::CircuitSheetIr project(schgen::CircuitSheetIr live,
                                     const std::string& project_name) {
    live = project_reviewed_circuit(std::move(live), project_name);
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
    if (!schgen::authoring_json_equal(schgen::authored_circuit_json(project_reviewed_circuit(live, project_name)),
                                      schgen::authored_circuit_json(live))) {
        bool refused = false;
        try { (void)project_reviewed_circuit(project_reviewed_circuit(live, project_name), project_name); }
        catch (const std::runtime_error&) { refused = true; }
        require(refused, "reviewed projection accepted an already-historical sheet");
        auto drift = live; drift.title += " drift";
        require(!matches(project(drift, project_name)), "reviewed projection hid unrelated drift");
        auto stray = live; stray.parts.push_back({"R9999", "Device:R", "1k", "Resistor_SMD:R_0603_1608Metric", {}, {}, {}});
        require(!matches(project(stray, project_name)), "reviewed projection hid an added part");
    }
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
