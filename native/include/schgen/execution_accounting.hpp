#pragma once

#include <cstddef>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {
using QuantizationCounts = std::map<std::string, std::size_t>;
// Invocation-owned observations; no execution, registry, globals or replay.
struct ExecutionAccounting {
    QuantizationCounts quantization_engagements;
    std::vector<std::string> fallback_events;
};
inline void checked_quantization_add(QuantizationCounts& counts, const std::string& name,
                                     std::size_t amount = 1) {
    const auto p = counts.find(name);
    if (p == counts.end()) {
        counts.emplace(name, amount);
        return;
    }
    if (amount > std::numeric_limits<std::size_t>::max() - p->second)
        throw std::overflow_error("quantization counter overflow: " + name);
    p->second += amount;
}
inline void checked_quantization_merge(QuantizationCounts& counts, const QuantizationCounts& delta) {
    auto next = counts;
    for (const auto& [name, amount] : delta) checked_quantization_add(next, name, amount);
    counts.swap(next);
}
} // namespace schgen
