#pragma once

namespace schgen::board_decision_policy {
// Producer policy shared with the independent board registry. Keep literals
// and operation order unchanged at consumer sites: these are not new fits.
inline constexpr double zone_pack_fill = .62;
inline constexpr double edge_zone_aspect = 2.2;
inline constexpr double interior_zone_aspect = 2.0;
inline constexpr double interior_band_target = 32.0;
inline constexpr int df40_min_pins = 40;
inline constexpr double breathe_epsilon_mm = 1e-4;
inline constexpr double breathe_step_mm = .25;
// Default and live consumers share the same reviewed policy storage.
namespace floorplan {
inline constexpr double clear = .3;
inline constexpr double small_part_routing_factor = 3.5;
}
namespace placement {
inline constexpr double clear = .5;
}
namespace pack {
inline constexpr double point_segment_tolerance_mm = 1e-6;
inline constexpr double visual_axis_tolerance_mm = 1e-6;
inline constexpr double collinear_overlap_tolerance_mm = 1e-6;
// Cross products have squared-coordinate units, not a linear clearance.
inline constexpr double segment_cross_tolerance_mm2 = 1e-9;
inline constexpr double label_courtyard_gap_mm = .9;
// Preserve the established double literal; do not recompute from pi.
inline constexpr double label_orbit_tau = 6.283185307179586;
}
namespace compose {
inline constexpr double guard_mm = 4.0;
inline constexpr int repair_max = 16, median_passes = 8, channel_min_nets = 6;
inline constexpr double channel_floor = 2.0, channel_per_net = .2;
inline constexpr double hop_weight = 1.0, seed_weight = .05;
}
namespace svg {
inline constexpr double ox = 46, oy = 64, scale = 6;
}
namespace escape {
inline constexpr double radius = 1.8, lattice = .05, lane_handle = 1., hole_hole = .5;
}
}
