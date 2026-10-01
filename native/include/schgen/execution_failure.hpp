#pragma once
#include "schgen/execution_accounting.hpp"

namespace schgen {
// Borrowed only during a synchronous operation. Success leaves this channel
// untouched; the ordinary return value retains sole ownership of its receipt.
// Failure publishes a value-owned prefix, never geometry or a borrowed sink.
struct ExecutionFailureReceipt {
    bool captured = false;
    bool unavailable = false;
    ExecutionAccounting accounting;
};
inline void invalidate_execution_failure(ExecutionFailureReceipt* sink) {
    if (!sink) return;
    sink->captured=false;
    sink->unavailable=true;
    sink->accounting={};
}
inline void merge_execution_counts(QuantizationCounts& into,
    const QuantizationCounts& delta, ExecutionFailureReceipt* failure) {
    try { checked_quantization_merge(into,delta); }
    catch (const std::overflow_error&) { invalidate_execution_failure(failure);throw; }
}
inline void append_execution_accounting(ExecutionAccounting& into,
    const ExecutionAccounting& delta, ExecutionFailureReceipt* failure=nullptr) {
    auto next=into;
    merge_execution_counts(next.quantization_engagements,delta.quantization_engagements,failure);
    next.fallback_events.insert(next.fallback_events.end(),delta.fallback_events.begin(),delta.fallback_events.end());
    into=std::move(next);
}
inline void capture_execution_failure(ExecutionFailureReceipt* sink,
    ExecutionAccounting prefix, const ExecutionFailureReceipt* child=nullptr) {
    if(!sink)return;
    // An unrepresentable successful-child merge must never become a smaller,
    // apparently complete prefix while unwinding through outer owners.
    if(sink->unavailable || (child && child->unavailable)) {
        invalidate_execution_failure(sink);return;
    }
    if(child && child->captured)append_execution_accounting(prefix,child->accounting,sink);
    sink->accounting=std::move(prefix);
    sink->captured=true;
}
}
