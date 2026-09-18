#pragma once
#include "schgen/project.hpp"
#include <map>

namespace schgen {
struct NormalizedBomValue { std::string component_class; double magnitude = 0; };
std::optional<NormalizedBomValue> normalize_bom_value(const std::string& value,
    const std::optional<std::string>& class_hint = std::nullopt);
bool equal_bom_values(const NormalizedBomValue&, const NormalizedBomValue&);
// Catalog JSON scalar spelling (including null/number) remains authoritative.
struct BomValueEntry { JsonNode value, note; bool has_value = false; };
using BomValueCatalog = std::map<std::string, BomValueEntry>;
BomValueCatalog bom_value_catalog_from_json(const JsonNode&);
BomValueCatalog load_bom_value_catalog(const std::filesystem::path&);
struct BomValueResult {
    bool ok = true;
    std::size_t checked = 0, catalog_size = 0;
    std::vector<std::string> mismatches, unverified;
    std::string report() const;
};
BomValueResult check_bom_values(const std::vector<ProjectCircuit>&, const BomValueCatalog&);
// Does not create report_dir, matching bom_values.run; throws on failed I/O.
BomValueResult run_bom_values(const std::vector<ProjectCircuit>&, const BomValueCatalog&,
    const std::filesystem::path& report_dir);
JsonNode bom_value_result_json(const BomValueResult&);
}  // namespace schgen
