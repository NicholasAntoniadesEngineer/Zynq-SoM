#pragma once
#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
// Compact-mode only. Retains the incumbent and every existing variant/index.
// Whole-zone turns never exchange faces or rewrite footprint/pin documents.
void append_rigid_zone_orientations(Context&, Geometry&, const std::string&,
                                    const Shape& incumbent);
}
