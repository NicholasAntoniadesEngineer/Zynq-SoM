#pragma once

#include "schgen/route_search.hpp"

#include <string>
#include <vector>

namespace schgen::route {

namespace constants {
inline constexpr NamedConstant route_passes{"route_passes", 6, "passes", "policy",
    "times the whole board is routed again with the nets that failed routed first; a pass that fails the same nets as the one before ends the search"};
inline constexpr std::array route_run_registry{route_passes};
}

struct RunSetup {
    SearchSetup search;
    std::size_t passes = static_cast<std::size_t>(constants::route_passes.value);
};

struct NetOutcome {
    int net = no_net;
    std::size_t links = 0, joined = 0, vias = 0;
    double length = 0;
    std::string failure;
};

struct RunReport {
    std::vector<NetOutcome> nets;
    std::size_t links = 0, joined = 0, vias = 0, passes = 0, opened = 0;
    double length = 0;
    std::vector<std::size_t> pass_failures;
    bool complete() const { return links == joined; }
    std::string summary(const Board& board) const;
};

RunReport route_all(World& world, const RunSetup& setup);

}
