#pragma once

#include "schgen/route_board.hpp"

#include <string>
#include <vector>

namespace schgen::route {

struct CheckReport {
    std::vector<std::string> shorts, clearances, holes, edges, keepouts, opens, strays;
    std::size_t items = 0, nets = 0, joined = 0;
    bool ok() const { return shorts.empty() && clearances.empty() && holes.empty() && edges.empty() && keepouts.empty() && opens.empty() && strays.empty(); }
    std::string summary() const;
};

CheckReport verify(const Board& board, const std::vector<Item>& copper);

}
