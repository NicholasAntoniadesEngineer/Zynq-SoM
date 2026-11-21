#pragma once

#include "schgen/assembly_facts.hpp"
#include "schgen/order_files.hpp"

#include <string>
#include <vector>

namespace schgen {

struct AssemblyPartsVerdict {
    std::vector<std::string> failures, advisories, facts;
    bool ok() const { return failures.empty(); }
    std::string report() const;
    std::string summary() const;
};

AssemblyPartsVerdict check_assembly_parts(const std::vector<CircuitSheetIr>& sheets, const OrderFiles& files,
                                          const AssemblyFacts& facts, const PartFacts& part_facts, int build_count);

}
