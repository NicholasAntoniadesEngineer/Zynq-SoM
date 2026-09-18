#pragma once

#include "schgen/circuit.hpp"

#include <string>
#include <vector>

namespace schgen {
struct BomRow {
    std::string value, footprint, lcsc;
    std::vector<std::string> refs;
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
}
