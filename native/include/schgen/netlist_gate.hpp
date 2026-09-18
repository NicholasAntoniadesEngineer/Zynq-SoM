#pragma once

#include "schgen/circuit.hpp"
#include "schgen/som_interface.hpp"

#include <filesystem>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace schgen {

using ExtractedNetlist = KicadNetlist;
using NetlistExtractOptions = SomExtractOptions;

class NetlistGateError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct NetlistGateResult {
    bool ok = true;
    std::vector<std::string> shorts, opens, nc_cheats, part_mismatches, name_mismatches;
    std::string summary() const;
};

// Ordered XML nets; duplicate names use last value at first position, as in
// Python dicts. Missing nets/attributes are empty, never invented connectivity.
// Uses the shared secure XML parser (no DTDs, external entities or network I/O).
ExtractedNetlist parse_netlist_xml(std::string_view xml,
                                 const std::string& source = "<memory>");
// Always invokes KiCad on the supplied schematic. No catalog or cache fallback.
ExtractedNetlist extract_netlist(const std::filesystem::path& schematic,
                                const NetlistExtractOptions& options = {});

std::string normalize_netlist_name(std::string_view name);
std::vector<std::string> dead_two_terminal(const CircuitSheetIr& circuit);
// Embedded symbol geometry is authoritative here, not IR metadata or a library
// reloaded from disk. Recurses through all symbol units/styles, then applies the
// shared pin_page_position transform and Python two-decimal point rounding.
std::vector<std::string> emitted_nc_cheats(const CircuitSheetIr& circuit,
                                         std::string_view schematic_text);

// Pure check of caller-owned IR, extracted connectivity and schematic text.
// Netlist entries have ordered-dictionary semantics even for manually supplied
// duplicate names. Finding order and wording match the original Python gate.
// All five categories run; failed connectivity never skips the geometry guard.
// Call validate_circuit separately for symbol-backed electrical completeness.
NetlistGateResult check_netlist(const CircuitSheetIr& circuit,
                               const ExtractedNetlist& extracted,
                               std::string_view schematic_text);
// Live gate: export connectivity, read the same schematic, then run all checks.
NetlistGateResult check_netlist(const CircuitSheetIr& circuit,
                               const std::filesystem::path& schematic,
                               const NetlistExtractOptions& options = {});

}  // namespace schgen
