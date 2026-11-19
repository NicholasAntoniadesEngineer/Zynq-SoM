#pragma once

#include "schgen/pcb_model.hpp"
#include "schgen/rules.hpp"

namespace schgen {

struct PlacementIntegrityResult {
    bool ok = true;
    std::vector<rules::RuleResult> rules;
    const rules::RuleResult& of(std::string_view id) const;
    std::string summary() const;
};

std::string controlled_net(const PcbCheckInstance& instance, const PcbModel& model);
bool drilled_part(const PcbCheckInstance& instance);
bool module_clearance_exempt(const PcbCheckInstance& instance);
PlacementIntegrityResult check_placement_integrity(const PcbCheckInput& input, const PcbModel& model,
                                                   const layout::AuthoredIntent& intent);

}
