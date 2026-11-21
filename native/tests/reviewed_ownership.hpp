#pragma once
#include "schgen/placement_requirements.hpp"
#include <algorithm>
#include <stdexcept>
#include <tuple>

namespace reviewed_ownership {
using schgen::PlacementRequirements;
using schgen::SupplyOwnership;

inline PlacementRequirements reviewed(const std::string& sheet) {
    PlacementRequirements d;
    d.sheet = sheet;
    if (sheet == "board_aux") {
        d.owners = {{"U1", "SY6280AAC"}, {"U2", "PCA9306DCUR"}};
        d.ownership = {
            {"U1", "5", "IN", "C1", "1", "2", "+3V3", "GND", "10u", "input_bypass"},
            {"U1", "1", "OUT", "C2", "1", "2", "+3V3_AUX", "GND", "100n", "output_bypass"},
            {"U1", "1", "OUT", "C3", "1", "2", "+3V3_AUX", "GND", "10u", "shared_output_bulk"},
            {"U2", "2", "VREF1", "C4", "1", "2", "+3V3_SC", "GND", "100n", "authored_reference_rail_bypass_not_translation_filter"},
            {"U2", "7", "VREF2", "C5", "1", "2", "AUX_ISO_REF", "GND", "100p", "reference_filter"}};
        d.top_switches = {"SW1"};
    } else if (sheet == "bringup_rails") {
        d.owners = {{"U1", "TCA9535PWR"}};
        d.ownership = {{"U1", "24", "VCC", "C1", "1", "2", "+3V3_SC", "GND", "100n", "supply_bypass"}};
        d.top_switches = {"SW1", "SW2", "SW3", "SW4", "SW5", "SW6"};
    } else throw std::runtime_error("no reviewed ownership for " + sheet);
    return d;
}

inline std::string mismatch(const PlacementRequirements& actual) {
    const auto want = reviewed(actual.sheet);
    auto a = actual.ownership, b = want.ownership;
    auto less = [](const SupplyOwnership& x, const SupplyOwnership& y) {
        return std::tie(x.owner, x.pin, x.pin_name, x.cap, x.cap_pin, x.return_pin, x.rail, x.return_net, x.value, x.role)
             < std::tie(y.owner, y.pin, y.pin_name, y.cap, y.cap_pin, y.return_pin, y.rail, y.return_net, y.value, y.role);
    };
    std::sort(a.begin(), a.end(), less);
    std::sort(b.begin(), b.end(), less);
    if (a != b) return "omitted, extra or wrong ownership declaration";
    if (actual.top_switches != want.top_switches) return "omitted, extra or wrong access declaration";
    if (actual.owners != want.owners) return "omitted, extra or wrong owner part numbers";
    return "";
}

inline schgen::PlacementRequirementReport check(
    const PlacementRequirements& requirements, const schgen::CircuitSheetIr& circuit,
    const std::map<std::string, schgen::CatalogPart>& catalog, const schgen::PcbCheckInput& placed,
    const std::map<std::string, std::string>& refs, const std::map<std::string, std::string>& nets) {
    const auto problem = mismatch(requirements);
    if (!problem.empty()) {
        schgen::PlacementRequirementReport report;
        report.sheet = requirements.sheet;
        report.violations.push_back(problem);
        return report;
    }
    return schgen::check_placement_requirements(requirements, circuit, catalog, placed, refs, nets);
}
}
