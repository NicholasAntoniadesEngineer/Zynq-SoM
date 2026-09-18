#pragma once

#include "schgen/circuit.hpp"
#include "schgen/symbols.hpp"

#include <cstddef>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

// Vector maps retain Python dictionary insertion order. Report methods sort
// only where the original report sorts, and do not append a final newline.
struct DesignRuleResult {
    std::vector<std::string> decap, i2c, reset, strap, ep, waived;
    std::vector<std::pair<std::string, std::size_t>> checked;
    bool ok() const;
    std::vector<std::string> findings() const;
    std::string summary() const;
    std::string report() const;
};

struct TestpointCoverage {
    std::vector<std::pair<std::string, std::string>> required;
    std::vector<std::pair<std::string, std::vector<std::string>>> have;
    std::vector<std::pair<std::string, std::pair<std::string, std::string>>> waived;
    std::vector<std::string> errors;
    // Legacy field is intentionally empty after check; report derives extras
    // from have, not from this field.
    std::vector<std::pair<std::string, std::vector<std::string>>> extras;
    bool ok() const;
    std::size_t covered() const;
    std::string report() const;
};

// The Python coverage check raises StopIteration for an unnetted testpoint.
// A future Python adapter can translate this specific exception accordingly.
class UnnettedTestpoint : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

using DesignRuleSymbolResolver = std::function<const SymbolDef&(const std::string&)>;

// Owns an immutable snapshot of sheets and resolved pin metadata, with indexed
// sheet pin->first net, ref->part, net->drivers and board-wide RC connectivity.
// Resolve each distinct lib_id once. Ordinary resolver std::exception failures
// (SymbolError, missing ID/out_of_range, runtime_error, etc.) mean empty pins,
// matching Python's broad _pins exception skip. Deliberately do NOT suppress
// std::bad_alloc, std::system_error, or non-std exceptions. Pin-copy/index/report
// failures also propagate; only the resolver invocation has a compatibility
// catch. A resolver must return stable definitions during
// construction. It is never retained or called by check()/check_testpoints().
// No files, catalogs, interpreter, or process-global project state are consulted.
// Construct a NEW index after edits; reusing one intentionally checks its snapshot.
class DesignRuleIndex {
public:
    DesignRuleIndex(std::vector<CircuitSheetIr> sheets,
                    const DesignRuleSymbolResolver& resolve);
    DesignRuleIndex(std::vector<CircuitSheetIr> sheets,
                    const std::vector<SymbolDef>& symbols);
    DesignRuleResult check() const;
    TestpointCoverage check_testpoints() const;

private:
    struct Impl;
    std::shared_ptr<const Impl> impl_;
};

bool is_power_pin_name(const std::string& name);
DesignRuleResult check_design_rules(const std::vector<CircuitSheetIr>& sheets,
                                    const DesignRuleSymbolResolver& resolve);
DesignRuleResult check_design_rules(const std::vector<CircuitSheetIr>& sheets,
                                    const std::vector<SymbolDef>& symbols);
// Coverage requires only circuit IR; no symbol resolution or geometry.
TestpointCoverage check_testpoint_coverage(const std::vector<CircuitSheetIr>& sheets);

// Transport helpers preserve complete result fields, derived properties and
// byte-exact reports. No parsing or reloading of caller-owned circuits occurs.
JsonNode design_rule_result_json(const DesignRuleResult& result);
JsonNode testpoint_coverage_json(const TestpointCoverage& result);

}  // namespace schgen
