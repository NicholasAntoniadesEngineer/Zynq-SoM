#pragma once
#include "schgen/execution_accounting.hpp"
#include <array>
#include <algorithm>
namespace pack_grid_precision_fixture {
inline const std::array<std::string,6> names{{"silk_cell_floor", "breathe_grid_extent",
    "breathe_stamp_index", "breathe_free_index", "refdes_size_precision3dp", "refdes_pose_precision4dp"}};
inline bool added(const std::string& name) {
    return std::find(names.begin(), names.end(), name) != names.end();
}
inline schgen::QuantizationCounts select(const schgen::QuantizationCounts& q, bool additions=true) {
    schgen::QuantizationCounts out;
    for (const auto& [name,n] : q) if (added(name)==additions) out[name]=n;
    return out;
}
}
