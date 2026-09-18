#pragma once
#include "schgen/project.hpp"
#include "schgen/schematic.hpp"
#include <map>
#include <set>

namespace schgen {
struct FootprintResolutionOptions {
    std::filesystem::path parts_dir, kicad_footprint_root;
    std::vector<std::filesystem::path> library_tables;
    std::map<std::string, std::string> aliases;
};
using FootprintPaths = std::map<std::string, std::filesystem::path>;
FootprintPaths load_footprint_library_tables(const FootprintResolutionOptions&);
std::optional<std::filesystem::path> resolve_footprint(const std::string&,
    const FootprintPaths&, const FootprintResolutionOptions&);
// Legacy quoted-pad scan, including multiline and duplicate pads, excluding
// empty numbers. No semantic-parser substitution that changes accepted inputs.
std::set<std::string> footprint_pad_numbers(std::string_view text);
std::set<std::string> read_footprint_pad_numbers(const std::filesystem::path&);
using FootprintPadResolver = std::function<std::optional<std::set<std::string>>(const std::string&)>;
using SymbolPinNumberResolver = std::function<std::set<std::string>(const std::string&)>;
struct FootprintPadsResult {
    bool ok = true;
    std::size_t checked = 0;
    std::vector<std::string> violations, unresolved;
    std::string report() const;
};
FootprintPadsResult check_footprint_pads(const std::vector<ProjectCircuit>&,
    const SymbolPinNumberResolver&, const FootprintPadResolver&);
FootprintPadsResult check_footprint_pads(const std::vector<ProjectCircuit>&,
    SymbolLibrary&, const FootprintResolutionOptions&);
FootprintPadsResult run_footprint_pads(const std::vector<ProjectCircuit>&,
    SymbolLibrary&, const FootprintResolutionOptions&, const std::filesystem::path& report_dir);
JsonNode footprint_pads_result_json(const FootprintPadsResult&);
}  // namespace schgen
