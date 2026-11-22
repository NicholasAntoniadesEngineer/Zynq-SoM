#pragma once

#include "schgen/layout_kernel.hpp"
#include "schgen/named_constant.hpp"

#include <array>
#include <string>
#include <vector>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant construct_reach{"construct_reach", 12e6, "nm", "policy",
    "largest distance from its owner at which the constructor looks for a part's seat; an owned part farther out has lost its tie"};
inline constexpr NamedConstant construct_evictions{"construct_evictions", 4, "parts", "policy",
    "seated parts one part may displace to take its own seat; a part that needs more has no room near its owner and is reported"};
inline constexpr NamedConstant construct_window{"construct_window", 64, "seats", "policy",
    "best seats examined for a displaceable blocker; seats beyond these are far enough from the tie that displacing for them gains nothing"};
inline constexpr NamedConstant construct_branches{"construct_branches", 4, "seats", "policy",
    "distinct seats tried per part when an owner's parts are arranged together; more multiplies the search without finding new arrangements"};
inline constexpr NamedConstant construct_spacing{"construct_spacing", 0.5e6, "nm", "policy",
    "least distance between two seats tried for one part in that search; closer seats block the same neighbours"};
inline constexpr NamedConstant construct_nodes{"construct_nodes", 512, "seats", "policy",
    "seats examined in one such search before the owner's parts are reported as not fitting"};
inline constexpr std::array construct_registry{construct_reach, construct_evictions, construct_window, construct_branches,
                                               construct_spacing, construct_nodes};
}

struct ConstructReport {
    std::size_t taken = 0, seated = 0, returned = 0, searched = 0;
    std::vector<std::string> unseated;
    std::vector<std::string> causes;
    Nm length_before = 0, length_after = 0;
};

ConstructReport construct_owned(Kernel& kernel, Nm pitch, Nm reach);
std::string construct_summary(const ConstructReport& report);

}
