#pragma once

#include "schgen/assembly_facts.hpp"
#include "schgen/bom.hpp"
#include "schgen/fabricator.hpp"
#include "schgen/pcb_model.hpp"
#include "schgen/project.hpp"

#include <set>
#include <string>
#include <vector>

namespace schgen {

struct OrderFiles {
    std::string bom, cpl;
    std::set<std::string> unplaced, placed;
    std::vector<BomRow> lines;
};

struct OrderFilesVerdict {
    std::vector<std::string> failures, advisories, facts;
    bool ok() const { return failures.empty(); }
    std::string report() const;
    std::string summary() const;
};

OrderFiles build_order_files(const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PcbModel& model,
                             const FabricatorProfile& profile, const AssemblyFacts& facts);
OrderFilesVerdict check_order_files(const std::string& bom, const std::string& cpl, const std::set<std::string>& unplaced,
                                    const FabricatorProfile& profile);

}
