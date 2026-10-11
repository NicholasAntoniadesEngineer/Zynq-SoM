#pragma once
#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
// Geometric identity ignores tags and treats absent per-part rotations as zero.
bool same_zone_shape_geometry(const Shape&, const Shape&);
void append_distinct_zone_shapes(Shape incumbent, std::vector<Shape>& existing,
                                const std::vector<Shape>& candidates);
// Compact-mode only. Retains the incumbent and every existing variant/index.
// Whole-zone turns never exchange faces or rewrite footprint/pin documents.
// first_original limits work to an appended suffix; it does not prune offers
// or make a global packer preserve an incumbent across different offer sets.
void append_rigid_zone_orientations(Context&, Geometry&, const std::string&,
                                    const Shape& incumbent, std::size_t first_original = 0);
void append_contract_group_faces(Context&, Geometry&, const std::string&, const Shape&);
}
