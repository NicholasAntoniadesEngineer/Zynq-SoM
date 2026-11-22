#pragma once

#include "schgen/named_constant.hpp"

#include <array>

namespace schgen::contract_search {

inline constexpr NamedConstant branch_width{"branch_width", 4, "seats", "policy",
    "distinct seats tried for one contract member before the zone solver goes back to the member before it; four reach every side of an anchor"};
inline constexpr NamedConstant branch_spacing{"branch_spacing", 4.0, "mm", "policy",
    "least distance between two seats counted as distinct; wider than a small passive, so an alternative is a different place and not the next grid cell"};
inline constexpr NamedConstant node_budget{"node_budget", 96, "seats", "policy",
    "most seats tried for one contract cluster at one widen scale; exhausting it fails that scale and proves nothing about other seats"};
inline constexpr std::array registry{branch_width, branch_spacing, node_budget};

}
