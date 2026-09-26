#pragma once

namespace schgen {

// Pure operations: producers count actual calls in invocation-owned accounting.
// Preserve each original rounding boundary, including nested position rounds.
double estimate_position_precision(double value);
double estimate_pad_precision(double value);
double breathe_delta_precision(double value);
double breathe_commit_precision(double value);

// Preserve truncation toward zero, not floor/ceil. A finite positive step is
// required; reject a nonfinite quotient or an unrepresentable result before
// narrowing. Forward adds one only after the original int conversion.
int breathe_forward_steps(double distance, double step);
int breathe_retreat_steps(double distance, double step);

// Different historical rounding laws: do not combine these operations.
// Mechanical rounds ties-even, then rejects nonfinite/out-of-int-range
// results before narrowing. Stage retains std::round's ties-away/IEEE result.
int mechanical_direction_component(double value);
double stage_direction_component(double value);

// Floorplan candidate decisions and ledger construction keep distinct scalar
// boundaries. Cached ledger rendering does not execute these operations.
double floorplan_candidate_area_precision1dp(double value);
double floorplan_seed_aspect_precision4dp(double value);
double floorplan_ledger_value_precision1dp(double value);
double floorplan_ledger_margin_precision3dp(double value);
double floorplan_ledger_dimension_precision4dp(double value);
double floorplan_ledger_display_precision4dp(double value);

} // namespace schgen
