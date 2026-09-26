#pragma once
#include "schgen/floorplan.hpp"

namespace schgen {
// Authored declaration metadata, NOT inferred from an observed decision stream
// or compiler census. Legacy covers are provenance only, never C++ coverage.
struct FloorplanLedgerPolicy {
    std::string name, kind, step, unit, basis, source, legacy_cover, expression;
    std::vector<std::string> inputs;
    bool repeated = false;
};
std::vector<FloorplanLedgerPolicy> floorplan_ledger_policy();
struct FloorplanLedgerMigration {
    std::string name, disposition, reason;
    std::vector<std::string> replacements;
};
// Explicit reviewed provenance changes, never inferred from observed rows.
// Five unused board assumptions retire; three claimed physical via operands
// are replaced by the two estimator costs the native algorithm really uses.
// Existing breathe epsilon/search-step policy is now explicitly exposed.
std::vector<FloorplanLedgerMigration> floorplan_ledger_migrations();
// Only providers with actual C++ storage/parameters are exposed here. nullopt
// means the old reporting table has no independently accessible native policy
// value; it MUST NOT be substituted with that table's frozen default.
std::optional<double> floorplan_live_assumption(const std::string&,const FloorplanInput&);
}
