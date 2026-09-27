#pragma once
#include "schgen/execution_accounting.hpp"
#include <utility>

namespace schgen::board_pipeline_detail {
// Only producer failures enter this catch. Import failures propagate once and
// are never mistaken for producer failures or retried with the same receipt.
template<class Run,class Import>
auto with_precision_receipt(Run&& run,Import&& import) {
    QuantizationCounts counts;
    auto result=[&]{
        try { return std::forward<Run>(run)(counts); }
        catch (...) { std::forward<Import>(import)(counts);throw; }
    }();
    std::forward<Import>(import)(counts);
    return result;
}
}
