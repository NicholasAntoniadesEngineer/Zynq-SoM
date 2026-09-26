#include "native_audit_quantize_internal.hpp"
#include "schgen/quantize.hpp"
#include "schgen/occupancy.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>

namespace schgen {
double native_breathe_anchor_grid(double value){return fixed_part_grid(value);}
double native_seat_slide(){return 1.2;}
double native_run_overflow_tol(){return 0.1;}
double native_refit_pose_precision(double value){return py_round(value,4);}
int native_checked_step(double value){
    if(!std::isfinite(value)||value!=std::trunc(value)||value<std::numeric_limits<int>::min()||value>std::numeric_limits<int>::max())
        throw std::invalid_argument("quantize: step must fit an exact C++ int");
    return static_cast<int>(value);
}
} // namespace schgen
