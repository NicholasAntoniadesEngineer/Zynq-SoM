#pragma once
#include "schgen/execution_accounting.hpp"
#include <stdexcept>

namespace ledger_accounting_fixture {
// Historical full-board fixtures predate two real est_via_cost entries in
// Engine::ledger_initial. Use ONLY for one completed Engine::run, never a
// partial/helper receipt. native_floorplan_receipt_contracts independently
// instruments the two entries and verifies exception/overflow behavior.
inline schgen::QuantizationCounts before_initial_receipt_fix(
    schgen::QuantizationCounts counts) {
    const auto found=counts.find("est_via_cost");
    if(found==counts.end() || found->second<2)
        throw std::runtime_error("missing two ledger_initial via-cost entries");
    found->second-=2;
    if(found->second==0)counts.erase(found);
    return counts;
}
inline void contracts() {
    using schgen::QuantizationCounts;
    const QuantizationCounts prior{{"est_via_cost",7},{"est_via_cost_typo",3},{"unknown",5}};
    auto actual=prior;actual.at("est_via_cost")+=2;
    if(before_initial_receipt_fix(actual)!=prior ||
       !before_initial_receipt_fix({{"est_via_cost",2}}).empty())
        throw std::runtime_error("ledger receipt correction changed unrelated accounting");
    for(const auto& bad:{QuantizationCounts{},QuantizationCounts{{"est_via_cost",1}},
                         QuantizationCounts{{"est_via_cost_typo",2}}}) {
        bool rejected=false;
        try{(void)before_initial_receipt_fix(bad);}catch(const std::runtime_error&){rejected=true;}
        if(!rejected)throw std::runtime_error("missing-entry mutation escaped ledger adapter");
    }
}
}
