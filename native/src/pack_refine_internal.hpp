#pragma once
#include "schgen/pack_refine.hpp"

namespace schgen::floorplan_detail {
// Synchronous read-only search. Caller must supply the dimensions with which
// occupancy was constructed; public adapters retain their resizing semantics.
std::vector<SeatShapeHit> seat_shape_candidates_on_current_board(const Occupancy&,
    double, double, const std::vector<SeatShapeCand>&, double, double, double,
    QuantizationCounts*);
}
