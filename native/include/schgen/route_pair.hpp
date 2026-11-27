#pragma once

#include "schgen/route_search.hpp"

#include <optional>
#include <string>
#include <vector>

namespace schgen::route {

namespace constants {
inline constexpr NamedConstant pair_reach{"pair_reach", 2500000, "nm", "policy",
    "distance from the middle of a pair's two pads within which the coupled run may begin and end; the two short tracks from the pads to it are the uncoupled breakout, well inside the 0.25 inch TI allows (SPRAAR7J, read 2026-11-27)"};
inline constexpr std::array route_pair_registry{pair_reach};
}

struct PairEnds {
    std::vector<std::size_t> near_first, near_second, far_first, far_second;
};

struct PairResult {
    bool coupled = false;
    std::vector<std::size_t> first_items, second_items;
    double coupled_length = 0, loose_length = 0;
    std::size_t opened = 0;
    std::string why;
};

std::optional<std::string> pair_partner(const std::string& name);
bool pair_names(const std::string& first, const std::string& second);
PairResult route_pair(World& world, const SearchSetup& setup, int first, int second, const PairEnds& ends);

}
