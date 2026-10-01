#pragma once
#include "schgen/catalog.hpp"
#include "schgen/pcb_checks.hpp"

namespace schgen {
struct SupplyOwnership {
    std::string owner, pin, pin_name, cap, cap_pin, return_pin, rail, return_net, value, role;
    bool operator==(const SupplyOwnership&) const;
};
struct PlacementRequirements {
    std::string sheet;
    std::vector<SupplyOwnership> ownership;
    std::set<std::string> top_switches;
};
// Malformed, duplicate or unknown fields fail; no numeric policy is inferred.
PlacementRequirements parse_placement_requirements(const JsonNode&);
struct PlacementRequirementDeclaration {
    PlacementRequirements required;
    std::map<std::string, std::string> owner_mpn;
};
// Independent reviewed declarations, not reconstructed from the input manifest.
// Unknown project/sheet throws; it is never an empty successful requirement set.
PlacementRequirementDeclaration carrier_surface_requirement_declaration(const std::string& sheet);
struct OwnedTerminalMeasurement {
    std::string owner, owner_pin, member, member_pin, owner_side, member_side;
    double planar_pad_box_gap_mm = 0;
    // Planar pad-box gap is not copper path length, loop inductance or 3D distance.
};
struct PlacementRequirementReport {
    std::string sheet;
    std::vector<std::string> violations, unverified;
    std::vector<OwnedTerminalMeasurement> measurements;
    bool hard_requirements_met() const { return violations.empty(); }
    std::string status() const { return !violations.empty() ? "FAIL" : "UNVERIFIED"; }
    // This checker never grants additional movement/side permissions.
    std::string summary() const;
};
// Invocation-owned inputs only. Catalog keyed by MPN must come from the actual
// independent part catalog; ref_map/net_map must come from validated hierarchy
// assembly, never be synthesized from the candidate model being checked.
// Complete live pin/net identity is checked, not just the six owned capacitors.
PlacementRequirementReport check_placement_requirements(
    const PlacementRequirements&, const PlacementRequirementDeclaration&,
    const CircuitSheetIr&, const std::map<std::string, CatalogPart>& catalog,
    const PcbCheckInput&, const std::map<std::string,std::string>& ref_map,
    const std::map<std::string,std::string>& net_map);
} // namespace schgen
