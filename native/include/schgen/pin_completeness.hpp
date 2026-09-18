#pragma once
#include "schgen/project.hpp"
#include "schgen/schematic.hpp"
#include <map>
#include <set>

namespace schgen {
using NcAllowlist = std::map<std::string, std::map<std::string, std::set<std::string>>>;
NcAllowlist nc_allowlist_from_json(const JsonNode&);
NcAllowlist load_nc_allowlist(const std::filesystem::path&); // Missing file -> empty.
struct PinCompletenessResult {
    bool ok = true;
    std::size_t parts_checked = 0, nc_total = 0;
    std::vector<std::string> floats, nc_seeded, nc_new;
    std::string report() const;
};
// Includes two-pin parts, exactly as Python's len(pins)>=2 condition. Silent
// floats set ok=false despite legacy REPORT-FIRST wording; no promotion/demotion.
PinCompletenessResult check_pin_completeness(const std::vector<ProjectCircuit>&,
    const SchematicSymbolResolver&, const NcAllowlist& = {});
PinCompletenessResult check_pin_completeness(const std::vector<ProjectCircuit>&,
    SymbolLibrary&, const NcAllowlist& = {});
PinCompletenessResult run_pin_completeness(const std::vector<ProjectCircuit>&,
    SymbolLibrary&, const NcAllowlist&, const std::filesystem::path& report_dir);
JsonNode pin_completeness_result_json(const PinCompletenessResult&);
}  // namespace schgen
