#pragma once
#include "schgen/schematic.hpp"

namespace schgen {
struct SymbolLawResult {
    std::vector<std::string> violations, pending;
    bool ok() const { return violations.empty(); }
    std::string summary() const;
};
// Explicit policy replaces the mutable PENDING_MIGRATION module global.
// Only SymbolError lookup failures mean "not a power flag"; other exceptions
// propagate. A direct (power) raw child is authoritative, not lib_id spelling.
bool symbol_is_power_flag(const SchematicSymbolResolver&, const std::string& lib_id);
SymbolLawResult check_symbol_law(const std::vector<CircuitSheetIr>&,
    const SchematicSymbolResolver&, const std::map<std::string, std::string>& pending = {});
SymbolLawResult check_symbol_law(const std::vector<CircuitSheetIr>&,
    SymbolLibrary&, const std::map<std::string, std::string>& pending = {});
JsonNode symbol_law_result_json(const SymbolLawResult&);
}  // namespace schgen
