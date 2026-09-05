#pragma once

#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

#include <optional>
#include <string>
#include <utility>

namespace schgen {

// Pad (at x, at y, half-extent w, half-extent h) from a footprint pad node.
// Missing / short `at` or `size` children → nullopt (Python `_pad_geom`).
struct PadGeom {
    double at_x = 0.0;
    double at_y = 0.0;
    double half_w = 0.0;
    double half_h = 0.0;
};

// `_embed_footprint` body assembly only (embed.py 102–131, not the
// property/pad walk). `footprint_tree[1]` must already be the aliased
// library name. `instance_rotation` is omitted from `(at …)` when it is
// 0.0 (Python `if inst.rotation`). `instance_side == "bottom"` runs
// `flip_to_bottom`. `footprint_uuid` is the already-computed
// `uid("fp:{ref}")` string.
//
// Bind (do not edit module.cpp from this kernel):
//   tree = sexpr_from_py(mod)
//   return sexpr_to_tagged(embed_footprint_body(move(tree), x, y, rot,
//                                               side, uuid))
// Python recovers a native list via `_from_tagged`.
Sexpr embed_footprint_body(Sexpr footprint_tree, double instance_x,
                           double instance_y, double instance_rotation,
                           const std::string& instance_side,
                           const std::string& footprint_uuid);

// `_pad_geom` (embed.py 188–194) using `pad_half_extent` for the size
// half-box. Bind: sexpr_from_py(pad) → optional (at_x, at_y, hw, hh).
std::optional<PadGeom> pad_geom(const Sexpr& pad_node);

// `_beside` offset only (stage_templates.py 139–158). Caller supplies
// courtyard halves; this does not load a footprint. Unknown `direction`
// falls through to D, matching Python. Final pair is `py_round(..., 4)`.
// Bind: Box4 from (t[0], t[1], t[2], t[3]); along_center is nullopt when
// Python passes None.
std::pair<double, double> beside_offset(
    double courtyard_hx, double courtyard_hy, const Box4& target,
    const std::string& direction, double gap,
    const std::optional<double>& along_center);

}  // namespace schgen
