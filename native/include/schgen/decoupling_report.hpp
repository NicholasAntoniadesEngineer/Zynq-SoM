#pragma once

#include "schgen/placement_integrity.hpp"
#include "schgen/rules.hpp"

#include <string>
#include <vector>

namespace schgen {

struct DecouplingRow {
    std::string sheet, owner, pin, net, cap, value, role;
    double gap = 0, reach = 0;
    bool beside = false, under = false, judged = false, pass = false;
};

struct DecouplingReport {
    std::vector<DecouplingRow> rows;
    std::size_t failures(std::string_view role) const;
    std::size_t failures() const;
    std::string text() const;
};

DecouplingReport build_decoupling_report(const rules::RuleContext& context);

std::vector<std::string> verify_decoupling_report(const DecouplingReport& report, const rules::RuleContext& context,
                                                  const layout::AuthoredIntent& intent, const rules::RuleResult& bypass_rule);

}
