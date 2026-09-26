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

} // namespace schgen
