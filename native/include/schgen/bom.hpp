#pragma once

#include "schgen/circuit.hpp"

#include <string>
#include <vector>

namespace schgen {
struct BomRow {
    std::string value, footprint, lcsc;
    std::vector<std::string> refs;
};
struct BomEntry {
    std::string designator, value, footprint, lcsc;
};
struct BomOutput {
    std::vector<BomRow> rows;
    std::vector<std::string> missing_lcsc, missing_footprints;
    std::string csv;
};
// Sheet-qualified refs match board manufacturing output. The standalone
// historical `bom <sheets>` command uses unqualified refs instead.
BomOutput generate_bom(const std::vector<CircuitSheetIr>& sheets,
                       bool qualified_refs = true);
// With one_line_per_code, entries that share an order code and a footprint form one line whose comment is
// the least of their values; otherwise a line is one value, footprint and code.
std::vector<BomRow> group_bom_entries(const std::vector<BomEntry>& entries, bool one_line_per_code = false);
std::string bom_csv_cell(const std::string& value);
}
