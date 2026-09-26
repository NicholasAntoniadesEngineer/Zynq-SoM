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
}
