#pragma once
#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
// Compact-mode only. Retains the incumbent and every existing variant/index.
// Whole-zone turns never exchange faces or rewrite footprint/pin documents.
// first_original limits work to an appended suffix; it does not prune offers
// or make a global packer preserve an incumbent across different offer sets.
void append_rigid_zone_orientations(Context&, Geometry&, const std::string&,
                                    const Shape& incumbent, std::size_t first_original = 0);
void append_contract_group_faces(Context&, Geometry&, const std::string&, const Shape&);
}
