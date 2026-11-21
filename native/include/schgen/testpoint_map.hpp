#pragma once

#include "schgen/design_rules.hpp"
#include "schgen/pcb_model.hpp"
#include "schgen/project.hpp"

#include <string>
#include <vector>

namespace schgen {

struct TestpointRow {
    std::string ref, net, sheet, face;
    double x = 0, y = 0;
};

struct TestpointWaiverRow {
    std::string net, sheet, reason;
};

struct TestpointMap {
    std::vector<TestpointRow> rows;
    std::vector<TestpointWaiverRow> waivers;
    std::string text() const;
};

TestpointMap build_testpoint_map(const PcbModel& model, const TestpointCoverage& coverage);

std::vector<std::string> verify_testpoint_map(const TestpointMap& map, const std::vector<CircuitSheetIr>& sheets,
                                              const SheetIndex& index, const PcbModel& model,
                                              const TestpointCoverage& coverage);

}
