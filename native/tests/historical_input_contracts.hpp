#pragma once
#include "schgen/authoring.hpp"
#include <algorithm>
#include <stdexcept>

// Test-only bridge to immutable migration oracles. Validate the reviewed live
// identity BEFORE projecting exactly three fields; all other IR stays visible
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
    return live;
}

// Exercise each consumer's actual comparator, including canonical bytes/hash.
// Reverted/ambiguous identities must fail, as must unrelated electrical drift.
template<class Matches> void check(const schgen::CircuitSheetIr& live,
                                  const std::string& project_name, Matches matches) {
    require(matches(project(live, project_name)), project_name + ":" + live.name +
        " differs beyond reviewed C1 delta from immutable historical input");
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
    // Identical sheet names in another project receive no projection.
    require(schgen::authoring_json_equal(schgen::authored_circuit_json(project(live, "devkit_mini")),
        schgen::authored_circuit_json(live)), "C1 projection crossed project boundary");
}
} // namespace historical_input_contracts
